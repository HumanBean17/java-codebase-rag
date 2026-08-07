# Multi-System Workspace Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `jrag install`/`init` accept a parent source-root containing nested Java systems (e.g. `WorkingProject/{SystemA/microservice-1, SystemB/microservice-2}`) and build one merged index, instead of exiting 2 at the wizard's one-level Java detection.

**Architecture:** The index/build path already supports a parent source-root recursively — the only blocker is `installer.detect_java_directories`, which scans just `source_root` and its immediate children. This plan replaces it with `detect_java_layout`, which distinguishes three layouts (single module / sibling modules / multi-system parent) and returns a `JavaDetection` value. `run_install` prints a summary and skips the subset-picker for the multi-system case (index-all, no `microservice_roots` written). Attribution already works via `microservice_for_path`'s outermost-marker fallback; a regression test pins it for the nested-parent case.

**Tech Stack:** Python 3, pytest, PyYAML; the `java_codebase_rag` package (editable install). Reuses `path_filtering` prune rules and `graph_enrich` attribution — no new dependencies.

**Spec:** `docs/superpowers/specs/active/2026-08-07-multi-system-workspace-design.md`

## Global Constraints

- Python env: use `.venv/bin/python` and `.venv/bin/pip` at repo root only (never system python/pip). Editable install is enforced by `tests/conftest.py`; if behavior looks stale while pytest passes, run `.venv/bin/pip install -e ".[dev]"`.
- Before running any test subset, erase stale manual indexes that hijack project-root discovery: `rm -rf tests/*/.java-codebase-rag tests/*/.java-codebase-rag.yml tests/*/.java-codebase-rag.hosts`
- Tests build their own fresh index in a temp dir; never commit an index under `tests/`.
- On-disk names `.java-codebase-rag*` and `JAVA_CODEBASE_RAG_*` env vars are intentional (backward compat) — do not rename them.
- The full suite is slow; run the relevant subset during development, then the full suite once at the end.
- The build-marker set used by detection MUST equal `graph_enrich.BUILD_MARKERS` (`pom.xml`, `build.gradle`, `build.gradle.kts`, `build.sbt`) so detection and attribution agree on what a "module" is.
- Commit messages end with a trailer line: `Co-Authored-By: Claude <noreply@anthropic.com>`.
- All work happens on branch `feat/multi-system-workspace` (already created; spec already committed there).

## File Structure

- `src/java_codebase_rag/installer.py` — add `JavaDetection` dataclass + `LAYOUT_*` constants + `BUILD_FILES`; replace `detect_java_directories` with `detect_java_layout`; add `_multi_system_summary`; update `run_install` Stage-1 to consume `JavaDetection` and handle the multi-system case; update the `select_microservices` docstring that references the old function name.
- `tests/package/test_installer.py` — rewrite `TestDetectJavaDirectories` for the new contract; add multi-system detection tests, a `_multi_system_summary` test, and a multi-system `run_install` integration test.
- `tests/graph/test_graph_enrich.py` — add a nested-parent `microservice_for_path` regression test.
- `docs/JRAG-CLI.md`, `docs/CODEBASE_REQUIREMENTS.md`, `docs/CONFIGURATION.md` — multi-system workflow documentation.

---

### Task 1: Detection contract + `run_install` multi-system handling

**Files:**
- Modify: `src/java_codebase_rag/installer.py` (replace `detect_java_directories` at lines ~225-263; edit `run_install` Stage-1 at lines ~2044-2065; edit the `select_microservices` docstring at line ~416)
- Test: `tests/package/test_installer.py` (rewrite `TestDetectJavaDirectories` at lines ~101-153; add new tests)

**Interfaces:**

- Consumes (unchanged, already in the codebase):
  - `from java_codebase_rag.graph.path_filtering import UNCONDITIONAL_PRUNE_DIRS, _is_build_output_dir` — prune semantics reused so detection sees the same tree the indexer walks. `UNCONDITIONAL_PRUNE_DIRS` is a `frozenset[str]` of dir names (`.git`, `.idea`, `.venv`, `node_modules`); `_is_build_output_dir(parent_dir_path: str, dirname: str) -> bool` is True when `dirname` is `target`/`build`/`out` AND the parent holds a build-tool indicator.
  - `select_microservices(java_dirs: list[Path], *, non_interactive: bool, preselected: list[str] | None) -> list[str] | None` — unchanged; returns `None` for "all", else a subset.
  - `generate_yaml_config(source_root, model, microservice_roots, existing_yaml) -> str` — unchanged; omits `microservice_roots` when it is `None`.
- Produces (new contract other tasks rely on):
  - `@dataclass(frozen=True) class JavaDetection` with fields:
    - `kind: str` — exactly one of the `LAYOUT_*` constants below.
    - `roots: list[Path]` — module roots relative to `source_root`. For single-module and multi-system this is `[Path(".")]`; for sibling-modules it is the list of immediate-child dir names that hold a build marker (iterdir order).
    - `system_dirs: list[str]` — top-level directory names under `source_root` that contain a discovered marker in their subtree; non-empty ONLY for the multi-system kind, empty otherwise. Sorted.
  - Module constants: `LAYOUT_SINGLE_MODULE = "single_module"`, `LAYOUT_SIBLING_MODULES = "sibling_modules"`, `LAYOUT_MULTI_SYSTEM = "multi_system"`.
  - Module constant `BUILD_FILES: tuple[str, ...] = ("pom.xml", "build.gradle", "build.gradle.kts", "build.sbt")` with an inline comment: "Keep in sync with graph_enrich.BUILD_MARKERS."
  - `detect_java_layout(source_root: Path) -> JavaDetection` — evaluates, in order:
    1. **Single module** — if any `BUILD_FILES` marker is a file directly in `source_root`: return `JavaDetection(LAYOUT_SINGLE_MODULE, [Path(".")], [])`.
    2. **Sibling modules** — else collect immediate-child directories of `source_root` that hold a `BUILD_FILES` marker. If any: return `JavaDetection(LAYOUT_SIBLING_MODULES, [Path(child.name) for those children], [])`.
    3. **Multi-system parent** — else perform a bounded recursive descent over `source_root` to look for any `BUILD_FILES` marker deeper than the immediate children. The descent prunes `dirnames` at each step by removing any entry in `UNCONDITIONAL_PRUNE_DIRS` or for which `_is_build_output_dir(current_dirpath, entry)` is True; any directory that itself holds a `BUILD_FILES` marker is a **leaf** (record it, do not descend into it). If at least one marker is discovered: compute `system_dirs` as the sorted unique set of the first relative path segment (relative to `source_root`) of each discovered marker's directory; return `JavaDetection(LAYOUT_MULTI_SYSTEM, [Path(".")], system_dirs)`.
    4. **No Java** — if no marker is found anywhere under `source_root`: print `Error: No Java build files (<pom.xml, build.gradle, build.gradle.kts, build.sbt>) found in <source_root> or its subtree.` to stdout and raise `SystemExit(2)`. (Wording changes from "immediate children" to "subtree" because detection now scans deeper.)
  - `_multi_system_summary(system_dirs: list[str]) -> str` — returns exactly:
    `Multi-system workspace — found Java under: <dir1>/, <dir2>/. Indexing all as one merged index.` where `<dirN>/` are the `system_dirs` entries each suffixed with `/`, joined by `, `. (For `["SystemA","SystemB"]` the returned string contains the substrings `Multi-system workspace`, `SystemA/`, `SystemB/`, and `Indexing all as one merged index`.)
  - `run_install` Stage-1 change: call `detection = detect_java_layout(source_root)` (wrapped in the existing `try/except SystemExit as e: return e.code`). Then:
    - If `detection.kind == LAYOUT_MULTI_SYSTEM`: `print(_multi_system_summary(detection.system_dirs))` and set `selected_roots = None` (skip the subset-picker — the name-based `microservice_roots` key cannot express nested subsets).
    - Else: keep the existing behavior but operate on `detection.roots` — `selected_roots = select_microservices(detection.roots, non_interactive=non_interactive, preselected=...) if len(detection.roots) >= 2 else None`, wrapped in its existing `try/except SystemExit`.
    - The rest of `run_install` (model, hosts, scope, surface, deploy, `generate_yaml_config(source_root, resolved_model, selected_roots, ...)`, indexing) is unchanged.
  - Update the `select_microservices` docstring (line ~416) so its reference to the old `detect_java_directories` names `detect_java_layout` instead.

- [ ] **Step 1: Write/rewrite the detection tests (failing first)**

  Rewrite the class currently named `TestDetectJavaDirectories` (rename it `TestDetectJavaLayout`) so every test imports `detect_java_layout` and asserts a `JavaDetection`. Each test's scenario and exact expected result:
  - Root holds `pom.xml` → `JavaDetection(kind=LAYOUT_SINGLE_MODULE, roots=[Path(".")], system_dirs=[])`. Keep the two parallel variants for `build.gradle` and `build.gradle.kts` (same expectation).
  - No root marker; `service-a/pom.xml` and `service-b/pom.xml` exist → `kind == LAYOUT_SIBLING_MODULES`, `set(roots) == {Path("service-a"), Path("service-b")}` (order-insensitive), `system_dirs == []`.
  - No root marker; only `service-a/pom.xml` → `kind == LAYOUT_SIBLING_MODULES`, `roots == [Path("service-a")]`, `system_dirs == []`.
  - No root marker, no child markers, nothing deeper → raises `SystemExit` with `code == 2`; captured stdout contains both `"Error:"` and `"No Java build files"`.

  Add these new detection tests in the same class:
  - **Multi-system happy path**: create `SystemA/microservice-1/pom.xml` and `SystemB/microservice-2/pom.xml` (no root marker, no immediate-child marker) → `kind == LAYOUT_MULTI_SYSTEM`, `roots == [Path(".")]`, `set(system_dirs) == {"SystemA", "SystemB"}`.
  - **Multi-system leaf rule**: `SystemA/microservice-1/pom.xml` AND `SystemA/microservice-1/sub-mod/pom.xml` → `set(system_dirs) == {"SystemA"}` (the nested `sub-mod` marker is not counted because `microservice-1` is a leaf).
  - **Multi-system prunes node_modules**: `SystemA/microservice-1/pom.xml` AND `node_modules/evil/pom.xml` → `set(system_dirs) == {"SystemA"}` (the `node_modules` subtree is pruned via `UNCONDITIONAL_PRUNE_DIRS`).
  - **Multi-system recognizes build.sbt**: `SystemA/microservice-1/build.sbt` → `kind == LAYOUT_MULTI_SYSTEM`, `set(system_dirs) == {"SystemA"}` (proves `BUILD_FILES` includes `build.sbt`).

- [ ] **Step 2: Run detection tests to verify they fail**

  Run: `.venv/bin/python -m pytest tests/package/test_installer.py::TestDetectJavaLayout -v`
  Expected: FAIL — `detect_java_layout` is not defined (the old `detect_java_directories` still exists). The four new multi-system tests and the rewritten assertions all error/fail.

- [ ] **Step 3: Write the `_multi_system_summary` test (failing first)**

  Add a test (e.g. in a new `TestMultiSystemSummary` class) verifying `_multi_system_summary(["SystemA", "SystemB"])` returns a string that contains all of: `"Multi-system workspace"`, `"SystemA/"`, `"SystemB/"`, and `"Indexing all as one merged index"`. Also assert it does NOT contain a trailing unjoined list repr (i.e. it is a single formatted string, not a `str(list)`).

- [ ] **Step 4: Run the summary test to verify it fails**

  Run: `.venv/bin/python -m pytest tests/package/test_installer.py::TestMultiSystemSummary -v`
  Expected: FAIL — `_multi_system_summary` is not defined.

- [ ] **Step 5: Implement the detection contract and summary helper**

  In `src/java_codebase_rag/installer.py`: add the `UNCONDITIONAL_PRUNE_DIRS`/`_is_build_output_dir` import from `path_filtering`; add the `LAYOUT_*` constants and `BUILD_FILES`; add the `JavaDetection` frozen dataclass (mirror the existing `@dataclass(frozen=True) HostConfig` style); add `detect_java_layout` implementing the four-case behavior in the Produces block above; add `_multi_system_summary`. Delete the old `detect_java_directories`. The implementer writes the code from the behavior description — no algorithm is specified here beyond the contract above.

- [ ] **Step 6: Run detection + summary tests to verify they pass**

  Run: `.venv/bin/python -m pytest tests/package/test_installer.py::TestDetectJavaLayout tests/package/test_installer.py::TestMultiSystemSummary -v`
  Expected: PASS (all detection + summary tests green). Note: `run_install` still calls the removed `detect_java_directories`, but Python resolves that name at call time, so it is a runtime `NameError` only when `run_install` is invoked — it does not affect these unit tests, which call `detect_java_layout` directly.

- [ ] **Step 7: Write the multi-system `run_install` integration test (failing first)**

  Add a test in `TestInstallIntegration` mirroring `test_install_non_interactive_claude_code_bank_chat`, but building the layout directly in `tmp_path` (no committed fixture): create `SystemA/microservice-1/pom.xml`, `SystemA/microservice-1/src/main/java/com/acme/Foo.java`, `SystemB/microservice-2/pom.xml`, `SystemB/microservice-2/src/main/java/com/acme/Bar.java`; create `.git`. `monkeypatch.setattr(shutil, "which", lambda x: "/fake/bin/java-codebase-rag-mcp")`; monkeypatch `java_codebase_rag.pipeline.run_cocoindex_update` and `java_codebase_rag.pipeline.run_build_ast_graph` to return `subprocess.CompletedProcess(args=[...], returncode=0)`; `monkeypatch.setattr(Path, "cwd", lambda: tmp_path)`. Capture stdout with `capsys`. Call `run_install(non_interactive=True, agents=["claude-code"], scope="project", model="auto", surface="mcp", source_root=tmp_path, quiet=True)`. Assert: `result == 0`; the YAML at `tmp_path/.java-codebase-rag.yml` parses and has NO `microservice_roots` key; `tmp_path/.mcp.json` exists with the `java-codebase-rag` stdio entry; the skill and agent files exist under `tmp_path/.claude/`; captured stdout contains `"Multi-system workspace"`, `"SystemA/"`, and `"SystemB/"`.

- [ ] **Step 8: Run the integration test to verify it fails**

  Run: `.venv/bin/python -m pytest tests/package/test_installer.py::TestInstallIntegration::<new_test_name> -v`
  Expected: FAIL — `run_install` still calls the removed `detect_java_directories` (NameError) or does not yet print the summary.

- [ ] **Step 9: Wire `run_install` to consume `JavaDetection`**

  In `run_install` Stage-1, apply the change described in Produces: call `detect_java_layout`, branch on `LAYOUT_MULTI_SYSTEM` (print `_multi_system_summary(detection.system_dirs)`, set `selected_roots = None`), else run the existing `select_microservices(detection.roots, ...)` gate. Update the `select_microservices` docstring reference. Leave the rest of `run_install` untouched.

- [ ] **Step 10: Run the full installer test module to verify it passes**

  Run: `.venv/bin/python -m pytest tests/package/test_installer.py -v`
  Expected: PASS — every class including the existing `TestSelectMicroservices`, `TestGenerateYamlConfig`, `TestInstallIntegration` (bank-chat), and PR-4 progress tests stays green; the new multi-system detection, summary, and integration tests pass.

- [ ] **Step 11: Run the broader relevant subset for regressions**

  Run: `.venv/bin/python -m pytest tests/package/ tests/graph/test_graph_enrich.py -q`
  Expected: PASS (no regressions in installer or graph-enrich surfaces).

- [ ] **Step 12: Commit**

  Run: `git add src/java_codebase_rag/installer.py tests/package/test_installer.py`
  Run: `git commit -m "feat(install): support multi-system parent source-root\n\nReplace one-level detect_java_directories with detect_java_layout,\nwhich recognizes a parent source-root of nested Java systems and\nindexes everything as one merged index (no microservice_roots).\n\nCo-Authored-By: Claude <noreply@anthropic.com>"`

---

### Task 2: `microservice_for_path` nested-parent regression test

This is a characterization test for an UNCHANGED pure function — it should pass on the first run. It pins the spec's attribution claim for the multi-system layout. If it unexpectedly fails, `microservice_for_path` has a regression and the task expands to fix it (not expected per the source investigation).

**Files:**
- Test: `tests/graph/test_graph_enrich.py` (add one test alongside the existing `microservice_for_path` tests; they already import `microservice_for_path` from `java_codebase_rag.graph.graph_enrich` and use `tmp_path`/`monorepo` fixtures)

**Interfaces:**
- Consumes: `microservice_for_path(file_path: str, project_root: str | Path | None = None) -> str` — unchanged. With no `microservice_roots` override present, it returns the outermost build-marker ancestor's dir name between `project_root` and the file.
- Produces: a new test proving attribution for the nested-parent layout (no production code change).

- [ ] **Step 1: Write the regression test**

  Using `tmp_path`, create `SystemA/microservice-1/pom.xml` and `SystemA/microservice-1/src/main/java/com/acme/Foo.java` (and similarly a second system `SystemB/microservice-2/...`). Assert `microservice_for_path(str(tmp_path / "SystemA/microservice-1/src/main/java/com/acme/Foo.java"), tmp_path) == "microservice-1"` and the SystemB file yields `"microservice-2"`. This proves the outermost-marker fallback returns the inner microservice (not the `SystemA` grouping dir) when markers live at the microservice dirs.

- [ ] **Step 2: Run the test to verify it passes (characterization)**

  Run: `.venv/bin/python -m pytest tests/graph/test_graph_enrich.py -k microservice -v`
  Expected: PASS — the new test passes alongside the existing `microservice_for_path` tests. (If it fails, stop and treat it as a real attribution regression to fix before proceeding.)

- [ ] **Step 3: Commit**

  Run: `git add tests/graph/test_graph_enrich.py`
  Run: `git commit -m "test(graph): microservice_for_path nested-parent regression\n\nPin attribution for the multi-system parent layout: a file under\nSystemA/microservice-1 yields microservice=microservice-1 via the\noutermost-marker fallback.\n\nCo-Authored-By: Claude <noreply@anthropic.com>"`

---

### Task 3: Document the multi-system workspace workflow

**Files:**
- Modify: `docs/JRAG-CLI.md` (add a subsection under the `install` setup area)
- Modify: `docs/CODEBASE_REQUIREMENTS.md` (extend §A.1 "Two location concepts: module and microservice")
- Modify: `docs/CONFIGURATION.md` (add a note near §1 config discovery / §2 project YAML)

**Interfaces:**
- Consumes: the exact behaviors shipped in Task 1 (parent source-root accepted; `jrag install`/`init` build one merged index; generated YAML omits `microservice_roots`; cross-system edges resolve; parent-POM rollup caveat).
- Produces: operator-facing documentation describing the supported workflow.

- [ ] **Step 1: Add the JRAG-CLI subsection**

  Add a "Multi-system workspace" subsection near the `install` command description. It must state, in prose:
  - `jrag` accepts a parent source-root that contains multiple nested Java systems (concrete example tree `WorkingProject/{SystemA/microservice-1, SystemB/microservice-2}`).
  - Run `jrag install --source-root WorkingProject` (or `cd WorkingProject && jrag install`); detection recognizes the multi-system layout, prints the systems it found, and builds ONE merged index at `WorkingProject/.java-codebase-rag/`.
  - The generated `.java-codebase-rag.yml` omits `microservice_roots` (all systems indexed); cross-service edges (`HTTP_CALLS`/`ASYNC_CALLS`) resolve within the single graph, so cross-system questions work.
  - The same applies to `jrag init --source-root WorkingProject`.
  - Caveat (cross-link to `CODEBASE_REQUIREMENTS.md` §A.1): if the `System*/` dirs themselves carry aggregator `pom.xml`, `microservice` attribution rolls up to the System name while `module` keeps inner-module granularity.

- [ ] **Step 2: Extend CODEBASE_REQUIREMENTS §A.1**

  Add a short paragraph to the "Two location concepts: module and microservice" discussion stating: pointing `jrag` at a parent directory of nested systems is supported (by both the wizard and `init`); with build markers at the `System/microservice-*/` level, `microservice_for_path` returns the inner microservice name via the outermost-marker rule; if `System*/` carry aggregator POMs, `microservice` rolls up to the System name (`module` unchanged). Keep it consistent with the JRAG-CLI subsection.

- [ ] **Step 3: Add the CONFIGURATION note**

  Near §1 (config discovery) or §2 (project YAML), add a note: for multi-system workspaces the `.java-codebase-rag.yml` and the `.java-codebase-rag/` index live at the parent directory and `source_root` resolves to that parent; walk-up discovery from inside any nested microservice finds the parent YAML (and the `.java-codebase-rag/config_source` pointer bridges the sibling-config case).

- [ ] **Step 4: Verify the sections are present and mutually consistent**

  Run: `rg -n "Multi-system workspace" docs/JRAG-CLI.md docs/CODEBASE_REQUIREMENTS.md docs/CONFIGURATION.md`
  Expected: each file shows the new heading/content. Re-read the three additions and confirm they agree on the example tree, the merged-index claim, and the parent-POM caveat.

- [ ] **Step 5: Commit**

  Run: `git add docs/JRAG-CLI.md docs/CODEBASE_REQUIREMENTS.md docs/CONFIGURATION.md`
  Run: `git commit -m "docs: multi-system workspace (parent source-root) workflow\n\nDocument that jrag install/init accept a parent source-root of\nnested Java systems and build one merged index, plus the parent-POM\nattribution caveat.\n\nCo-Authored-By: Claude <noreply@anthropic.com>"`

---

## Final verification (after all tasks)

- [ ] Run the full test suite once: `.venv/bin/python -m pytest -q` (erase stale `tests/*/.java-codebase-rag*` first). Expected: all green.
- [ ] Sanity-check the operator path end-to-end on a scratch multi-system tree: `jrag init --source-root <scratch parent>` (or `jrag install --non-interactive --agent claude-code --source-root <scratch parent>` if agent wiring is desired) builds one merged index; `jrag meta --source-root <scratch parent>` shows two microservices and no errors. (Manual; only on a real Java tree if available — otherwise rely on the integration test.)
