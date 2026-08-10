"""Tests for ``scripts/release.sh`` — the human-half bump+tag orchestrator.

``release.sh`` is the maintainer-facing entry point of the tag-triggered
release: it bumps root + shim pyprojects in lockstep (via ``bump_version.py``),
runs the install-artifact sync gate, commits ``bump version to <X.Y.Z>``, and
pushes an annotated tag ``v<X.Y.Z>``. A CI workflow (built later) picks up the
tag and publishes both PyPI names; this script itself builds/uploads nothing.

Two execution contexts, mirroring the brief:
  - **Real repo, ``--dry-run`` (no mutation):** exercises the full chain
    (preconditions → version math → sync gate → plan print) against the live
    repo at ``REPO_ROOT``. The real repo is in sync, so the sync gate passes
    and the dry-run reaches the plan-print. Asserts the working tree is still
    clean afterward (dry-run must mutate nothing).
  - **Temp repo (commit/tag + dirty-tree mechanics):** a minimal two-pyproject
    git repo under ``tmp_path``. The sync gate is skipped here (a minimal repo
    has no agent artifacts, so the gate would fail closed — the apply test in
    the brief already establishes ``--skip-sync-check`` as the temp-repo
    pattern); these tests isolate the commit/tag/dirty-tree behavior.

Tests invoke ``bash`` explicitly (do not rely on the +x bit).
``RELEASE_SH = REPO_ROOT / "scripts" / "release.sh"``.
"""
from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RELEASE_SH = REPO_ROOT / "scripts" / "release.sh"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run release.sh via bash (explicit — no reliance on the +x bit)."""
    return subprocess.run(
        ["bash", str(RELEASE_SH), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _root_version(repo: Path) -> str:
    with (repo / "pyproject.toml").open("rb") as fh:
        return tomllib.load(fh)["project"]["version"]


def _next_patch(version: str) -> str:
    """``0.12.0`` → ``0.12.1`` (dynamic, so the test survives future bumps)."""
    major, minor, patch = (int(x) for x in version.split("."))
    return f"{major}.{minor}.{patch + 1}"


def _git(repo: Path, *args: str) -> str:
    """Run a git command in ``repo`` and return stdout (str)."""
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        encoding="utf-8",
    ).stdout


def _init_temp_repo(root: Path) -> Path:
    """Build a minimal two-pyproject git repo at ``root``.

    Mirrors the real dual-dist layout at the minimum needed for the bump+tag
    mechanics: root ``pyproject.toml`` (single source of truth) and the shim
    with its ``jrag-cli==<ver>`` pin. Committed as the initial commit so the
    tree starts clean and ``git rev-parse --show-toplevel`` resolves. Accepts
    either the pytest ``tmp_path`` or a subdirectory (created if needed).
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "pyproject.toml").write_text(
        '[project]\nname = "jrag-cli"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    (root / "shim").mkdir()
    (root / "shim" / "pyproject.toml").write_text(
        '[project]\nname = "java-codebase-rag"\n'
        'version = "0.1.0"\n'
        'dependencies = ["jrag-cli==0.1.0"]\n',
        encoding="utf-8",
    )
    _git(root, "init")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "T")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "init")
    return root


# --- Real repo, --dry-run (no mutation) ------------------------------------


def test_dry_run_next_version_passes() -> None:
    """Dry-run with current+patch prints the plan and mutates nothing.

    Exercises the full chain on the live repo: clean-tree precondition, version
    math (next patch > current), the real (in-sync) sync gate, then the plan
    print. The tree must be clean before and after — dry-run writes nothing.
    """
    before = _git(REPO_ROOT, "status", "--porcelain")
    assert before == "", "real repo must start clean for this test"

    current = _root_version(REPO_ROOT)
    next_ver = _next_patch(current)
    result = _run([next_ver, "--dry-run"], REPO_ROOT)

    assert result.returncode == 0, result.stderr
    assert f"bump version to {next_ver}" in result.stdout, result.stdout
    assert f"v{next_ver}" in result.stdout, result.stdout
    # No mutation: tree still clean.
    assert _git(REPO_ROOT, "status", "--porcelain") == ""


def test_dry_run_lower_version_refused() -> None:
    """A target lower than current is rejected by bump_version.py's math.

    The check runs before the sync gate and fails closed; stderr names the
    monotonic constraint. The tree must be unchanged (no commit/tag created).
    """
    assert _git(REPO_ROOT, "status", "--porcelain") == ""
    result = _run(["0.0.1", "--dry-run"], REPO_ROOT)

    assert result.returncode != 0
    assert "current version" in result.stderr.lower() or "monotonic" in result.stderr.lower(), result.stderr
    assert _git(REPO_ROOT, "status", "--porcelain") == ""
    # No tag created.
    assert "v0.0.1" not in _git(REPO_ROOT, "tag", "-l")


# --- Temp repo: commit/tag + dirty-tree mechanics --------------------------


def test_apply_commits_and_tags_lockstep(tmp_path: Path) -> None:
    """Apply (no push) bumps both pyprojects, commits, and lays an annotated tag.

    Asserts the three invariants a correct release must leave behind:
      (1) a ``bump version to 0.2.0`` commit exists;
      (2) exactly one tag ``v0.2.0`` and it is annotated (``cat-file -t`` → tag);
      (3) root + shim versions and the shim dep pin all equal ``0.2.0`` (lockstep).
    """
    repo = _init_temp_repo(tmp_path)
    result = _run(["0.2.0", "--no-push", "--skip-sync-check"], repo)

    assert result.returncode == 0, result.stderr
    log = _git(repo, "log", "--oneline")
    assert "bump version to 0.2.0" in log, log
    tags = _git(repo, "tag", "-l").split()
    assert tags == ["v0.2.0"], tags
    assert _git(repo, "cat-file", "-t", "v0.2.0").strip() == "tag"

    with (repo / "pyproject.toml").open("rb") as fh:
        root = tomllib.load(fh)
    with (repo / "shim" / "pyproject.toml").open("rb") as fh:
        shim = tomllib.load(fh)
    assert root["project"]["version"] == "0.2.0"
    assert shim["project"]["version"] == "0.2.0"
    assert shim["project"]["dependencies"] == ["jrag-cli==0.2.0"]


def test_dry_run_refuses_dirty_tree(tmp_path: Path) -> None:
    """A dirty working tree is rejected at the precondition, before any work.

    The clean-tree check fires before version math and the sync gate, so no
    bump commit or tag is created even though the target version is valid.
    """
    repo = _init_temp_repo(tmp_path)
    (repo / "pyproject.toml").write_text("x\n", encoding="utf-8")  # dirty the tree

    result = _run(["0.2.0", "--dry-run"], repo)

    assert result.returncode != 0
    assert "dirty" in result.stderr.lower() or "clean" in result.stderr.lower(), result.stderr
    # No bump commit / tag created — only the init commit remains.
    assert "bump version to 0.2.0" not in _git(repo, "log", "--oneline")
    assert _git(repo, "tag", "-l").split() == []


def test_apply_pushes_commit_and_tag(tmp_path: Path) -> None:
    """Apply WITH push exits 0 and ships both the commit and the tag to origin.

    Regression guard: a trailing ``[[ ]] && echo`` at the script's tail leaked
    exit 1 on the success path when ``--no-push`` was absent (the brief's apply
    test used ``--no-push``, so the matrix missed it). Sets up a local bare
    ``origin`` and asserts:
      (1) exit 0 on full success (the bug's symptom was exit 1);
      (2) both the ``bump version to 0.2.0`` commit and the ``v0.2.0`` tag land
          on origin (the ``--atomic`` push ties them).
    """
    repo = _init_temp_repo(tmp_path / "work")
    # Give the repo a real upstream: a local bare "origin" that receives the push.
    # Placed OUTSIDE the work repo (a sibling), else git status would see it as
    # untracked content and the clean-tree precondition would fire.
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "--bare", str(origin))
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "origin", "HEAD")  # seed origin with the init commit

    result = _run(["0.2.0", "--skip-sync-check"], repo)  # no --no-push

    assert result.returncode == 0, result.stderr
    # Origin received both the bump commit and the annotated tag.
    assert "bump version to 0.2.0" in _git(origin, "log", "--oneline")
    assert "v0.2.0" in _git(origin, "tag", "-l")


def test_dry_run_no_mutation(tmp_path: Path) -> None:
    """Dry-run on a clean temp repo leaves the commit history and tags untouched.

    The sync gate is skipped (minimal temp repo has no agent artifacts; the
    apply test in the same brief establishes ``--skip-sync-check`` for the
    temp-repo context). Asserts the log still holds only the init commit and
    no tag was created.
    """
    repo = _init_temp_repo(tmp_path)
    log_before = _git(repo, "log", "--oneline")

    result = _run(["0.2.0", "--dry-run", "--skip-sync-check"], repo)

    assert result.returncode == 0, result.stderr
    assert _git(repo, "log", "--oneline") == log_before
    assert _git(repo, "tag", "-l").split() == []
