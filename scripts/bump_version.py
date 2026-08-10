#!/usr/bin/env python3
"""Lockstep version bump for the jrag dual-PyPI release.

This script is the foundation of the tag-triggered release pipeline: a later
``release.sh`` orchestrator calls ``--apply``, and the ``publish-pip`` skill's
manual fallback calls it too. It owns the single invariant that keeps the two
PyPI names (``jrag-cli`` and ``java-codebase-rag``) in sync at the source —
the shim version is always derived from the root, never edited independently.

Two modes:
  --check <X.Y.Z>   validate only (no writes). Exit 0 if the target is
                    well-formed (``^\\d+\\.\\d+\\.\\d+$``) and strictly greater
                    than the current root version; exit 1 otherwise.
  --apply <X.Y.Z>   run the same validation first, then write the new version
                    into root ``pyproject.toml`` (the ``version = "..."`` line
                    under ``[project]``) and ``shim/pyproject.toml`` (both the
                    ``version = "..."`` line and the ``jrag-cli==<ver>`` pin in
                    ``dependencies``). No file is written on validation
                    failure.

Repo-root resolution: prefer ``git rev-parse --show-toplevel``; if that fails
(not a git repo, as in unit tests), fall back to CWD. Plain ``X.Y.Z`` numeric
versions only — no pre-release suffixes, epochs, or non-numeric versions.

Exit codes:
    0: target accepted (and, for ``--apply``, written in lockstep)
    1: target rejected as malformed or not strictly greater than current
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from pathlib import Path

# Plain X.Y.Z — no pre-release tags, epochs, or non-numeric versions, ever.
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
# Matches a ``version = "..."`` line, scoped to the [project] section by the
# line-walk in ``_replace_project_version``. The closing-quote tail captures
# any trailing comment and the optional newline so the replacement is a
# targeted value swap, not a full-rewrite.
_VERSION_LINE_RE = re.compile(r'^(\s*version\s*=\s*")([^"]*)("[^\n]*\n?)$')
# The shim's sole runtime dep pin — ``jrag-cli==`` appears nowhere else.
_PIN_RE = re.compile(r"jrag-cli==\d+\.\d+\.\d+")


def repo_root() -> Path:
    """Resolve the repo root: prefer ``git rev-parse``, fall back to CWD.

    The CWD fallback exists so the script works outside a git checkout —
    notably in unit tests, which run with ``cwd=tmp_path`` and no ``.git``.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
        )
        top = out.stdout.strip()
        if top:
            return Path(top)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        pass
    return Path.cwd()


def read_root_version(root_pyproject: Path) -> str:
    """Return ``[project].version`` from the root pyproject (single source of truth)."""
    with root_pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    return data["project"]["version"]


def parse_version(s: str) -> tuple[int, int, int]:
    """Split a validated ``X.Y.Z`` string into an ``(int, int, int)`` tuple."""
    major, minor, patch = s.split(".")
    return (int(major), int(minor), int(patch))


def validate(target: str, current: str) -> str | None:
    """Return an error message if ``target`` is invalid, else None.

    ``target`` must match ``^\\d+\\.\\d+\\.\\d+$`` and compare strictly greater
    than ``current`` (as an ``(int, int, int)`` tuple). Equal or lower is
    rejected — a release must move strictly forward.
    """
    if not VERSION_RE.match(target):
        return f"target version {target!r} is not well-formed (expected X.Y.Z)"
    if parse_version(target) <= parse_version(current):
        return (
            f"target version {target!r} is not strictly greater than "
            f"current version {current!r}"
        )
    return None


def _replace_project_version(text: str, new_version: str) -> str:
    """Replace the ``version = "..."`` line under ``[project]`` only.

    Walks the file line-by-line so a ``version`` key in some other section
    (e.g. ``[tool.setuptools.dynamic]``) is left untouched. Only the value
    between the quotes is swapped; every other byte — comments, formatting,
    blank lines — is preserved verbatim.
    """
    lines = text.splitlines(keepends=True)
    in_project = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_project = stripped == "[project]"
            continue
        if in_project:
            m = _VERSION_LINE_RE.match(line)
            if m:
                lines[i] = f"{m.group(1)}{new_version}{m.group(3)}"
                break  # [project] has exactly one version key
    return "".join(lines)


def _replace_jrag_cli_pin(text: str, new_version: str) -> str:
    """Rewrite the ``jrag-cli==<ver>`` dependency pin to ``new_version``."""
    return _PIN_RE.sub(f"jrag-cli=={new_version}", text)


def write_lockstep(root_pyproject: Path, shim_pyproject: Path, new_version: str) -> None:
    """Bump root version + shim version + shim dep pin together (no round-trip)."""
    root_pyproject.write_text(
        _replace_project_version(root_pyproject.read_text(encoding="utf-8"), new_version),
        encoding="utf-8",
    )
    shim_text = shim_pyproject.read_text(encoding="utf-8")
    shim_text = _replace_project_version(shim_text, new_version)
    shim_text = _replace_jrag_cli_pin(shim_text, new_version)
    shim_pyproject.write_text(shim_text, encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--check", action="store_true", help="validate only; write nothing"
    )
    mode.add_argument(
        "--apply", action="store_true", help="validate, then write both pyprojects"
    )
    ap.add_argument("version", help="target version X.Y.Z")
    args = ap.parse_args()

    root_pyproject = repo_root() / "pyproject.toml"
    shim_pyproject = repo_root() / "shim" / "pyproject.toml"

    try:
        current = read_root_version(root_pyproject)
    except (OSError, KeyError, ValueError) as exc:
        print(f"cannot read current version from {root_pyproject}: {exc}", file=sys.stderr)
        return 1

    err = validate(args.version, current)
    if err is not None:
        print(err, file=sys.stderr)
        return 1

    if args.check:
        print(f"OK: {args.version} > {current}")
        return 0

    try:
        write_lockstep(root_pyproject, shim_pyproject, args.version)
    except OSError as exc:
        print(f"write failed: {exc}", file=sys.stderr)
        return 1
    print(f"bumped {current} -> {args.version} (root + shim in lockstep)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
