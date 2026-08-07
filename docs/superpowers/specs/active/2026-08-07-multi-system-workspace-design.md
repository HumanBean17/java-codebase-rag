# Multi-system workspace indexing (parent source-root)

- **Date:** 2026-08-07
- **Status:** in_progress

## Motivation

Q&A users (analysts, SREs, manual QA) keep Java code in a workspace that groups
multiple systems, each with one or more microservices, under one parent directory:

```
WorkingProject/            <- desired jrag source-root
    SystemA/
        microservice-1/      (pom.xml, src/main/java/...)
    SystemB/
        microservice-2/      (pom.xml, src/main/java/...)
```

They want one jrag index rooted at `WorkingProject/` so cross-system questions
("what in SystemB consumes SystemA's event?") resolve in a single graph. Running
`jrag install` from `WorkingProject/` exits 2 with "No Java build files found."

A source-level trace shows the index/build path already supports a parent
source-root end to end: source-root resolution (`config.py:resolve_operator_config`)
takes `--source-root` verbatim with no build-marker re-rooting; the CocoIndex walk
(`java_index_flow_lancedb.py:app_main`) and the graph walk
(`path_filtering.iter_source_files`) are recursive and apply the layered
ignore/gitignore rules at every depth; `microservice_for_path` returns the correct
`microservice-1`/`microservice-2` via the outermost-marker fallback when build
markers sit at the microservice dirs; `jrag watch` binds one recursive tree; and no
`git rev-parse` / single-repo assumption exists in the index/build path.

The sole blocker is the install wizard. `installer.py:detect_java_directories`
inspects only `source_root` and its **immediate children**. Build markers at
`SystemA/microservice-1/` are two levels deep, so detection bails at exit 2 before
any indexing or agent wiring runs. `jrag init` avoids the wizard (and consumes
`source_root` verbatim) but skips agent-artifact deployment, so it is not a complete
path for this persona.

## Goal & scope

**Goal.** A Q&A user runs `jrag install --source-root WorkingProject` (or `init`)
and gets one merged index spanning every nested Java system, with the agent surface
wired up, identical in shape to a single-repo install.

**In scope.** The install wizard's Java detection; UX confirmation for the
multi-system layout; documentation; tests.

**Out of scope.** Path-aware `microservice_roots`; nested-layout subset-selection;
fixing the parent-POM attribution rollup (documented only); marker-less source dumps.

## Decisions

1. **One merged index.** The parent source-root produces a single index; cross-system
   edges (`HTTP_CALLS`, `ASYNC_CALLS`) resolve within it. Per-system scoping at read
   time uses the existing `microservice` filter — no new multi-index machinery.
2. **Wizard happy path (Approach A).** Extend detection so a parent source-root does
   not bail; default to "index everything"; document edge cases. No config-schema
   change, no reprocess required for existing single-repo users.
3. **Detection trigger stays build-markers-only.** A layout with no
   `pom.xml` / `build.gradle` / `build.gradle.kts` / `build.sbt` anywhere under the
   source-root still exits 2 (genuine no-Java), matching today's fail-fast contract.
4. **Subset-picker skipped for multi-system layouts.** The interactive
   `select_microservices` picker is not offered for the multi-system outcome — the
   name-based `microservice_roots` key cannot express nested subsets, and the
   cross-system Q&A intent wants all systems.

## Detection behavior (core change)

**Component:** `installer.py:detect_java_directories`, consumed by `run_install`
(Stage 1), with the `len(java_dirs) >= 2` gate on `select_microservices`.

Detection evaluates three outcomes, in order:

1. **Single module** — `source_root` itself holds a build marker → returns `[Path(".")]`.
2. **Sibling modules** — one or more immediate children of `source_root` hold build
   markers → returns those child names.
3. **Multi-system parent** — no immediate-child markers, but a build marker exists
   deeper under `source_root` → returns a sentinel meaning "index everything under
   `source_root`." The indexing path treats this identically to `[Path(".")]`.

The multi-system scan is a bounded recursive descent that reuses the existing prune
rules (`path_filtering.UNCONDITIONAL_PRUNE_DIRS` + build-output directory pruning +
`.git`), so `node_modules` / `target` / `build` / `.git` / etc. neither inflate the
scan nor produce false detections. A directory is a detection leaf: once its build
marker is found, its subtree is not scanned for further markers. If no build marker is
found anywhere under `source_root`, detection exits 2 (genuine no-Java), unchanged.

When detection returns the multi-system sentinel, `run_install` **skips**
`select_microservices` (the picker cannot express the layout) and proceeds to indexing
and agent wiring keyed off `source_root` as today.

## Wizard UX & config

- On the multi-system outcome, the wizard prints a short summary naming the top-level
  directories under which Java was found (e.g. *"Multi-system workspace — found Java
  under: SystemA/, SystemB/. Indexing all as one merged index."*), then continues
  through model, host, scope, and surface selection unchanged.
- The generated `.java-codebase-rag.yml` **omits** `microservice_roots` (index-all).
  Attribution falls through to the existing outermost-marker rule in
  `microservice_for_path`.
- Agent-artifact deployment, MCP/CLI surface selection, the hosts marker, and
  `jrag init` are unchanged — they already key off `source_root` (the parent).
- `update_gitignore` is unchanged. When `WorkingProject/` is not a git repository, it
  is a no-op; the index lives at `WorkingProject/.java-codebase-rag/`, outside the
  nested repositories, so it is not committed by them. When `WorkingProject/` is a git
  repository, the existing behavior appends `.java-codebase-rag/` to its `.gitignore`.

## Attribution & edge cases

- **Common case** (build markers at `microservice-*/`): `microservice_for_path`
  returns `microservice-1`/`microservice-2` and `module_for_path` returns the
  innermost module. Correct, no change.
- **Parent-POM rollup**: when `SystemA/`/`SystemB/` carry aggregator `pom.xml`, the
  outermost-marker rule assigns `microservice="SystemA"`/`"SystemB"` to every file
  beneath, while `module` keeps inner-module granularity. This is documented as
  expected behavior (system-level bucketing), not fixed. System-level `microservice=`
  filters remain useful for cross-system Q&A.
- **Name collisions** (two microservices named `app` across systems): a pre-existing
  limitation of name-based `microservice_roots`; documented. FQN and `module`
  disambiguate at query time.
- **Agent invoked from inside a microservice directory**: walk-up config discovery
  (`config.py:discover_project_root`) from `SystemA/microservice-1/` finds
  `WorkingProject/.java-codebase-rag.yml`; the `.java-codebase-rag/config_source`
  pointer bridges the sibling-config case. Unchanged.

## Documentation

- `docs/JRAG-CLI.md` — a "Multi-system workspace" note under setup: `install`/`init`
  accept a parent source-root and produce one merged index spanning nested systems.
- `docs/CODEBASE_REQUIREMENTS.md` (§A.1) — extend the monorepo/microservice discussion
  with the parent-source-root multi-system case and the parent-POM attribution rollup.
- `docs/CONFIGURATION.md` — note that for multi-system workspaces the YAML and index
  live at the parent and `source_root` resolves to the parent.

## Tests

- A fixture mirroring the layout: `WorkingProject/{SystemA/microservice-1,
  SystemB/microservice-2}`, each with a build marker and a `.java` source.
- Detection on the fixture returns the multi-system outcome and does not exit 2.
- A focused install smoke on the fixture generates a YAML with no `microservice_roots`
  and completes indexing.
- Regression: `microservice_for_path` on a file under `SystemA/microservice-1` returns
  `microservice-1`.
- Per `CLAUDE.md`: erase any stale `tests/*/.java-codebase-rag*` before running; tests
  build their own index in a temp dir; no index is committed under `tests/`.

## Files touched (design-level)

- `src/java_codebase_rag/installer.py` — `detect_java_directories` (multi-system
  outcome) and the `run_install` Stage-1 gate.
- `docs/JRAG-CLI.md`, `docs/CODEBASE_REQUIREMENTS.md`, `docs/CONFIGURATION.md` —
  multi-system workflow documentation.
- `tests/` — new fixture + detection/install/attribution tests.

## TL;DR

Pointing `jrag` at a parent dir of nested Java systems already works for indexing —
only the `jrag install` wizard's one-level Java detection bails at exit 2. This change
extends detection to recognize a multi-system parent source-root (bounded recursive
build-marker scan, reusing existing prune rules), defaults to "index everything,"
skips the subset-picker for this layout, and documents the parent-POM attribution
rollup. One merged index, cross-system edges resolve, agent surface wired up — no
config-schema change, no reprocess for existing users.
