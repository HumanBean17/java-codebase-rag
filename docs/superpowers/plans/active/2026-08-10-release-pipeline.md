# Tag-triggered CI release pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a release by running one script that bumps and tags; CI then builds the canonical `jrag-cli` dist and the `java-codebase-rag` shim, publishes both to PyPI via OIDC Trusted Publishing (no stored token), verifies both names report the same version, and opens a GitHub Release with auto-generated notes.

**Architecture:** Two halves joined by an annotated git tag. Human half = `scripts/release.sh X.Y.Z` (delegates pure version math to `scripts/bump_version.py`, runs the existing artifact-sync gate, commits `bump version to X.Y.Z`, pushes tag `vX.Y.Z`). CI half = `.github/workflows/release.yml` triggered on tag `v*`: builds root + shim, guards each with the existing `check_dist_version.py`, publishes both via `pypa/gh-action-pypi-publish` (OIDC), skipping any name already at the target via a new `scripts/pypi_at_version.py` helper, verifies both names match, creates the GitHub Release. The stale `sed` name-swap in the `publish-pip` skill is retired; the shim becomes the dual-publish mechanism.

**Tech Stack:** Bash, Python 3.11 (stdlib `tomllib`, `urllib`, `zipfile`, `argparse`), GitHub Actions, PyPI Trusted Publishing (OIDC), `pypa/gh-action-pypi-publish`, PyPA `build`.

## Global Constraints

- **Python:** all commands use `.venv/bin/python` and `.venv/bin/pip` at repo root; never system `python`/`pip`. Editable install only.
- **Two PyPI names, lockstep:** `jrag-cli` (canonical, `[project].name` in root `pyproject.toml`) and `java-codebase-rag` (legacy shim at `shim/pyproject.toml`). Every release publishes both at the same version; they must never diverge.
- **PEP 427 name normalization** (dist-file prefixes): `jrag-cli → jrag_cli`, `java-codebase-rag → java_codebase_rag`. The existing guard derives the prefix from `[project].name`.
- **Version source of truth:** root `pyproject.toml` `[project].version` (`version = "X.Y.Z"`, plain numeric, no pre-release tags). The shim version is *derived* from the root by `bump_version.py`, never edited independently. Tag format: annotated `vX.Y.Z`.
- **Existing on-disk names retained:** `.java-codebase-rag*` and `JAVA_CODEBASE_RAG_*` are backward-compat — do not rename.
- **Pre-upload guard:** `scripts/check_dist_version.py [--dist D] [--pyproject P]` exits 0 clean / 1 on empty, foreign-version, or METADATA mismatch; target is read from `--pyproject`.
- **Sync gate:** `scripts/sync_agent_artifacts.py --check` exits 0 synced / 1 out-of-sync.
- **PyPI permanence:** uploads are permanent (yank only, no overwrite). Cleanup of `dist/`, `build/`, `*.egg-info` uses the `find`-based egg-info removal (zsh `NOMATCH` trap); these are gitignored.
- **First release fails closed** until Trusted Publishers are configured on both PyPI projects (out-of-repo prerequisite, documented in the skill).
- **Commit convention:** bump commits use `bump version to X.Y.Z`.

---

## File Structure

**New files:**
- `scripts/bump_version.py` — pure version logic: parse current version from root `pyproject.toml`, validate the target is a strict increase, write the new version into root `pyproject.toml` (its `version`) and `shim/pyproject.toml` (its `version` **and** its `jrag-cli==<ver>` dep pin) in lockstep. Modes `--check` (validate, no write) and `--apply` (validate + write). Fully unit-testable; no git.
- `scripts/pypi_at_version.py` — idempotency helper: query the PyPI JSON API for a project, exit 0 if `<version>` is already published there, else non-zero. Unit-testable with a stubbed `urlopen`.
- `scripts/release.sh` — bash orchestrator (the human half): precondition checks (clean tree), delegate to `bump_version.py`, run the sync gate, commit, push annotated tag. Flags `--dry-run`, `--no-push`, `--skip-sync-check`.
- `.github/workflows/release.yml` — tag-triggered CI publish (root + shim build, guard both, OIDC dual publish with idempotency, verify both, GitHub Release). Also `workflow_dispatch` with a `dry_run` input for rehearsal.
- `.github/release.yml` — GitHub release-notes categorization config (consumed by the Release step; distinct from the workflow despite the shared basename).
- `tests/package/test_bump_version.py`, `tests/package/test_pypi_at_version.py`, `tests/package/test_release_sh.py` — unit tests for the three new scripts.

**Modified files:**
- `.claude/skills/publish-pip/SKILL.md` — rewritten: primary path = tag → CI; manual runbook corrected to the shim and demoted to a "CI is down" fallback; documents the Trusted-Publisher prerequisite.
- `shim/pyproject.toml` — unchanged in shape; its version + dep pin are now written by `bump_version.py` (no longer hand-edited).

**Out-of-repo (documented, not a repo task):** add an OIDC Trusted Publisher to both `jrag-cli` and `java-codebase-rag` on pypi.org.

---

## Task 1: `scripts/bump_version.py` — version math + lockstep writer

**Files:**
- Create: `scripts/bump_version.py`
- Test: `tests/package/test_bump_version.py`

**Interfaces:**
- Consumes: root `pyproject.toml` `[project].version`; `shim/pyproject.toml` `[project].version` and `[project].dependencies` (the `jrag-cli==<ver>` pin). Existing pattern: `tests/package/test_shim_package.py` already reads both pyprojects via `tomllib`.
- Produces: a CLI invoked as:
  - `.venv/bin/python scripts/bump_version.py --check <X.Y.Z>` — validates only, no writes. Exit 0 if `<X.Y.Z>` is well-formed (`^\d+\.\d+\.\d+$`) and strictly greater than the current root version (compared as an `(int, int, int)` tuple); exit 1 otherwise, with a stderr message naming the current version and why the target is rejected.
  - `.venv/bin/python scripts/bump_version.py --apply <X.Y.Z>` — runs the same validation, then writes the new version into root `pyproject.toml` (the `version = "..."` line under `[project]`) and `shim/pyproject.toml` (both the `version = "..."` line and the `dependencies = ["jrag-cli==..."]` pin). Exit 0 on success, 1 on validation failure (no file written on failure). The script resolves repo root as `git rev-parse --show-toplevel` from CWD; pyprojects are `<root>/pyproject.toml` and `<root>/shim/pyproject.toml`.
  - Both modes read the current version from the root pyproject (single source of truth); the shim's existing version is not consulted as input — it is only overwritten on `--apply`.

- [ ] **Step 1: Write failing tests for the version-math contract**

Test file `tests/package/test_bump_version.py`, using a `tmp_path` repo: write a minimal `<tmp>/pyproject.toml` with `[project]\nname = "jrag-cli"\nversion = "0.12.0"\n` and `<tmp>/shim/pyproject.toml` with `[project]\nname = "java-codebase-rag"\nversion = "0.12.0"\ndependencies = ["jrag-cli==0.12.0"]\n`. Run the script with `cwd=tmp_path` (so `git rev-parse` isn't required — see Step 3 note) via `subprocess.run([sys.executable, str(SCRIPT), "--check", target], cwd=tmp_path)`. Tests to write:
  - `test_check_accepts_higher_patch`: `--check 0.12.1` → exit 0.
  - `test_check_accepts_higher_minor`: `--check 0.13.0` → exit 0.
  - `test_check_accepts_major`: `--check 1.0.0` → exit 0.
  - `test_check_rejects_equal`: `--check 0.12.0` → exit 1, stderr mentions current `0.12.0`.
  - `test_check_rejects_lower`: `--check 0.11.9` → exit 1.
  - `test_check_rejects_malformed`: `--check 0.12` → exit 1 (does not match `^\d+\.\d+\.\d+$`).
  - `test_apply_writes_lockstep`: `--apply 0.13.0` → exit 0; re-read both pyprojects with `tomllib` and assert root `version == "0.13.0"`, shim `version == "0.13.0"`, shim `dependencies == ["jrag-cli==0.13.0"]`.
  - `test_apply_no_write_on_invalid`: `--apply 0.11.0` (lower) → exit 1; assert root `pyproject.toml` still has `version == "0.12.0"` (unchanged).
  - `test_apply_preserves_other_lines`: after `--apply 0.13.0`, the root pyproject still contains its original `name = "jrag-cli"` line and the shim still contains `name = "java-codebase-rag"` (targeted replace, not a full rewrite).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/package/test_bump_version.py -v`
Expected: FAIL — script file does not exist / `ModuleNotFoundError` or nonzero for every case.

- [ ] **Step 3: Write minimal implementation**

Behavior to provide: argparse with mutually-required mode flags `--check`/`--apply` and a positional `<version>`. Resolve repo root: prefer `git rev-parse --show-toplevel`; if that fails (not a git repo, as in unit tests), fall back to CWD. Read current version from `<root>/pyproject.toml` with `tomllib`. Validate `<version>` against `^\d+\.\d+\.\d+$`; parse both into `(major, minor, patch)` int tuples and require target > current. `--check` prints nothing on success (or a short OK line) and exits 0; on failure prints a stderr message naming current vs. target and exits 1. `--apply` performs the same validation first (exit 1, no writes, on failure), then does a **targeted text replace** (preserve all other content/formatting/comments): in root `pyproject.toml`, replace the `version = "..."` line under `[project]`; in `shim/pyproject.toml`, replace both the `version = "..."` line and the `jrag-cli==...` token inside `dependencies`. Use byte-exact line editing or a regex scoped to those lines; do not round-trip through a TOML writer (no `tomli_w` dependency). Exit 0 after writing.
Do NOT write code that handles pre-release suffixes, epochs, or non-numeric versions — plain `X.Y.Z` only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/package/test_bump_version.py -v`
Expected: PASS — all 9 cases.

- [ ] **Step 5: Commit**

Run: `git add scripts/bump_version.py tests/package/test_bump_version.py`
Run: `git commit -m "feat(release): bump_version.py — lockstep version math + writer"`

---

## Task 2: `scripts/pypi_at_version.py` — idempotency helper

**Files:**
- Create: `scripts/pypi_at_version.py`
- Test: `tests/package/test_pypi_at_version.py`

**Interfaces:**
- Consumes: the PyPI JSON API at `https://pypi.org/pypi/<name>/json`. CA bundle from `certifi` (the existing skill sets `SSL_CERT_FILE` to `certifi.where()` to avoid the local `CERTIFICATE_VERIFY_FAILED` error — the script must do this internally so callers don't have to).
- Produces: a CLI `.venv/bin/python scripts/pypi_at_version.py <project-name> <X.Y.Z>` that returns:
  - exit **0** (stdout `published`) when the project exists on PyPI AND (`info.version == <X.Y.Z>` OR `<X.Y.Z>` is a key in the `releases` map) — i.e., that exact version is already uploaded;
  - exit **1** (stdout `not-published`) when the project exists but the version is absent, or the project itself is absent (HTTP 404);
  - exit **1** (stderr `unknown: <reason>`) on any network/JSON/SSL error — so the workflow proceeds to attempt the upload and lets PyPI's own duplicate-rejection (400) be the loud backstop.

- [ ] **Step 1: Write failing tests with a stubbed PyPI response**

Test file `tests/package/test_pypi_at_version.py`. Use `monkeypatch` to replace `urllib.request.urlopen` with a fake returning canned JSON. Build the fake response objects so `.read()` returns a JSON byte string and the code path used by the script (likely `json.load(urlopen(...))` or `urlopen(...).read()`) works. Run via `subprocess.run([sys.executable, str(SCRIPT), name, version], env={...})` — but because the script is a subprocess, prefer instead to monkeypatch by importing the module's function in-process: structure the script as a `main() -> int` plus a `_fetch(name) -> dict|None` helper, and have tests import `pypi_at_version` and monkeypatch `_fetch`. Tests:
  - `test_published_when_latest_matches`: `_fetch` returns `{"info": {"version": "0.12.0"}, "releases": {}}`; `main(["x", "0.12.0"])` → 0, stdout `published`.
  - `test_published_when_in_releases_not_latest`: `_fetch` returns `{"info": {"version": "0.13.0"}, "releases": {"0.12.0": [...]}}`; `main(["x", "0.12.0"])` → 0 (an older published version counts).
  - `test_not_published_when_absent`: `_fetch` returns `{"info": {"version": "0.13.0"}, "releases": {"0.13.0": [...]}}`; `main(["x", "0.12.0"])` → 1, stdout `not-published`.
  - `test_not_published_when_project_missing`: `_fetch` returns `None` (404); `main(["x", "0.12.0"])` → 1, stdout `not-published`.
  - `test_unknown_on_network_error`: `_fetch` raises `urllib.error.URLError`; `main(["x", "0.12.0"])` → 1, stderr contains `unknown`.
  - `test_unknown_on_bad_json`: `_fetch` raises `json.JSONDecodeError`; `main(["x", "0.12.0"])` → 1, stderr contains `unknown`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/package/test_pypi_at_version.py -v`
Expected: FAIL — module/script does not exist.

- [ ] **Step 3: Write minimal implementation**

Behavior: a `_fetch(name)` function that builds the URL `https://pypi.org/pypi/<name>/json`, sets `SSL_CERT_FILE` to `certifi.where()` (via `os.environ` before the request, or by passing an `ssl.create_default_context(cafile=certifi.where())` to `urlopen`), issues the GET, and returns the parsed JSON dict (or `None` on HTTP 404, raises on other errors). `main(argv)` parses `<name>` and `<version>`, calls `_fetch`, applies the published-rule above, prints the appropriate token to stdout/stderr, and returns the exit code. Wire `if __name__ == "__main__": sys.exit(main(sys.argv[1:]))`. Do not add retry, caching, or rate-limit logic — keep it one-shot.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/package/test_pypi_at_version.py -v`
Expected: PASS — all 6 cases.

- [ ] **Step 5: Commit**

Run: `git add scripts/pypi_at_version.py tests/package/test_pypi_at_version.py`
Run: `git commit -m "feat(release): pypi_at_version.py — idempotency check helper"`

---

## Task 3: `scripts/release.sh` — the human-half orchestrator

**Files:**
- Create: `scripts/release.sh` (mode 0755)
- Test: `tests/package/test_release_sh.py`

**Interfaces:**
- Consumes:
  - `scripts/bump_version.py` `--check`/`--apply` (Task 1).
  - `scripts/sync_agent_artifacts.py --check` (existing; exit 0 synced / 1 out-of-sync).
  - The git CLI (`rev-parse`, `status --porcelain`, `commit`, `tag -a`, `push`).
- Produces: a CLI `release.sh <X.Y.Z> [--dry-run] [--no-push] [--skip-sync-check]` with behavior:
  - **Preconditions (always checked first):** CWD is inside a git worktree (`git rev-parse --show-toplevel` succeeds); working tree is clean (`git status --porcelain` is empty); `<X.Y.Z>` parses as `^\d+\.\d+\.\d+$`. Fail closed with a clear stderr message and nonzero exit if any fails.
  - **Version validation:** run `bump_version.py --check <X.Y.Z>`; fail closed on nonzero.
  - **Sync gate** (skipped when `--skip-sync-check`): run `sync_agent_artifacts.py --check`; fail closed on nonzero (message tells the operator to run the syncer without `--check`, commit, and retry).
  - **`--dry-run`:** stop here — print what would happen (the target version, the commit subject `bump version to <X.Y.Z>`, the tag `v<X.Y.Z>`) and exit 0. No commit, no tag, no push, no file writes.
  - **Apply:** run `bump_version.py --apply <X.Y.Z>`, then `git add pyproject.toml shim/pyproject.toml`, `git commit -m "bump version to <X.Y.Z>"`, `git tag -a v<X.Y.Z> -m "Release <X.Y.Z>"`.
  - **Push** (skipped when `--no-push`): `git push && git push origin v<X.Y.Z>` (or `git push --follow-tags` per the repo's default push behavior — whichever pushes both the commit and the annotated tag).
  - Resolve sibling-script paths relative to the script's own location (`SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"`) so it works from any CWD inside the repo; repo root via `git rev-parse --show-toplevel`.

- [ ] **Step 1: Write failing tests for the orchestrator**

Test file `tests/package/test_release_sh.py`. Two execution contexts:
  - **Real repo, `--dry-run` (no mutation):**
    - `test_dry_run_next_version_passes`: compute next = current root version + patch; run `[bash, str(RELEASE_SH), next, "--dry-run"]` with `cwd=REPO_ROOT`; assert exit 0 and stdout contains `bump version to <next>` and `v<next>`. Then assert `git status --porcelain` is still empty (no mutation).
    - `test_dry_run_lower_version_refused`: run with a target lower than current (e.g. `0.0.1`); assert nonzero exit and stderr mentions monotonic / current version; assert no mutation.
  - **Temp repo (for commit/tag + dirty-tree checks):** a helper that `git init`s a `tmp_path`, writes a minimal root `pyproject.toml` (`name = "jrag-cli"`, `version = "0.1.0"`) and `shim/pyproject.toml` (`name = "java-codebase-rag"`, `version = "0.1.0"`, `dependencies = ["jrag-cli==0.1.0"]`), `git add -A && git commit -m init`, and sets `git config user.email/name`. Then:
    - `test_apply_commits_and_tags_lockstep`: run `[bash, str(RELEASE_SH), "0.2.0", "--no-push", "--skip-sync-check"]` with `cwd=tmp_repo`; assert exit 0; assert `git -C tmp_repo log --oneline` contains a `bump version to 0.2.0` commit; assert `git -C tmp_repo tag -l` is exactly `v0.2.0` and it is annotated (`git cat-file -t v0.2.0` == `tag`); re-read both pyprojects with `tomllib` and assert root/shim versions and the shim dep pin all equal `0.2.0`.
    - `test_dry_run_refuses_dirty_tree`: in the temp repo, `echo x >> pyproject.toml`; run `--dry-run 0.2.0`; assert nonzero and stderr mentions dirty/clean tree; assert no commit/tag created.
    - `test_dry_run_no_mutation`: in a clean temp repo, run `--dry-run 0.2.0`; assert exit 0; assert `git -C tmp_repo log --oneline` is unchanged (still only the init commit) and `git tag -l` is empty.
  Note: invoke `bash` explicitly (do not rely on the +x bit in tests); `RELEASE_SH = REPO_ROOT / "scripts" / "release.sh"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/package/test_release_sh.py -v`
Expected: FAIL — `release.sh` does not exist.

- [ ] **Step 3: Write minimal implementation**

Behavior per the Produces contract above. Use `set -euo pipefail`. Resolve `SCRIPT_DIR` and `ROOT`. Implement flag parsing by hand (the flag set is small). Run `bump_version.py` and `sync_agent_artifacts.py` via `python "$SCRIPT_DIR/..."` — but use the venv python on `PATH` if available, else `python3`; document that the operator runs it from a repo with `.venv` activated (the script may detect `"$ROOT/.venv/bin/python"` and prefer it). On any failed precondition print `ERROR: <reason>` to stderr and `exit 1`. The `--dry-run` path must return before any mutating command. The apply path must `git add` exactly the two pyproject files. The push step must push both the commit and the tag. Keep the script under ~80 lines; no logic that duplicates `bump_version.py`'s math.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/package/test_release_sh.py -v`
Expected: PASS — all cases.

- [ ] **Step 5: Commit**

Run: `git add scripts/release.sh tests/package/test_release_sh.py`
Run: `git commit -m "feat(release): release.sh — bump+tag orchestrator (human half)"`

---

## Task 4: `.github/workflows/release.yml` + `.github/release.yml` — CI publish + notes config

**Files:**
- Create: `.github/workflows/release.yml`
- Create: `.github/release.yml`
- Test: `tests/package/test_release_workflow.py`

**Interfaces:**
- Consumes:
  - Tag trigger `v*` (annotated tags pushed by `release.sh`).
  - `scripts/check_dist_version.py` (existing) — run once per dist with `--pyproject` pointing at the relevant pyproject.
  - `scripts/pypi_at_version.py` (Task 2) — skip an upload whose name is already at the target.
  - PyPA `build` (`python -m build`) for the root; `python -m build` run in `shim/` for the shim.
  - `pypa/gh-action-pypi-publish@v1` (OIDC trusted-publishing mode is the action's default when no token/secret is supplied).
  - GitHub's auto-generated release notes, categorized by `.github/release.yml`.
- Produces: a workflow that, on tag `v*`, produces both PyPI names at the tag's version and a GitHub Release; under `workflow_dispatch` with `dry_run: true`, performs the build+guard+idempotency-check steps but **skips** upload and Release creation (rehearsal mode).

- [ ] **Step 1: Write a structural test for both files**

Test file `tests/package/test_release_workflow.py`. `yaml.safe_load` is available via `pyyaml` (already a runtime dep). Tests:
  - `test_workflow_yaml_parses`: `yaml.safe_load` of `.github/workflows/release.yml` succeeds.
  - `test_workflow_triggers_on_tags`: the workflow's `on.push.tags` list contains a pattern matching `v*` (e.g. `'v*'`).
  - `test_workflow_has_oidc_permission`: `permissions.id-token` == `'write'` and `permissions.contents` == `'write'` at job or workflow level.
  - `test_workflow_uses_release_environment`: the publish job's `environment` == `'release'`.
  - `test_workflow_supports_dry_run_dispatch`: `on.workflow_dispatch.inputs.dry_run` exists (a manual rehearsal trigger).
  - `test_notes_config_parses_and_categorizes`: `yaml.safe_load` of `.github/release.yml` succeeds and `data['changelog']` has a `categories` list whose entry labels include at least `Features`, `Bug Fixes`, and `Documentation; and a `exclude.labels` or ignore pattern that suppresses `chore`-scoped PRs. (Assert on the structural keys; do not over-constrain formatting.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/package/test_release_workflow.py -v`
Expected: FAIL — files do not exist.

- [ ] **Step 3: Write the workflow and notes config**

`.github/workflows/release.yml` — `name: release`; `on: { push: { tags: ['v*'] }, workflow_dispatch: { inputs: { dry_run: { description, type: boolean, default: false } } } }`; one job `release` on `ubuntu-latest` with `environment: release` and `permissions: { contents: write, id-token: write }`. Job steps, in order:
1. `actions/checkout@v4`.
2. `actions/setup-python@v5` with `python-version: "3.11"`.
3. Install build tooling: `python -m pip install --upgrade pip build`.
4. Read target version from the checked-out root `pyproject.toml` (a small Python step exposing it as an env var or output, e.g. `VERSION=$(python -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")`).
5. **Build root:** `python -m build` (produces `dist/jrag_cli-<ver>.*`).
6. **Guard root:** `python scripts/check_dist_version.py --dist dist --pyproject pyproject.toml` (fail job on nonzero).
7. **Idempotency check (root):** `python scripts/pypi_at_version.py jrag-cli "$VERSION"` and capture exit; if 0 (already published) skip the root upload, else proceed.
8. **Publish root:** `pypa/gh-action-pypi-publish@v1` with `packages-dir: dist` — gated on `dry_run == false` AND the idempotency check said "not published".
9. **Build shim:** in the `shim/` directory, `python -m build` into a separate dist (e.g. working-dir `shim` so its `dist/` holds `java_codebase_rag-<ver>.*`).
10. **Guard shim:** `python scripts/check_dist_version.py --dist shim/dist --pyproject shim/pyproject.toml`.
11. **Idempotency check (shim):** `python scripts/pypi_at_version.py java-codebase-rag "$VERSION"`.
12. **Publish shim:** `pypa/gh-action-pypi-publish@v1` with `packages-dir: shim/dist` — gated on `dry_run == false` AND shim not-already-published.
13. **Verify both:** a step that re-runs `pypi_at_version.py` for both names and asserts both exit 0 (both now at `$VERSION`); fail the job if either is not published.
14. **Create GitHub Release:** `softprops/action-gh-release@v2` (or equivalent) with `generate_release_notes: true`, gated on `dry_run == false`, targeting the tag.
Order is fixed: root publish before shim publish (Task 1 of the sync invariant). The `dry_run` gating uses step `if:` conditions; in dry-run the job still runs steps 1–13 (build, guard, idempotency, verify) but skips 8, 12, 14.

`.github/release.yml` — GitHub's release-notes config: a `changelog:` block with `categories:` mapping conventional-commit/label prefixes to section titles (`feat → Features`, `fix → Bug Fixes`, `perf → Performance`, `docs → Documentation`) and an `exclude.labels:` list that suppresses `chore`-scoped PRs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/package/test_release_workflow.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add .github/workflows/release.yml .github/release.yml tests/package/test_release_workflow.py`
Run: `git commit -m "feat(release): tag-triggered CI publish workflow + release-notes config"`

---

## Task 5: Rewrite the `publish-pip` skill (CI primary, shim-based fallback)

**Files:**
- Modify: `.claude/skills/publish-pip/SKILL.md`

**Interfaces:**
- Consumes: the workflow from Task 4; the shim as the dual-publish mechanism; `bump_version.py` / `release.sh` from Tasks 1 & 3.
- Produces: a corrected, non-stale runbook.

- [ ] **Step 1: Write a verification test that pins the skill's new shape**

Test file `tests/package/test_publish_skill_runbook.py`. The skill is a markdown file at `REPO_ROOT / ".claude/skills/publish-pip/SKILL.md"`. Tests read its text:
  - `test_primary_path_is_tag_to_ci`: the file mentions `scripts/release.sh` and references the tag-triggered workflow as the primary release path.
  - `test_no_stale_sed_nameswap`: the file does NOT contain the string `sed -i` or the phrase `name = "jrag-cli"` swap instruction (the stale procedure is gone).
  - `test_manual_fallback_uses_shim`: the manual/fallback section references `shim/pyproject.toml` and `python -m build` run in `shim/` (not a root name-swap).
  - `test_documents_trusted_publisher_prerequisite`: the file documents that OIDC Trusted Publishers must be configured on both `jrag-cli` and `java-codebase-rag` on pypi.org before the first tag-triggered release.
  - `test_retains_dual_publish_policy`: the file still states both names must report the same version after a release (the close-out invariant).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/package/test_publish_skill_runbook.py -v`
Expected: FAIL — the skill still contains the `sed -i` name-swap and lacks the CI-primary / shim / trusted-publisher content.

- [ ] **Step 3: Rewrite the skill**

Restructure `.claude/skills/publish-pip/SKILL.md`:
  - **Primary release path (new top section):** "Tag → CI publishes both names." State the maintainer runs `.venv/bin/bash scripts/release.sh X.Y.Z` (or activates the venv first), which bumps root + shim, syncs, commits, and pushes annotated tag `vX.Y.Z`; the `release.yml` workflow then builds, guards, dual-publishes via OIDC, verifies both names, and opens the GitHub Release. Note the one-time prerequisite: add an OIDC Trusted Publisher to both `jrag-cli` and `java-codebase-rag` on pypi.org (repo `HumanBean17/jrag`, workflow `release.yml`, environment `release`); the first tag-triggered release fails closed until both are configured.
  - **Manual fallback (corrected, demoted):** "When CI is down or reconciling a diverged PyPI state." Keep the venv-only / `~/.pypirc` tooling notes and the `find`-based egg-info cleanup (zsh `NOMATCH` lesson) and the `check_dist_version.py` guard. Replace the `sed` name-swap with the **shim** procedure: build root → upload `jrag-cli`; `cd shim && python -m build` → upload `java-codebase-rag`; run `check_dist_version.py --pyproject shim/pyproject.toml` before the shim upload. Use `bump_version.py --apply` for the version step so root + shim stay in lockstep.
  - **Dual-publish policy (kept):** both names must report the same version after every release; never leave them diverged. Keep the `0.10.0` artifact-leak incident note (still relevant to the manual fallback).
  - Keep the YAML frontmatter (`name`, `description`) accurate; update `description` to mention tag-triggered CI as the primary path.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/package/test_publish_skill_runbook.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add .claude/skills/publish-pip/SKILL.md tests/package/test_publish_skill_runbook.py`
Run: `git commit -m "docs(publish-pip): CI-primary release runbook; shim-based manual fallback"`

---

## Task 6: End-to-end rehearsal + first-release acceptance

**Files:**
- No new source files. Verify-only task (may add a short `docs/JRAG-CLI.md` note if the operator doc should mention the release flow — check whether that doc currently covers releases; if not, leave it, since presentation docs are out of scope per the spec).

**Interfaces:**
- Consumes: Tasks 1–5 complete; both PyPI projects have Trusted Publishers configured (out-of-repo).

- [ ] **Step 1: Verify the unit + structural suite is green**

Run: `.venv/bin/pytest tests/package/test_bump_version.py tests/package/test_pypi_at_version.py tests/package/test_release_sh.py tests/package/test_release_workflow.py tests/package/test_publish_skill_runbook.py tests/package/test_shim_package.py tests/package/test_check_dist_version.py -v`
Expected: PASS — every new and existing package-level guard green.

- [ ] **Step 2: Dry-run rehearsal via `workflow_dispatch`**

After merging the branch (or from the branch if the workflow runs on `workflow_dispatch` from any ref), trigger the `release` workflow manually with `dry_run: true` (GitHub Actions UI, or `gh workflow run release.yml -f dry_run=true`). Open the run and confirm: both root and shim build, both guards (`check_dist_version.py`) pass, both idempotency checks run, and the verify step reports whether each name is already at the target — with **no upload and no Release created** (the dry-run gates held).
Expected: the dry-run job reaches the verify step green and skips 8/12/14.

- [ ] **Step 3: Cut the first real release**

Run: `.venv/bin/bash scripts/release.sh <next-version>` (e.g. `0.13.0` or the next patch), pushing tag `v<next-version>`. Confirm on the Actions tab that the `release` run publishes both names via OIDC, the verify step passes (both at `<next-version>`), and a GitHub Release is created with auto-categorized notes. Independently confirm both PyPI projects report `<next-version>`:
`SSL_CERT_FILE="$(.venv/bin/python -c "import certifi;print(certifi.where())")"` then the PyPI JSON API for both `jrag-cli` and `java-codebase-rag`.
Expected: both names at `<next-version>`; GitHub Release present; the run green end to end.

- [ ] **Step 4: Commit any artifact drift**

If the first real release surfaced a skill/doc correction, commit it. Otherwise nothing to commit.
Expected: working tree clean (or a single follow-up docs commit).

---

## Self-Review (resolved inline before save)

- **Code scan:** No method bodies, algorithms, or copy-paste code in any task — only signatures, CLI contracts, data shapes, behavior descriptions, and test scenarios with expected results. (The single inline `tomllib` version-extract snippet in Task 4 step 4 is a one-line data-shape example for the version env var, not implementation logic; kept because the implementer needs the exact read path. Acceptable.)
- **Self-containment:** Each task restates the contracts it consumes (e.g., Task 3 re-states `bump_version.py`'s `--check`/`--apply` and `sync_agent_artifacts.py --check`'s exit codes; Task 4 re-states `check_dist_version.py`'s flags and `pypi_at_version.py`'s exit semantics). No task sends the reader to another task to understand what to build.
- **Spec coverage:** Spec §"Release flow" → Tasks 1+3 (human half) and Task 4 (CI half). §"Components (a)–(e)" → Tasks 1, 3, 4, 5, and the `shim` generated-by-bump rule (Task 1's `--apply` writes it). §"Authentication — Trusted Publishing" → Task 4 (permissions/environment/action) and Task 5 (prerequisite documented). §"Sync guarantee & idempotency" → Task 2 (helper), Task 4 (ordered publish + idempotent skip + both-names verify), Task 1 (lockstep source). §"Failure modes" → covered by the guard/idempotency contracts in Tasks 1/2/4. §"Tests" → each task's test file; Task 6 is the no-real-publish boundary + first-release acceptance. §"Out-of-repo prerequisite" → Task 5 documents it; Task 6 step 3 requires it. No spec section unaddressed.
- **Placeholder scan:** No "TBD/TODO/handle edge cases/etc." — every step states exact behavior and expected result.
- **Type/name consistency:** `bump_version.py` (`--check`/`--apply`), `pypi_at_version.py` (exit 0 published / 1 not-published-or-unknown), `release.sh` (`--dry-run`/`--no-push`/`--skip-sync-check`), `release.yml` (workflow) vs `release.yml` (notes config, disambiguated by full path), `environment: release` — all consistent across tasks.
