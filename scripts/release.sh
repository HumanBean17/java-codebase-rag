#!/usr/bin/env bash
# release.sh — the human-half bump+tag orchestrator for the dual-PyPI release.
#
# Bumps root + shim pyprojects in lockstep (via bump_version.py), runs the
# install-artifact sync gate, commits "bump version to <X.Y.Z>", lays an
# annotated tag v<X.Y.Z>, and pushes both to origin. A CI workflow (built in a
# later task) picks up the tag and publishes both PyPI names (jrag-cli +
# java-codebase-rag). This script does NOT build or upload anything.
#
# Usage: release.sh <X.Y.Z> [--dry-run] [--no-push] [--skip-sync-check]
#
# Every failure prints "ERROR: <reason>" to stderr and exits 1.
set -euo pipefail

err() { echo "ERROR: $*" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# --- arg parse (small flag set, by hand) ---
VERSION=""
DRY_RUN=0
NO_PUSH=0
SKIP_SYNC=0
for arg in "$@"; do
    case "$arg" in
        --dry-run)         DRY_RUN=1 ;;
        --no-push)         NO_PUSH=1 ;;
        --skip-sync-check) SKIP_SYNC=1 ;;
        -*)                err "unknown flag: $arg" ;;
        *)  [[ -n "$VERSION" ]] && err "unexpected extra argument: $arg"
            VERSION="$arg" ;;
    esac
done
[[ -n "$VERSION" ]] || err "usage: $0 <X.Y.Z> [--dry-run] [--no-push] [--skip-sync-check]"

# --- precondition 1: inside a git worktree (also gives the repo root) ---
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || err "not inside a git worktree"

# Python: prefer the repo venv, else python3 on PATH.
if [[ -x "$ROOT/.venv/bin/python" ]]; then PY="$ROOT/.venv/bin/python"; else PY="python3"; fi

# --- precondition 2: working tree clean ---
[[ -z "$(git -C "$ROOT" status --porcelain)" ]] \
    || err "working tree is dirty — clean it (commit or stash) before releasing"

# --- precondition 3: version well-formed ---
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || err "version '$VERSION' is not well-formed (expected X.Y.Z)"

# --- version validation: bump_version.py owns the strict-greater-than math ---
"$PY" "$SCRIPT_DIR/bump_version.py" --check "$VERSION" >/dev/null \
    || err "bump_version.py rejected '$VERSION' (must be strictly greater than the current root version)"

# --- sync gate: the install-artifact drift check (skipped with --skip-sync-check) ---
if [[ "$SKIP_SYNC" -eq 0 ]]; then
    "$PY" "$SCRIPT_DIR/sync_agent_artifacts.py" --check >/dev/null \
        || err "agent artifacts out of sync — run: python scripts/sync_agent_artifacts.py, commit, and retry"
fi

# --- dry-run: print the plan and stop. No mutation, no commit, no tag, no push. ---
if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "dry-run plan (no changes will be made):"
    echo "  target version: $VERSION"
    echo "  commit subject: bump version to $VERSION"
    echo "  tag:            v$VERSION"
    exit 0
fi

# --- apply: bump (lockstep), stage the two pyprojects, commit, tag (annotated). ---
"$PY" "$SCRIPT_DIR/bump_version.py" --apply "$VERSION" >/dev/null \
    || err "bump_version.py --apply failed"
git -C "$ROOT" add pyproject.toml shim/pyproject.toml
git -C "$ROOT" commit -m "bump version to $VERSION" >/dev/null \
    || err "git commit failed"
git -C "$ROOT" tag -a "v$VERSION" -m "Release $VERSION" \
    || err "git tag failed"

# --- push: ship commit + tag together (atomic unless --no-push). ---
if [[ "$NO_PUSH" -eq 0 ]]; then
    git -C "$ROOT" push --atomic origin HEAD "v$VERSION" \
        || err "git push failed (commit + tag v$VERSION)"
fi

echo "release $VERSION: committed 'bump version to $VERSION' and tagged v$VERSION."
if [[ "$NO_PUSH" -eq 1 ]]; then
    # NOTE: a trailing ``[[ ]] && echo`` here would leak exit 1 on the success
    # path (the test is false when --no-push is absent), making a fully-successful
    # release exit nonzero. Use a real ``if`` so success always exits 0.
    echo "(--no-push: not pushed; run 'git push --atomic origin HEAD v$VERSION' to ship)"
fi
