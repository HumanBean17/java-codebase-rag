# Tag-triggered CI release pipeline (dual PyPI publish + release notes)

- **Date:** 2026-08-10
- **Status:** draft

## Motivation

A public-launch milestone is approaching: declaring `jrag` public/stable on 0.x
(no 1.0 API-freeze commitment) alongside an announce event. The release pipeline
is not ready for that spotlight:

- **Zero git tags.** The `publish-pip` skill explicitly states "no git tag."
  There is no recoverable pointer to "what code shipped as 0.11.2" — history is
  reconstructable only from `git log` and PyPI project pages.
- **No changelog / release notes** anywhere in the repo. Users have no
  curated "what changed" surface.
- **Fully manual publish** from a worktree, including a fragile `sed`
  name-swap to dual-publish the legacy `java-codebase-rag` name.
- **The publish runbook is stale relative to the codebase.** `shim/pyproject.toml`
  (added in PR #453) is a clean metadata-only package — `name =
  "java-codebase-rag"`, `dependencies = ["jrag-cli==<ver>"]`, `py-modules = []`
  — pinned in shape and version-lockstep by `tests/package/test_shim_package.py`.
  Dual-publish via the shim is one root build + one shim build, no name-swap.
  But the `publish-pip` skill still documents the old `sed` rebuild, which ships
  a *full* second package (the 486 KB artifact currently on PyPI for 0.12.0). The
  shim mechanism has never been used for a real release.
- **Duplicated shim version.** `shim/pyproject.toml` hardcodes the version twice
  (its own `version` and the `jrag-cli==<ver>` dep pin). The lockstep tests
  catch drift but do not prevent it; a bump that forgets the shim is a live
  hazard.

The pieces to fix this mostly already exist: the `shim`, the lockstep tests,
`scripts/check_dist_version.py` (pre-upload guard, already covering both dist
names), `scripts/sync_agent_artifacts.py` (install-data sync gate), and a
conventional-ish commit history (`feat(...)`, `fix(...)`, `docs:`). This spec
wires them into a tag-triggered CI release rather than reinventing them.

## Goal & scope

**Goal.** A maintainer cuts a release by running one script that bumps, commits,
and pushes an annotated tag; CI then builds the canonical `jrag-cli` dist and the
`java-codebase-rag` shim, publishes both to PyPI under the same version with no
stored secret, and opens a GitHub Release with auto-generated notes. The two
PyPI names are guaranteed in sync, and every release is recoverable from its
git tag.

**In scope.** The maintainer-facing release script; the tag-triggered CI
workflow; OIDC Trusted Publishing wiring; GitHub-Release-as-changelog notes
config; retirement of the stale `sed` name-swap in the `publish-pip` skill;
shim-version handling on bump; tests for the release path.

**Out of scope.** Public-readiness *presentation* (no `CONTRIBUTING.md`,
`SECURITY.md`, issue templates, Dev-Status classifier bump, or README revamp);
a 1.0 / API-stability commitment; a committed `CHANGELOG.md` (GitHub Releases
is the changelog); backfilling historical tags (`v0.9.6`→`v0.12.0`);
automatic version bumping from commits (semantic-release / commitizen);
automated `pip install -U` upgrade testing.

## Decisions

1. **The annotated tag `vX.Y.Z` is both the trigger and the release pointer.**
   It is the one thing a maintainer produces to ship a release, and it is the
   durable, recoverable answer to "what code was 0.13.0."
2. **Manual bump + manual tag → CI publishes.** The maintainer chooses the
   version number and timing; CI does the mechanical, error-prone work. No
   semantic-release auto-versioning.
3. **The shim is the dual-publish mechanism.** The `sed` name-swap is retired.
   CI builds the root dist (`jrag-cli`) and the shim dist
   (`java-codebase-rag`) separately — two clean builds, no in-place `pyproject`
   mutation.
4. **OIDC Trusted Publishing, no stored token for routine releases.** The
   `~/.pypirc` token is demoted to the manual-fallback credential only.
5. **GitHub Releases is the changelog.** Auto-generated, conventional-commit
   categorized notes; no separate `CHANGELOG.md` to maintain.
6. **Sync is a hard invariant, enforced four ways:** lockstep bump at the
   source (script updates both pyprojects), fixed publish order (`jrag-cli`
   then shim), required both-names verification, and **idempotent retry** that
   heals any partial failure to the both-at-`X.Y.Z` terminal state.
7. **`release.sh` owns the version bump.** `shim/pyproject.toml` becomes a
   generated artifact of the script, not a hand-edited file; the lockstep tests
   stay as the safety net.

## Release flow

Two halves joined by the tag.

**Human half — `scripts/release.sh X.Y.Z`** (the only command a maintainer runs):

1. Precondition checks: working tree clean; `X.Y.Z` strictly greater than the
   current `pyproject.toml` version; the script refuses otherwise.
2. Bumps the version in **two** files in lockstep — root `pyproject.toml` and
   `shim/pyproject.toml` (both its own `version` *and* the `jrag-cli==X.Y.Z`
   dep pin). The shim version is derived from the root, never accepted as
   independent input.
3. Runs `scripts/sync_agent_artifacts.py --check`; aborts on mismatch (run the
   syncer without `--check`, commit, and re-run if so).
4. Commits with the existing convention (`bump version to X.Y.Z`) and pushes an
   **annotated** tag `vX.Y.Z`.

It does **not** build, upload, or create the GitHub Release — that is CI's job.

**CI half — `.github/workflows/release.yml` (triggers on tag pattern `v*`):**

5. Checks out the tag; sets up Python 3.11; installs `build` and `twine`.
6. Builds the root dist → `jrag-cli` artifacts; builds the shim dist →
   `java-codebase-rag` artifacts (built from `shim/pyproject.toml`).
7. Runs `scripts/check_dist_version.py` against **each** dist name — hard stop
   before any upload (existing guard, now applied to both).
8. Publishes both to PyPI via Trusted Publishing (OIDC), `jrag-cli` first, then
   the shim. Each upload is preceded by an idempotency check (see Sync).
9. Verifies both names report `X.Y.Z` via the PyPI JSON API. The job is not
   green unless both match.
10. Creates a GitHub Release pinned to the tag, body auto-generated and
    categorized by `.github/release.yml`.

## Components

**(a) `scripts/release.sh X.Y.Z`.** Bash, repo-root, venv-aware. Contract per
the human half above. Fails closed on every unmet precondition. Exposes a
`--dry-run` mode that performs the bump on a *copy* (or in memory) and asserts
the lockstep and monotonic checks **without** committing, tagging, or pushing —
this is what the test suite exercises.

**(b) `.github/workflows/release.yml`.** Triggers on tag `v*` only; runs on
`ubuntu-latest`. Declares `permissions: { id-token: write, contents: write }`
and publishes under `environment: release`. Publish uses the canonical
`pypa/gh-action-pypi-publish` action (OIDC-native), invoked twice — once with
the `jrag-cli` dist files, once with the shim dist files, in that order. The
dual publish is two ordered build → guard → (idempotency-check) → upload blocks
sharing one Python toolchain setup. Post-upload verification and Release
creation follow.

**(c) `.github/release.yml` — release-notes config** *(GitHub's native notes
categorizer — a different file sharing the basename; lives at the repo `.github/`
root, not under `workflows/`).* Maps conventional-commit / PR-title prefixes to
sections (`feat → Features`, `fix → Bug Fixes`, `perf → Performance`,
`docs → Documentation`) with an ignore list that suppresses noise (`chore`,
`bump version to …`). This is the only thing that makes the GitHub Release body
read as a changelog with zero manual curation.

**(d) `shim/pyproject.toml`.** Now a generated artifact of `release.sh`. Its
version and dep pin change only via the script; hand-edits are not the supported
path. `tests/package/test_shim_package.py` continues to pin shape and lockstep.

**(e) `publish-pip` skill (`.claude/skills/publish-pip/SKILL.md`).** Rewritten:
the **primary** section becomes "tag → CI publishes both names" (one paragraph +
the `release.sh X.Y.Z` command + the out-of-repo Trusted-Publisher prerequisite).
The existing manual build/twine/guard runbook is **retained but corrected** —
rebuilt around the **shim** (not the `sed` name-swap) and reframed as the
"CI is down / PyPI reconciliation" fallback. The dual-publish policy and the
"both names must report the same version" close-out remain prominent. The
`0.10.0` artifact-leak lesson and the `find`-based cleanup / `check_dist_version`
guard stay — they still defend the manual fallback.

## Authentication — Trusted Publishing (OIDC)

No stored token for routine releases. The target PyPI project is determined by
the package being uploaded (its wheel METADATA `Name`); PyPI authorizes the
upload by checking whether *this workflow* is a registered trusted publisher for
*that project*. One workflow therefore publishes to both names, but each PyPI
project must be configured separately.

**One-time, out-of-repo maintainer TODO on pypi.org (for BOTH `jrag-cli` and
`java-codebase-rag`):**

- Add a Trusted Publisher (OIDC): PyPI project → Manage → "Add publisher":
  repository `HumanBean17/jrag`, workflow filename `release.yml`, environment
  name `release`.
- Workflow name and environment must match the in-repo workflow exactly.

**In-repo:** the workflow's `id-token: write` permission, `environment: release`,
and the `pypa/gh-action-pypi-publish` action's default trusted-publishing mode
constitute the OIDC exchange. No `PYPI_TOKEN` / `TWINE_PASSWORD` secret is set.

**Optional blast-radius gate (recommended for the first 2–3 launches):**
GitHub's `release` environment may require manual reviewer approval before the
publish job runs — a second confirmation ahead of permanent uploads, on top of
the deliberate tag-push. Relax it once the flow has shipped cleanly a few times.

The `~/.pypirc` token is retained solely for the manual-fallback runbook.

## Sync guarantee & idempotency

`jrag-cli` and `java-codebase-rag` must report the same version on PyPI after
every release. PyPI has no atomic two-project upload (two independent permanent
uploads), so the design makes divergence unreachable at the source and
self-healing on retry:

- **Unreachable at source:** `release.sh` bumps both pyprojects in one commit;
  `test_shim_package.py` lockstep tests fail CI if they drift.
- **Fixed order:** `jrag-cli` ships before the shim, so `pip install
  java-codebase-rag` never transiently fails to resolve `jrag-cli==X.Y.Z`.
- **Idempotent retry (the crux):** before each upload, the workflow queries the
  PyPI JSON API for that project's current version; if it already equals
  `X.Y.Z`, the upload for that name is **skipped** and the flow proceeds.
  Re-uploads always 400 on PyPI, so "already there" must be treated as success.
  This is what makes a partial failure converge: a re-run completes only the
  missing half.
- **Required verification:** the job is not green until *both* names report
  `X.Y.Z`.

## Failure modes & recovery

| Scenario | Outcome |
|---|---|
| Tag pushed but version unchanged / not increasing | `release.sh` refuses (monotonic check). A stale tag that slips through hits the PyPI-already-there idempotency path → safe skip. |
| Someone hand-edits `shim/pyproject.toml` | `test_shim_package.py` lockstep test fails in the `test` workflow before any tag; `release.sh` re-derives from root regardless. |
| `sync_agent_artifacts.py --check` mismatch | `release.sh` aborts before commit/tag. |
| Build fails | No upload; re-run the workflow on the existing tag. Nothing to clean. |
| `jrag-cli` uploads, shim fails (partial) | Job red on both-names verification. Re-run heals: skips `jrag-cli`, rebuilds + uploads the shim, verification passes. |
| Version exists on one name, not the other (stranding) | Same idempotent skip-then-complete — the scenario dual-publish exists to prevent. |
| GitHub Release step fails after both uploads | PyPI correct; maintainer re-runs (publish steps skip) or creates the Release from the tag in one click. |
| Persistent shim-upload failure | Maintainer follows the corrected `publish-pip` fallback (shim-based) to publish the legacy name manually. **Never leave the two names diverged.** |

## Tests

- **Existing guards retained and applied to both names:** `test_shim_package.py`
  (shape + version lockstep) and `test_check_dist_version.py` (guard accepts the
  matching prefix and rejects a foreign/unknown artifact for **both**
  `jrag-cli` and `java_codebase_rag`).
- **New — `release.sh --dry-run` exercised in the `test` workflow.** Asserts it
  bumps root and shim in lockstep, that the shim dep pin tracks the root
  version, and that it **refuses** a non-increasing version and a dirty tree —
  with no commit, tag, or push.
- **New — idempotency logic unit-tested** with a stubbed PyPI JSON response:
  "already at `X.Y.Z`" → skip; "behind" → publish. (The logic only; no real
  PyPI call in CI.)
- **Explicit boundary — no real PyPI publish in tests.** Permanent uploads are
  not exercisable in CI; the actual publish is validated only on the first real
  tag after merge. The "both names report `X.Y.Z`" checklist (mirrored from the
  current skill) is the human acceptance gate for that first release.
- Per `CLAUDE.md`: erase stale `tests/*/.java-codebase-rag*` before running;
  tests build their own state in temp dirs.

## Files touched (design-level)

- `scripts/release.sh` — new; the human half (bump root + shim, sync check,
  commit, annotated tag).
- `.github/workflows/release.yml` — new; tag-triggered CI publish (root + shim,
  guard both, OIDC dual publish, verify both, GitHub Release).
- `.github/release.yml` — new; GitHub release-notes categorization config.
- `.claude/skills/publish-pip/SKILL.md` — rewritten (primary path = tag → CI;
  manual runbook corrected to the shim and demoted to fallback).
- `shim/pyproject.toml` — unchanged in shape; becomes script-generated on bump.
- `tests/` — `release.sh --dry-run` test; idempotency-logic unit test. Existing
  `test_shim_package.py` / `test_check_dist_version.py` unchanged.

## Out-of-repo one-time prerequisite

Add an OIDC Trusted Publisher to **both** `jrag-cli` and `java-codebase-rag` on
pypi.org (repo `HumanBean17/jrag`, workflow `release.yml`, environment
`release`). The first tag-triggered release fails closed until both are
configured — by design, so the workflow can never silently fall back to a token.

## TL;DR

The release pipeline has zero tags, no changelog, a fully manual dual-publish,
and a `publish-pip` skill that documents a `sed` name-swap the codebase has
already replaced with a clean `shim/pyproject.toml`. This spec wires the
existing shim, version guard, and artifact-sync gate into a tag-triggered CI
release: a maintainer runs `scripts/release.sh X.Y.Z` (bumps root + shim in
lockstep, commits, pushes an annotated tag); CI builds both dists, publishes
both names to PyPI via OIDC Trusted Publishing (no stored token), verifies both
report `X.Y.Z`, and opens a GitHub Release with auto-categorized notes. The two
PyPI names are kept in sync by lockstep bumping, fixed publish order, required
both-names verification, and idempotent retry that heals partial failures to
the both-at-`X.Y.Z` terminal state. The stale skill is rewritten (CI primary,
shim-based manual fallback); no presentation/CONTRIBUTING/Dev-Status scope, no
1.0 commitment, no `CHANGELOG.md`.
