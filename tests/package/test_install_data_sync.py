"""Tests for agent artifacts sync script.

Skill/agent consumer artifacts were removed (the CLI surface ships a
``jrag prime`` SessionStart hook, the MCP surface a server entry — neither
deploys files). ``SYNC_MAP`` is empty and the script is now an absence
guard, so these tests pin that contract:

- ``--check`` is green at HEAD
- a file reintroduced on either side (dev tree or install_data) fails it
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path



# Paths relative to repo root
SYNC_SCRIPT = Path("scripts/sync_agent_artifacts.py")


def run_sync_script(*, check: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run the sync script and return the result.

    Args:
        check: Pass --check flag (verify only, no writes)
        cwd: Working directory (defaults to repo root if None)

    Returns:
        CompletedProcess with stdout/stderr captured as text.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    if cwd is None:
        cwd = repo_root

    cmd = [sys.executable, str(repo_root / SYNC_SCRIPT)]
    if check:
        cmd.append("--check")

    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",  # Script emits UTF-8 (✓ marker); decode as such, not the locale ANSI codepage (cp1252 on Windows).
    )


def test_install_data_artifacts_in_sync_with_dev_source():
    """Baseline: --check passes at HEAD (no artifacts shipped on either side)."""
    result = run_sync_script(check=True)

    assert result.returncode == 0, (
        f"Sync check failed - artifacts out of sync.\n"
        f"stdout: {result.stdout}\n"
        f"stderr: {result.stderr}"
    )

    assert "✓ All agent artifacts in sync" in result.stdout, (
        f"Expected success message not found in stdout.\n"
        f"stdout: {result.stdout}"
    )


# One guarded directory per side of the old sync: the dev source tree and its
# install_data mirror. A reintroduced artifact must fail from either one.
_STRAY_CASES = [
    ("dev tree", Path("skills") / "explore-codebase" / "SKILL.md"),
    ("install_data", Path("src/java_codebase_rag/install_data/agents/explorer-rag-enhanced.md")),
]


def test_sync_script_flags_reintroduced_artifact():
    """Verify --check exits non-zero when an artifact reappears.

    Seeds a stray file into a fresh temp workspace (one case per guarded
    directory) and runs the script with ``cwd`` pointed there, so the repo
    is never mutated.
    """
    for label, stray_rel in _STRAY_CASES:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            stray = tmp_path / stray_rel
            stray.parent.mkdir(parents=True, exist_ok=True)
            stray.write_text("# this should not be here")

            result = run_sync_script(check=True, cwd=tmp_path)

            assert result.returncode == 1, (
                f"[{label}] Expected --check to exit non-zero on a stray artifact, "
                f"but got {result.returncode}.\n"
                f"stdout: {result.stdout}\n"
                f"stderr: {result.stderr}"
            )

            output = result.stdout + result.stderr
            assert "extra file" in output.lower(), (
                f"[{label}] Expected script to report the stray artifact.\n"
                f"output: {output}"
            )


def test_sync_script_green_when_guarded_dirs_absent():
    """An empty workspace (no guarded dirs at all) is a pass, not an error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_sync_script(check=True, cwd=Path(tmpdir))

        assert result.returncode == 0, (
            f"Expected --check to pass on an empty workspace.\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}"
        )
        assert "✓ All agent artifacts in sync" in result.stdout
