"""Retrieval-mode-aware vectors skip across the remaining vectors-phase call
sites: the installer's ``run_init_if_needed``/``run_update`` indexing sub-steps
and the MCP ``reprocess`` refresh pipeline.

Sibling of ``test_retrieval_lifecycle.py`` (the CLI init/increment/reprocess
commands) and of the graph-only (stack-absent) branches these call sites already
have. Same shape: a tmp project root carrying a ``.java-codebase-rag.yml`` with
``retrieval: bm25`` drives each call site with the pipeline runners monkeypatched
at the ``pipeline`` module seam (the installer imports them function-locally, so
the source module is the patch point). The cocoindex runner fails the test if
invoked — under bm25 there is nothing to embed, so it must never be spawned —
while the graph runner counts. A ``retrieval: vectors`` control pins today's
behavior (cocoindex IS invoked).
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import shutil
import subprocess
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from java_codebase_rag import installer as installer_mod
from java_codebase_rag.config import YAML_CONFIG_FILENAMES
from java_codebase_rag.mcp import server as server_mod
from java_codebase_rag.pipeline import VECTORS_SKIPPED_BM25


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Snapshot os.environ so ``cfg.apply_to_os_environ()`` can't leak between tests.

    Also clears the discovery/retrieval env vars so each test resolves its own
    tmp project from its own YAML (env would otherwise override the YAML tier).
    """
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for var in (
        "JAVA_CODEBASE_RAG_RETRIEVAL",
        "JAVA_CODEBASE_RAG_SOURCE_ROOT",
        "JAVA_CODEBASE_RAG_INDEX_DIR",
    ):
        monkeypatch.delenv(var, raising=False)


def _write_retrieval_yaml(root: Path, retrieval: str) -> None:
    (root / YAML_CONFIG_FILENAMES[0]).write_text(f"retrieval: {retrieval}\n", encoding="utf-8")


def _stub_completed() -> subprocess.CompletedProcess[str]:
    # args length > 1 so the preflight-blocker detectors never mistake this for a
    # pre-spawn stub (those carry returncode 126/127 with args length <= 1).
    return subprocess.CompletedProcess(args=["stub", "cmd"], returncode=0, stdout="", stderr="")


def _calls() -> dict[str, int]:
    return {"coco": 0, "graph": 0, "incremental_graph": 0}


def _install_index_stubs(
    monkeypatch: pytest.MonkeyPatch, calls: dict[str, int], *, coco: str
) -> None:
    """Stub the pipeline runners at the ``pipeline`` module seam.

    ``coco="forbid"`` makes any ``run_cocoindex_update`` call fail the test;
    ``coco="fake"`` counts the call and returns a successful stub (vectors mode).
    """

    def coco_forbidden(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        raise AssertionError("run_cocoindex_update must not be called when retrieval is bm25")

    def coco_fake(*_a: object, **_k: object) -> subprocess.CompletedProcess[str]:
        calls["coco"] += 1
        return _stub_completed()

    def fake_graph(**_k: object) -> subprocess.CompletedProcess[str]:
        calls["graph"] += 1
        return _stub_completed()

    def fake_incremental_graph(**_k: object) -> subprocess.CompletedProcess[str]:
        calls["incremental_graph"] += 1
        return _stub_completed()

    monkeypatch.setattr(
        "java_codebase_rag.pipeline.run_cocoindex_update",
        coco_forbidden if coco == "forbid" else coco_fake,
    )
    monkeypatch.setattr("java_codebase_rag.pipeline.run_build_ast_graph", fake_graph)
    monkeypatch.setattr("java_codebase_rag.pipeline.run_incremental_graph", fake_incremental_graph)


# --- installer: run_init_if_needed --------------------------------------------


def test_run_init_if_needed_bm25_skips_cocoindex_and_builds_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Under ``retrieval: bm25`` the install indexing sub-step never spawns
    cocoindex: it prints the bm25 skip line, builds the graph only, reports
    success, and — exactly like the stack-absent skip path — records the config
    source pointer so discovery can later relocate this YAML from the index dir."""
    _write_retrieval_yaml(tmp_path, "bm25")
    calls = _calls()
    _install_index_stubs(monkeypatch, calls, coco="forbid")

    ok = installer_mod.run_init_if_needed(
        tmp_path,
        tmp_path / ".java-codebase-rag",
        "auto",
        non_interactive=True,
        quiet=True,
        verbose=False,
    )

    assert ok is True
    assert calls["graph"] == 1
    captured = capsys.readouterr()
    assert VECTORS_SKIPPED_BM25 in captured.err
    # The stack-absent wording must not appear: the stack is present, the mode
    # is what skipped the phase.
    assert "vector stack not installed" not in captured.err
    pointer = tmp_path / ".java-codebase-rag" / "config_source"
    assert pointer.is_file(), "skip path did not write the config source pointer"
    assert pointer.read_text(encoding="utf-8").strip() == str(
        (tmp_path / YAML_CONFIG_FILENAMES[0]).resolve()
    )


def test_run_init_if_needed_vectors_mode_still_runs_cocoindex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Control (today's behavior): under ``retrieval: vectors`` the install
    indexing sub-step still runs cocoindex before the graph build."""
    _write_retrieval_yaml(tmp_path, "vectors")
    calls = _calls()
    _install_index_stubs(monkeypatch, calls, coco="fake")

    ok = installer_mod.run_init_if_needed(
        tmp_path,
        tmp_path / ".java-codebase-rag",
        "auto",
        non_interactive=True,
        quiet=True,
        verbose=False,
    )

    assert ok is True
    assert calls["coco"] == 1
    assert calls["graph"] == 1
    assert VECTORS_SKIPPED_BM25 not in capsys.readouterr().err


# --- installer: run_update ----------------------------------------------------


def _install_update_artifact_stubs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make the artifact-refresh phase succeed without touching the real package.

    ``run_update``'s exit code folds artifact failures in, so the retrieval
    assertions below need a deterministic refresh: a configured host whose MCP
    entry already matches (no write), a resolvable binary, and stable package
    content (mirrors the existing run_update tests' stubs)."""
    (tmp_path / ".mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "java-codebase-rag": {
                        "command": "/usr/local/bin/java-codebase-rag-mcp",
                        "type": "stdio",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/local/bin/java-codebase-rag-mcp")
    monkeypatch.setattr(
        "java_codebase_rag.installer._read_package_artifact", lambda path: "PACKAGE CONTENT"
    )


def test_run_update_bm25_skips_cocoindex_and_runs_graph_catchup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Under ``retrieval: bm25`` the update indexing sub-step skips cocoindex and
    runs only the graph catch-up (best-effort graph semantics unchanged), exiting
    0."""
    _write_retrieval_yaml(tmp_path, "bm25")
    index_dir = tmp_path / ".java-codebase-rag"
    index_dir.mkdir()
    (index_dir / "code_graph.lbug").write_text("", encoding="utf-8")  # index exists
    _install_update_artifact_stubs(monkeypatch, tmp_path)
    calls = _calls()
    _install_index_stubs(monkeypatch, calls, coco="forbid")
    # The CLI invokes update from the project dir, so discovery (source_root=None)
    # resolves via Path.cwd() — exactly as increment/init/reprocess do.
    monkeypatch.chdir(tmp_path)

    rc = installer_mod.run_update(force=False, dry_run=False, cwd=tmp_path)

    assert rc == 0
    assert calls["incremental_graph"] == 1
    captured = capsys.readouterr()
    assert VECTORS_SKIPPED_BM25 in captured.err
    assert "vector stack not installed" not in captured.err


def test_run_update_vectors_mode_still_runs_cocoindex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control (today's behavior): under ``retrieval: vectors`` the update
    indexing sub-step still runs the cocoindex catch-up before the graph."""
    _write_retrieval_yaml(tmp_path, "vectors")
    index_dir = tmp_path / ".java-codebase-rag"
    index_dir.mkdir()
    (index_dir / "code_graph.lbug").write_text("", encoding="utf-8")
    _install_update_artifact_stubs(monkeypatch, tmp_path)
    calls = _calls()
    _install_index_stubs(monkeypatch, calls, coco="fake")
    monkeypatch.chdir(tmp_path)

    rc = installer_mod.run_update(force=False, dry_run=False, cwd=tmp_path)

    assert rc == 0
    assert calls["coco"] == 1
    assert calls["incremental_graph"] == 1


# --- MCP reprocess: run_refresh_pipeline --------------------------------------


def test_run_refresh_pipeline_bm25_skips_vectors_and_runs_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``reprocess``'s refresh pipeline under bm25: with the vector stack present
    (the MODE, not the platform, drives the skip) the vectors phase is never
    spawned, the graph-only phase runs, and the operator-facing skip line is the
    bm25 one."""
    monkeypatch.setattr(server_mod, "vector_stack_installed", lambda: True)
    monkeypatch.setenv("JAVA_CODEBASE_RAG_RETRIEVAL", "bm25")
    monkeypatch.setenv("JAVA_CODEBASE_RAG_SOURCE_ROOT", str(tmp_path))
    monkeypatch.setenv("JAVA_CODEBASE_RAG_INDEX_DIR", str(tmp_path / "idx"))

    captured: dict[str, object] = {}

    async def fake_graph_phase(root, *, quiet, verbose, on_progress, on_progress_console):
        captured["called"] = True
        captured["root"] = root
        return 0, "GRAPH_STDOUT", "GRAPH_STDERR", True

    monkeypatch.setattr(server_mod, "_run_graph_phase", fake_graph_phase)

    async def forbidden_spawn(*_a: object, **_k: object):
        raise AssertionError("no subprocess may be spawned when retrieval is bm25")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden_spawn)

    buf = io.StringIO()
    with redirect_stderr(buf):
        out = asyncio.run(server_mod.run_refresh_pipeline(quiet=True))
    err = buf.getvalue()

    assert captured.get("called") is True
    assert out.success is True
    assert out.phases_run == ["graph"]
    assert out.graph_exit_code == 0
    assert VECTORS_SKIPPED_BM25 in err
    assert "vector stack not installed" not in err
    assert "retrieval mode is bm25" in (out.message or "")


def test_run_refresh_pipeline_vectors_mode_still_spawns_cocoindex(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Control (today's behavior): with retrieval vectors (env unset) and the
    stack present, the refresh pipeline resolves cocoindex and spawns it."""
    monkeypatch.setattr(server_mod, "vector_stack_installed", lambda: True)
    monkeypatch.setenv("JAVA_CODEBASE_RAG_SOURCE_ROOT", str(tmp_path))
    monkeypatch.setenv("JAVA_CODEBASE_RAG_INDEX_DIR", str(tmp_path / "idx"))

    on_path = tmp_path / "on_path" / "cocoindex"
    on_path.parent.mkdir(parents=True)
    on_path.write_text("")  # .is_file() True -> the not-found branch is skipped
    monkeypatch.setattr(server_mod, "resolve_cocoindex_bin", lambda: on_path)

    class _FakeProc:
        def __init__(self) -> None:
            self.returncode = 1  # nonzero: stop right after the vectors spawn

        async def communicate(self):
            return b"", b"cocoindex exit 1"

    spawned: list[str] = []

    async def fake_exec(exe, *args, **kwargs):
        spawned.append(exe)
        return _FakeProc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    out = asyncio.run(server_mod.run_refresh_pipeline(quiet=True))

    assert spawned, "cocoindex was never spawned (vectors phase skipped in vectors mode)"
    assert out.exit_code == 1
    assert out.phases_run == ["vectors"]
