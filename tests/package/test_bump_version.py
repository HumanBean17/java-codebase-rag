"""Tests for ``scripts/bump_version.py`` — lockstep version math + writer.

The bump script is the foundation of the tag-triggered release pipeline: a
later ``release.sh`` orchestrator calls ``--apply``, and the ``publish-pip``
skill's manual fallback calls it too. It owns the single invariant that keeps
the two PyPI names (``jrag-cli`` and ``java-codebase-rag``) in sync at the
source: the shim version is always derived from the root, never edited
independently.

These tests pin the two-mode CLI contract (``--check`` validates only;
``--apply`` validates then writes) and the strict-greater-than version math.
They build a minimal two-pyproject repo under ``tmp_path`` and run the script
with ``cwd=tmp_path`` (no ``.git``), which exercises the CWD fallback in the
repo-root resolver — the same path real releases hit when the script can't
``git rev-parse``.
"""
from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "bump_version.py"


def _write_repo(tmp_path: Path) -> None:
    """Build a minimal two-pyproject repo mirroring the real layout.

    Root pyproject is the single source of truth; the shim carries its own
    version + the ``jrag-cli==<ver>`` pin that must move in lockstep.
    """
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "jrag-cli"\nversion = "0.12.0"\n',
        encoding="utf-8",
    )
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    (shim_dir / "pyproject.toml").write_text(
        '[project]\nname = "java-codebase-rag"\n'
        'version = "0.12.0"\n'
        'dependencies = ["jrag-cli==0.12.0"]\n',
        encoding="utf-8",
    )


def _run(mode: str, version: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), f"--{mode}", version],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _load(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


# --- --check: version math -------------------------------------------------


def test_check_accepts_higher_patch(tmp_path: Path) -> None:
    """0.12.0 → 0.12.1 is a strict increase → exit 0."""
    _write_repo(tmp_path)
    result = _run("check", "0.12.1", tmp_path)
    assert result.returncode == 0, result.stderr


def test_check_accepts_higher_minor(tmp_path: Path) -> None:
    """0.12.0 → 0.13.0 is a strict increase → exit 0."""
    _write_repo(tmp_path)
    result = _run("check", "0.13.0", tmp_path)
    assert result.returncode == 0, result.stderr


def test_check_accepts_major(tmp_path: Path) -> None:
    """0.12.0 → 1.0.0 is a strict increase → exit 0."""
    _write_repo(tmp_path)
    result = _run("check", "1.0.0", tmp_path)
    assert result.returncode == 0, result.stderr


def test_check_rejects_equal(tmp_path: Path) -> None:
    """0.12.0 → 0.12.0 is not strictly greater → exit 1, naming the current."""
    _write_repo(tmp_path)
    result = _run("check", "0.12.0", tmp_path)
    assert result.returncode == 1
    assert "0.12.0" in result.stderr


def test_check_rejects_lower(tmp_path: Path) -> None:
    """0.12.0 → 0.11.9 is a decrease → exit 1."""
    _write_repo(tmp_path)
    result = _run("check", "0.11.9", tmp_path)
    assert result.returncode == 1


def test_check_rejects_malformed(tmp_path: Path) -> None:
    """``0.12`` does not match ``^\\d+\\.\\d+\\.\\d+$`` → exit 1."""
    _write_repo(tmp_path)
    result = _run("check", "0.12", tmp_path)
    assert result.returncode == 1


# --- --apply: lockstep writer ----------------------------------------------


def test_apply_writes_lockstep(tmp_path: Path) -> None:
    """``--apply 0.13.0`` moves root version, shim version, and shim pin together."""
    _write_repo(tmp_path)
    result = _run("apply", "0.13.0", tmp_path)
    assert result.returncode == 0, result.stderr

    root = _load(tmp_path / "pyproject.toml")
    shim = _load(tmp_path / "shim" / "pyproject.toml")
    assert root["project"]["version"] == "0.13.0"
    assert shim["project"]["version"] == "0.13.0"
    assert shim["project"]["dependencies"] == ["jrag-cli==0.13.0"]


def test_apply_no_write_on_invalid(tmp_path: Path) -> None:
    """Validation failure (target lower than current) → exit 1, root untouched."""
    _write_repo(tmp_path)
    result = _run("apply", "0.11.0", tmp_path)
    assert result.returncode == 1
    root = _load(tmp_path / "pyproject.toml")
    assert root["project"]["version"] == "0.12.0"


def _write_realistic_repo(tmp_path: Path) -> tuple[str, str]:
    """Build a realistic two-pyproject repo whose formatting a TOML writer would mangle.

    Unlike the minimal ``_write_repo``, this fixture carries content a
    canonicalizing TOML writer (``tomli_w``) round-trip would drop or reformat:
      - a ``[build-system]`` table before ``[project]`` (preamble + key order),
      - an inline comment (trailing the root version line; full-line in the shim),
      - a multi-line ``classifiers`` array in the root,
      - a ``[tool.*]`` sub-table in each.

    The version string ``0.12.0`` appears ONLY in the version line (root) and the
    version line + ``jrag-cli==`` pin (shim), so a precise in-memory swap of those
    tokens is a sound byte-exact oracle for "only the version value(s) changed".
    """
    root_text = (
        "[build-system]\n"
        'requires = ["setuptools>=61"]\n'
        'build-backend = "setuptools.build_meta"\n'
        "\n"
        "[project]\n"
        'name = "jrag-cli"\n'
        'version = "0.12.0"  # source of truth - bump in lockstep with shim\n'
        'description = "a description"\n'
        "classifiers = [\n"
        '    "Programming Language :: Python :: 3",\n'
        '    "Operating System :: OS Independent",\n'
        "]\n"
        "\n"
        "[project.scripts]\n"
        'jrag = "java_codebase_rag.cli:main"\n'
        "\n"
        "[tool.setuptools.packages.find]\n"
        'where = ["src"]\n'
    )
    (tmp_path / "pyproject.toml").write_text(root_text, encoding="utf-8")

    shim_text = (
        "[build-system]\n"
        'requires = ["setuptools>=61"]\n'
        'build-backend = "setuptools.build_meta"\n'
        "\n"
        "[project]\n"
        'name = "java-codebase-rag"\n'
        'version = "0.12.0"\n'
        "# metadata-only shim: pin moves in lockstep with the canonical dist\n"
        'dependencies = ["jrag-cli==0.12.0"]\n'
        "\n"
        "[tool.setuptools]\n"
        "py-modules = []\n"
    )
    shim_dir = tmp_path / "shim"
    shim_dir.mkdir()
    (shim_dir / "pyproject.toml").write_text(shim_text, encoding="utf-8")
    return root_text, shim_text


def test_apply_preserves_other_lines(tmp_path: Path) -> None:
    """Targeted replace: every byte except the version value(s) is preserved.

    The fixture (``_write_realistic_repo``) carries a ``[build-system]`` preamble,
    inline comments, and a multi-line ``classifiers`` array — content a
    canonicalizing TOML writer (``tomli_w``) round-trip would drop or reformat.
    The assertion compares the on-disk result to an in-memory swap of ONLY the
    version value(s), so any rewrite that touches a comment, key order, or array
    formatting fails here. This is the guard against a future regression to a
    TOML-writer rewrite; the minimal ``'name = ...' in read_text()`` check it
    replaced would have passed under such a rewrite.
    """
    root_before, shim_before = _write_realistic_repo(tmp_path)
    result = _run("apply", "0.13.0", tmp_path)
    assert result.returncode == 0, result.stderr

    root_after = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    shim_after = (tmp_path / "shim" / "pyproject.toml").read_text(encoding="utf-8")

    # Oracle: swap ONLY the version value(s) in the original text. Equality means
    # not a single other byte (comment, blank line, array indent, preamble,
    # sub-table) was perturbed — the targeted-replace contract holds.
    expected_root = root_before.replace('version = "0.12.0"', 'version = "0.13.0"')
    expected_shim = (
        shim_before
        .replace('version = "0.12.0"', 'version = "0.13.0"')
        .replace("jrag-cli==0.12.0", "jrag-cli==0.13.0")
    )
    assert root_after == expected_root, (
        "root pyproject bytes drifted beyond the version line — targeted-replace "
        "contract broken (a comment/preamble/multi-line array would be lost or "
        "reformatted under tomli_w)"
    )
    assert shim_after == expected_shim, (
        "shim pyproject bytes drifted beyond the version line + dep pin — "
        "targeted-replace contract broken (the inline comment would be dropped "
        "under tomli_w)"
    )
