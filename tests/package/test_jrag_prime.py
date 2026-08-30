"""Tests for `jrag prime` (Task 2, jrag-prime plan).

Real-behavior subprocess tests against the session bank-chat index, plus the
two halves of the latency contract: an in-process handler run that loads no
new vector-stack module, and a clean-interpreter run of ``main(["prime"])``
that loads none at all. The silence rule (no index -> empty stdout, rc 0) is
what makes a user-scope SessionStart hook tolerable, so it is pinned here
exactly rather than implied.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

_HEAVY_DEPS = ("torch", "sentence_transformers", "lancedb", "pyarrow", "cocoindex")

_IDENTITY_LINE = "You are the explorer; jrag is the map."


def _jrag_exe() -> str:
    """Locate the installed ``jrag`` entry point next to the venv interpreter."""
    candidate = Path(sys.executable).parent / "jrag"
    if candidate.is_file():
        return str(candidate)
    exe = shutil.which("jrag")
    assert exe is not None, "expected installed jrag entrypoint (run: pip install -e .)"
    return exe


def _run_jrag(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [_jrag_exe(), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=cwd,
        check=False,
    )


def _indexed_env(corpus_root: Path, ladybug_db_path: Path) -> dict[str, str]:
    """Env pointing ``jrag`` at the session bank-chat index."""
    env = os.environ.copy()
    env["JAVA_CODEBASE_RAG_SOURCE_ROOT"] = str(corpus_root)
    env["JAVA_CODEBASE_RAG_INDEX_DIR"] = str(ladybug_db_path.parent)
    return env


def _state_bullets(out: str) -> list[str]:
    """The three computed bullets under the ``**Index state**`` heading."""
    lines = out.splitlines()
    start = lines.index("**Index state**") + 1
    bullets: list[str] = []
    for line in lines[start:]:
        if line.startswith("- "):
            bullets.append(line)
        elif bullets or line.strip():
            break
    return bullets


# ----- Test 1: indexed repo -> full payload -----


def test_prime_prints_payload_on_indexed_repo(
    corpus_root: Path, ladybug_db_path: Path
) -> None:
    """`jrag prime` on a real index prints identity, command surface, and state."""
    proc = _run_jrag(["prime"], env=_indexed_env(corpus_root, ladybug_db_path))
    assert proc.returncode == 0, (
        f"prime failed: rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"
    )
    out = proc.stdout
    assert _IDENTITY_LINE in out
    assert "**Commands by group**" in out
    assert "`callers`" in out
    # Fresh: the session fixture just built the index, so no source file is
    # newer than built_at and the age is under the 90-minute bucket.
    assert re.search(r"^- Index fresh \(incremented \d+m ago\)", out, re.MULTILINE), out
    bullets = _state_bullets(out)
    assert len(bullets) == 3, f"expected the 3 state bullets, got: {bullets!r}"
    assert re.match(r"^- \d+ services \(", bullets[1]), bullets[1]
    assert re.match(r"^- \d+ routes · \d+ clients · \d+ producers$", bullets[2]), bullets[2]
    # Not a query envelope: prime never speaks the Envelope protocol.
    assert "status:" not in out


# ----- Test 2: silence rule -----


def test_prime_silent_without_index(tmp_path: Path) -> None:
    """No index -> empty stdout and rc 0 (never nags an unindexed repo)."""
    env = os.environ.copy()
    env["JAVA_CODEBASE_RAG_SOURCE_ROOT"] = str(tmp_path)
    env["JAVA_CODEBASE_RAG_INDEX_DIR"] = str(tmp_path / "no-index-here")
    proc = _run_jrag(["prime"], env=env, cwd=str(tmp_path))
    assert proc.returncode == 0, (
        f"rc={proc.returncode}\nstdout={proc.stdout!r}\nstderr={proc.stderr!r}"
    )
    assert proc.stdout == "", f"expected silent stdout, got: {proc.stdout!r}"


# ----- Test 3: --hook-json envelope -----


def test_prime_hook_json_envelope_valid(
    corpus_root: Path, ladybug_db_path: Path
) -> None:
    """`--hook-json` wraps the same payload in the SessionStart envelope."""
    proc = _run_jrag(["prime", "--hook-json"], env=_indexed_env(corpus_root, ladybug_db_path))
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    inner = doc["hookSpecificOutput"]
    assert inner["hookEventName"] == "SessionStart"
    assert _IDENTITY_LINE in inner["additionalContext"]
    # The envelope is one JSON document on stdout, nothing else around it.
    assert json.loads(proc.stdout.strip()) == doc


# ----- Test 4: staleness -----


def test_prime_reports_staleness(
    corpus_root: Path, ladybug_db_path: Path
) -> None:
    """A source file newer than built_at flips the payload to stale + count."""
    env = _indexed_env(corpus_root, ladybug_db_path)
    before = _run_jrag(["prime"], env=env)
    assert "Index fresh" in before.stdout

    # Tier-1 corpus is shared and checked in: touch an mtime only, and restore
    # it even on assertion failure so no future-dated mtime leaks past this
    # test (it would make every later freshness read report stale).
    target = sorted(corpus_root.rglob("*.java"))[0]
    stat = target.stat()
    future = time.time() + 3600.0
    os.utime(target, (future, future))
    try:
        after = _run_jrag(["prime"], env=env)
        assert after.returncode == 0, after.stderr
        assert "stale" in after.stdout
        assert "files changed" in after.stdout
        assert "stale — 1 files changed since last increment" in after.stdout
    finally:
        os.utime(target, (stat.st_atime, stat.st_mtime))


# ----- Test 5: import guard (in-process) -----


def test_prime_import_guard(
    corpus_root: Path,
    ladybug_db_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """The prime handler loads no vector-stack module the process didn't have.

    The session fixture chain itself pulls ``pyarrow`` (via the graph build
    passes), so the honest assertion is on the delta the handler introduces —
    which is exactly the property that matters: ``prime`` never *newly* loads
    torch/sentence_transformers/lancedb/pyarrow/cocoindex on the SessionStart
    path. ``test_prime_clean_process_loads_no_vector_stack`` pins the absolute
    form in a fresh interpreter.
    """
    from java_codebase_rag import jrag as jrag_mod

    before = {m for m in sys.modules if m.split(".")[0] in _HEAVY_DEPS}

    monkeypatch.setenv("JAVA_CODEBASE_RAG_SOURCE_ROOT", str(corpus_root))
    monkeypatch.setenv("JAVA_CODEBASE_RAG_INDEX_DIR", str(ladybug_db_path.parent))
    # ``_resolve_cfg`` -> ``apply_to_os_environ`` writes process env without
    # monkeypatch's knowledge; restore it so later tests in this process are
    # unaffected by SBERT_MODEL & friends.
    env_snapshot = dict(os.environ)
    try:
        parser = jrag_mod.build_parser()
        rc = jrag_mod._cmd_prime(parser.parse_args(["prime"]))
    finally:
        os.environ.clear()
        os.environ.update(env_snapshot)

    assert rc == 0
    assert _IDENTITY_LINE in capsys.readouterr().out

    after = {m for m in sys.modules if m.split(".")[0] in _HEAVY_DEPS}
    assert after == before, f"prime newly loaded vector stack: {sorted(after - before)}"


def test_prime_clean_process_loads_no_vector_stack(
    corpus_root: Path, ladybug_db_path: Path, tmp_path: Path
) -> None:
    """A fresh interpreter running ``main(["prime"])`` loads no vector stack.

    This is the latency contract as the hook actually experiences it: no
    torch/sentence_transformers/lancedb/pyarrow/cocoindex import (~2.5s and
    ~1GB) between SessionStart and the payload.
    """
    prog = (
        "import sys\n"
        "from java_codebase_rag.jrag import main\n"
        "rc = main(['prime'])\n"
        "pulled = sorted({m.split('.')[0] for m in sys.modules} "
        f"& {set(_HEAVY_DEPS)!r})\n"
        "print('RC', rc)\n"
        "print('PULLED', pulled)\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", prog],
        capture_output=True,
        text=True,
        env=_indexed_env(corpus_root, ladybug_db_path),
        cwd=str(tmp_path),
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "RC 0" in proc.stdout, proc.stdout
    assert "PULLED []" in proc.stdout, proc.stdout


# ----- Test 6: query-output flags are rejected -----


def test_prime_rejects_query_output_flags() -> None:
    """`jrag prime --count` is a usage error: prime has no per-row output flags.

    Mirrors ``test_offset_not_accepted_on_status_subcommand`` — prime uses
    ``_core_parser()``, not ``_common_parser()``, so ``--count``/``--exists``/
    ``--fields`` are rejected at parse time rather than accepted-then-ignored.
    """
    env = os.environ.copy()
    proc = _run_jrag(["prime", "--count"], env=env)
    assert proc.returncode != 0
    assert "Traceback" not in proc.stderr
    assert "--count" in proc.stderr or "unrecognized arguments" in proc.stderr.lower()
