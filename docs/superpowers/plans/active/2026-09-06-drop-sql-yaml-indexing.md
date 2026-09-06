# Drop SQL/YAML Indexing — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove SQL (Flyway) and YAML (Spring config) vector indexing entirely, leaving JVM sources (`.java`/`.kt`) as the only indexed input and a single-table `search` contract with no `table` selector.

**Architecture:** The CocoIndex flow stops extracting SQL/YAML; the Lance table registry shrinks 3→1; the read path (backend → `search_v2` → MCP schema → CLI → daemon payload) drops the `table` parameter end to end; the watcher treats `.sql`/`.yml` edits as non-events; a one-time cleanup drops the two orphaned `.lance` tables from existing index dirs and `erase` switches to dropping by directory scan. The graph, ontology, and `ONTOLOGY_VERSION` are untouched. Spec: `docs/superpowers/specs/active/2026-09-01-drop-sql-yaml-indexing-design.md`.

**Tech Stack:** Python 3.11+ stdlib `argparse`/`pathlib`, CocoIndex flow API, LanceDB embedded tables, pytest.

## Global Constraints

- Work happens in the worktree `.claude/worktrees/drop-sql-yaml` on branch `feat/drop-sql-yaml-indexing` (based off `feat/jrag-prime`). Use the worktree's own `.venv/bin/python` / `.venv/bin/pip` — never system python, never the main checkout's venv.
- Editable install only. If `jrag`/`java-codebase-rag` behave stale while pytest passes: `.venv/bin/pip install -e ".[dev]"` — don't report it as an issue.
- Before running any test suite: `rm -rf tests/*/.java-codebase-rag tests/*/.java-codebase-rag.{yml,hosts}` (stale manual indexes hijack project-root discovery). Never commit index state under `tests/`.
- Run only the test subset relevant to the current task; the full suite runs once, in Task 9.
- **Do not bump `ONTOLOGY_VERSION`** (stays `19` in `src/java_codebase_rag/ast/ast_java.py`). The graph build is byte-identical in this change.
- On-disk names (`.java-codebase-rag*` index dir, project YAML, hosts) and `JAVA_CODEBASE_RAG_*` env vars are retained as-is.
- No new config knobs: nothing that selects indexed file types.
- Historical specs (`docs/specs/**`, `docs/superpowers/specs/**`, `docs/superpowers/plans/**` other than this file) are records — do not edit them.
- HEAVY integration tests are gated by `JAVA_CODEBASE_RAG_RUN_HEAVY=1`.
- Commit after every task; message prefixes follow repo convention (`feat:`, `fix:`, `test:`, `docs:`).

## Pre-Verified Facts (do not re-derive)

- `docs/MIGRATION.md` mentions only generic "Lance tables" — **no row needed** for this change.
- `tests/bank-chat-system/.claude/skills/` no longer exists — **no fixture artifact updates needed**.
- Eval harness searches java-only today (`src/java_codebase_rag/eval/runner.py:300`) — only the kwarg removal is needed.
- The lexical BM25 list, graph-expand list, and FTS index are Symbol/java-only already; only the dense-vector list ever served sql/yaml rows.

---

### Task 1: Vector flow stops extracting SQL/YAML

**Files:**
- Modify: `src/java_codebase_rag/index/java_index_flow_lancedb.py` (docstring `:2`; `SQL_CHUNK`/`YAML_CHUNK` import `:47-48`; matcher docs `:230-231`; pre-walk predicates `:265-277`; `process_sql_file` `:609`; `process_yaml_file` `:658`; skip comment `:717`; sql/yaml schema+mount blocks `:742-759`; walks `:819-833`; drain-order comment `:857`; drains `:872-873`)
- Modify: `src/java_codebase_rag/index/java_index_v1_common.py:18-19` (delete `SQL_CHUNK`, `YAML_CHUNK`; fix module docstring `:1`)
- Test: `tests/integration/test_lancedb_e2e.py:366-383` (structural pin — non-HEAVY)
- Test: `tests/index/test_approximate_vectors_total.py` (create; if `tests/index/` lacks `__init__.py` conventions, follow the neighboring test package layout)

**Interfaces:**
- Consumes: nothing from other tasks (first task).
- Produces: a flow module that (a) defines neither `process_sql_file` nor `process_yaml_file` and neither `SqlLanceChunk` nor `YamlLanceChunk`, (b) contains exactly 2 `coco.use_context(IGNORE)` sites (java, kotlin), (c) mounts only `LANCE_TABLE_NAMES[0]`, (d) `_approximate_vectors_total(project_root: Path) -> int` counts only files matching the registered language-backend suffixes under `LayeredIgnore`. `java_index_v1_common` exports no `SQL_CHUNK`/`YAML_CHUNK`. Later tasks rely on the flow never referencing `LANCE_TABLE_NAMES[1]`/`[2]` again.

- [ ] **Step 1: Update the structural pin (failing)**

In `test_lancedb_e2e.py`, the source-structure test currently asserts exactly 4 `coco.use_context(IGNORE)` sites in the flow (java, kotlin, sql, yaml). Change it to assert exactly **2** sites (java, kotlin), and extend it to assert via `hasattr`/module-attribute checks that the flow module defines none of: `process_sql_file`, `process_yaml_file`, `SqlLanceChunk`, `YamlLanceChunk`; and that `java_index_v1_common` defines neither `SQL_CHUNK` nor `YAML_CHUNK`.

- [ ] **Step 2: Add the pre-walk unit test (failing)**

New test in `tests/index/test_approximate_vectors_total.py`: build a tmp project tree containing `src/main/java/com/x/A.java`, `src/main/resources/db/migration/V1__init.sql`, and `src/main/resources/application.yml`; call `_approximate_vectors_total(project_root)`; assert it returns `1`. Current code counts the `.sql` and `.yml` too, so it returns `3` — this is the failing expectation.

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/integration/test_lancedb_e2e.py -k "ignore or structure or context" -v` (select the structural test by its real name) and `.venv/bin/python -m pytest tests/index/test_approximate_vectors_total.py -v`
Expected: FAIL — 4 sites vs 2 expected; symbols present vs absent expected; total 3 vs 1.

- [ ] **Step 4: Remove the SQL/YAML extraction**

In `java_index_flow_lancedb.py` delete: the two `localfs.walk_dir` blocks for sql/yaml (`:819-833`); `process_sql_file` and `process_yaml_file` bodies (`:609-704`); `SqlLanceChunk` and `YamlLanceChunk` dataclasses (`:311-332`); the sql/yaml `TableSchema.from_class` + `mount_table_target` blocks (`:742-759`, keeping only the java mount on `LANCE_TABLE_NAMES[0]`); the two `_drain_files_concurrently` calls for sql/yaml (`:872-873`); the sql/yaml predicate blocks inside `_approximate_vectors_total` (`:265-277`); the `SQL_CHUNK`/`YAML_CHUNK` import (`:47-48`); and every docstring/comment naming SQL/YAML (`:2`, `:9` note, `:230-231`, `:717` skip-comment, `:857` drain-order comment). In `java_index_v1_common.py` delete `SQL_CHUNK`/`YAML_CHUNK` (`:18-19`) and fix the module docstring to name Java/Kotlin sources only. The java/kotlin extraction paths, concurrency plumbing, and ignore handling are untouched.

- [ ] **Step 5: Run tests to verify they pass**

Run: same two commands as Step 3.
Expected: PASS.

- [ ] **Step 6: Commit**

Run: `git add src/java_codebase_rag/index/ tests/integration/test_lancedb_e2e.py tests/index/`
Run: `git commit -m "feat(index): stop extracting SQL/YAML in the vector flow"`

---

### Task 2: Table registry shrinks 3 → 1

**Files:**
- Modify: `src/java_codebase_rag/lance_optimize.py:34-38` (`LANCE_TABLE_NAMES`)
- Modify: `src/java_codebase_rag/search/search_lancedb.py:61-65` (`TABLES`)
- Test: `tests/package/test_lance_optimize.py:238-247, 270-281`

**Interfaces:**
- Consumes: Task 1's flow (no longer references `LANCE_TABLE_NAMES[1]`/`[2]`).
- Produces: `LANCE_TABLE_NAMES: tuple[str, ...] == ("javacodeindex_java_code",)` and `TABLES: dict[str, str] == {"java": "javacodeindex_java_code"}`. These exact shapes are consumed by Tasks 3–6. The optimize loop and absent-table `"skipped"` behavior are otherwise unchanged.

- [ ] **Step 1: Update the registry pins (failing)**

In `tests/package/test_lance_optimize.py`: the parity test (`:270-281`) pins `LANCE_TABLE_NAMES == set(TABLES.values())` with exactly 3 tables — change the expected count to 1 and the expected membership to `{"javacodeindex_java_code"}`. Keep the absent-table `"skipped"` test (`:238-247`), updating its fixture so the "absent" table name is a plausible non-registered name (the sql/yaml names are no longer special).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/package/test_lance_optimize.py -v`
Expected: FAIL — parity test sees 3 tables vs 1 expected.

- [ ] **Step 3: Shrink the constants**

`LANCE_TABLE_NAMES` becomes the 1-tuple `("javacodeindex_java_code",)`; `TABLES` becomes `{"java": "javacodeindex_java_code"}`. No other edits in these two modules.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/package/test_lance_optimize.py tests/search/test_search_lancedb.py -v`
Expected: PASS for lance_optimize; search tests may show known failures only in sql/yaml-specific cases (those are rewritten in Task 4) — if any *java-path* search test fails, fix before committing.

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/lance_optimize.py src/java_codebase_rag/search/search_lancedb.py tests/package/test_lance_optimize.py`
Run: `git commit -m "feat(store): LANCE_TABLE_NAMES 3->1 — java source table only"`

---

### Task 3: Legacy-table cleanup + erase-by-scan

**Files:**
- Modify: `src/java_codebase_rag/lance_optimize.py` (new helpers alongside `LANCE_TABLE_NAMES`)
- Modify: `src/java_codebase_rag/pipeline.py` (`_run_cocoindex_update_impl` `:302` — hook the one-time drop)
- Modify: `src/java_codebase_rag/cli.py` (`_cmd_erase` `:699`, drop loop `:781-789`)
- Test: `tests/package/test_lance_optimize.py` (extend)

**Interfaces:**
- Consumes: Task 2's `LANCE_TABLE_NAMES` (1-tuple).
- Produces (all in `lance_optimize.py`):
  - `LEGACY_LANCE_TABLE_NAMES: tuple[str, ...] = ("sqlschemaindex_sql_schema", "yamlconfigindex_yaml_config")`
  - `drop_legacy_tables(idx_dir: Path) -> list[str]` — for each legacy name whose `<idx_dir>/<name>.lance` directory exists, remove it (LanceDB `drop_table` when the store opens it; otherwise remove the directory from disk), returning the removed names; returns `[]` when none present; idempotent.
  - `drop_all_tables_by_scan(idx_dir: Path) -> list[str]` — same drop semantics for **every** `*.lance` child directory of `idx_dir`, returning removed names; `[]` when the dir is empty/absent.
  - `pipeline._run_cocoindex_update_impl` calls `drop_legacy_tables` once per vector run after `idx_dir` is resolved, logging the removed names (silent when none).
  - `cli._cmd_erase` replaces its constant-listing drop loop with `drop_all_tables_by_scan`.

- [ ] **Step 1: Write the failing tests**

Extend `tests/package/test_lance_optimize.py`: (a) tmp `idx_dir` containing fake dirs `sqlschemaindex_sql_schema.lance` and `yamlconfigindex_yaml_config.lance` (each with a dummy file inside) plus `javacodeindex_java_code.lance` → `drop_legacy_tables` returns exactly the two legacy names, removes both dirs, leaves the java dir; second call returns `[]`. (b) same fixture → `drop_all_tables_by_scan` returns all three names and removes all three dirs. (c) empty tmp dir → both helpers return `[]` without raising.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/package/test_lance_optimize.py -v`
Expected: FAIL with ImportError/AttributeError — helpers not defined.

- [ ] **Step 3: Implement helpers + wire the two call sites**

Add the constant and two helpers per the Produces contract (fake/non-openable table dirs must fall back to directory removal — the unit tests drive this). In `pipeline._run_cocoindex_update_impl`, call `drop_legacy_tables(idx_dir)` after the index-dir resolution and before the cocoindex update, logging removed names via the module's existing logging pattern. In `cli._cmd_erase`, replace the loop that drops tables by name listing with a call to `drop_all_tables_by_scan`, keeping the existing success message and `--yes` gating unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/package/test_lance_optimize.py tests/package -v`
Expected: PASS (including any existing erase/optimize package tests).

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/lance_optimize.py src/java_codebase_rag/pipeline.py src/java_codebase_rag/cli.py tests/package/test_lance_optimize.py`
Run: `git commit -m "feat(store): drop legacy sql/yaml Lance tables; erase drops by scan"`

---

### Task 4: Search backend becomes single-table

**Files:**
- Modify: `src/java_codebase_rag/search/search_lancedb.py` (`TABLES` handled in Task 2; here: `run_search` `:956`, `_search_one_table` `:420`, `_apply_chunk_hints` `:191-203`, fused-all path `:1102-1139`, `main()` `--table` `:1148-1151, 1196-1201`)
- Modify: `src/java_codebase_rag/search/search_lexical.py` (`run_lexical_search` `:268`; sql/yaml early-return `:293-298`)
- Modify: `src/java_codebase_rag/mcp/mcp_v2.py` (backend call sites of `run_search`/`run_lexical_search` only — argument drops, not the `search_v2` signature)
- Modify: `src/java_codebase_rag/eval/runner.py:300` (drop `table_keys=["java"]`)
- Test: `tests/search/test_search_lancedb.py` (`:527-585` dedup passthrough, `:716` `_kind: "sql"` hint test)
- Test: `tests/search/test_search_lexical.py` (`:156-157` sql/yaml `[]` assertions)
- Test: `tests/mcp/test_mcp_v2.py:779` (yaml happy-path — delete here, not in Task 5)

**Interfaces:**
- Consumes: Task 2's `TABLES == {"java": ...}`.
- Produces:
  - `run_search(query, *, uri, limit, path_substring, model_name, device, offset=0, model=None, ...)` — the `table_keys: list[str]` parameter is removed; all remaining parameters keep their current names/types; the function searches the java table only and its return shape (list of row dicts, each carrying `_kind: "java"`) is unchanged.
  - `run_lexical_search(...)` — signature unchanged except the `table` parameter is removed and the sql/yaml early-return is gone; behavior for the java/symbol path identical.
  - `_search_one_table(...)` — the `kind` parameter is removed (java-only; enrichment columns always selected).
  - `_apply_chunk_hints(rows)` — no sql/yaml language-backfill branches; java rows unaffected.
  - CLI `main()` in `search_lancedb.py` — no `--table` argument.
  - `search_scoring._dedup_by_fqn` — **unchanged** (its FQN-less passthrough is kind-agnostic; verified not sql/yaml-specific — do not remove).
  - Task 5 consumes these signatures; Task 6's CLI relies on `search_v2` no longer needing a table.

- [ ] **Step 1: Update the backend tests (failing)**

In `tests/search/test_search_lancedb.py`: delete the sql/yaml FQN-dedup passthrough tests (`:527-585`) and the `_kind: "sql"` hint/line-refine test (`:716`); add one test asserting `run_search` on a fixture java table returns rows all carrying `_kind == "java"` with no `table_keys` parameter accepted (calling with `table_keys=[...]` raises `TypeError`). In `tests/search/test_search_lexical.py`: delete the `table="sql"`/`table="yaml"` `[]` assertions (`:156-157`). In `tests/mcp/test_mcp_v2.py`: delete the `search_v2(..., table="yaml", hybrid=True)` happy-path test (`:779`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/search/test_search_lancedb.py tests/search/test_search_lexical.py -v`
Expected: FAIL — new `TypeError` expectation not yet true (param still exists); deletions leave no red, the added test is the failing one.

- [ ] **Step 3: Implement the single-table backend**

Remove `table_keys` from `run_search` and the per-table fusion loop (single-table path becomes the only path; keep neighbor-context attach, graph-expand, and BM25-list fusion exactly as they are — they are already java-only). Remove `kind` from `_search_one_table` and its `has_lang` gating (enrichment columns always selected); keep setting `_kind = "java"` on rows. Remove sql/yaml backfill from `_apply_chunk_hints`. Remove `--table` from `main()`. In `search_lexical.py`, remove the `table` parameter and the sql/yaml early-return plus its docstring lines. Update the three call sites (`mcp_v2`'s `run_search`/`run_lexical_search` invocations — drop the arguments only) and `eval/runner.py:300` (drop the kwarg).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/search tests/mcp/test_mcp_v2.py tests/jrag/test_read_payloads.py -v`
Expected: PASS except tests that pass `table=` into `search_v2` beyond the deleted one — if any remain red, they are Task 5's scope; confirm they fail *only* on the `table` argument.

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/search/ src/java_codebase_rag/mcp/mcp_v2.py src/java_codebase_rag/eval/runner.py tests/search/ tests/mcp/test_mcp_v2.py`
Run: `git commit -m "feat(search): single-table backend — table selector removed from run_search/lexical"`

---

### Task 5: `search_v2` + MCP schema drop the `table` parameter

**Files:**
- Modify: `src/java_codebase_rag/mcp/mcp_v2.py` (`search_v2` `:922-933`; lazy `TABLES` import `:94-99`; graph-only advisory `:981-984`; hybrid `all` fast-fail `:1003-1010`; `_row_to_search_hit` `:678-707`)
- Modify: `src/java_codebase_rag/mcp/server.py` (search tool description `:652`; `table` Field `:666-669`; `list_code_index_tables_payload` `:347-362`)
- Modify: `src/java_codebase_rag/read_payloads.py` (`search_payload` `:523-573`; `args.table` pass-through `:564`)
- Verify: `src/java_codebase_rag/watch/protocol.py` (no table-specific keys expected — confirm, don't edit)
- Test: `tests/mcp/test_mcp_tools.py:68` (input-schema enum)
- Test: `tests/mcp/test_mcp_v2.py` (default-path search)
- Test: `tests/jrag/test_read_payloads.py:288-289`

**Interfaces:**
- Consumes: Task 4's `run_search`/`run_lexical_search` signatures.
- Produces:
  - `search_v2(query, hybrid=False, limit=5, offset=0, path_contains=None, filter=None, explain=False, graph=None, dedup=True, ...)` — the `table: str = "java"` parameter is removed; all remaining parameters keep current names/defaults; return shape (`SearchOutput` with `SearchHit` items) unchanged.
  - MCP `search` tool input schema contains **no** `table` field; tool description says "Ranked chunk retrieval over the indexed JVM sources" (no java/sql/yaml enumeration).
  - `search_payload(args, cfg, graph)` no longer reads `args.table`; builds the same `SearchOutput` via the table-less `search_v2`.
  - `list_code_index_tables_payload()` reflects `TABLES` (java-only) with no code change beyond what flowed from Task 2 — verify only.

- [ ] **Step 1: Update the contract tests (failing)**

In `tests/mcp/test_mcp_tools.py`: the schema test (`:68`) asserts the `table` input-schema enum `{java, sql, yaml, all}` — replace with an assertion that the input schema's properties contain **no** `table` key. In `tests/mcp/test_mcp_v2.py`: ensure a default-path test exists calling `search_v2(query=..., hybrid=True)` with no `table` argument, asserting hits come back with `filename`/`snippet`/`score` populated from the java fixture table. In `tests/jrag/test_read_payloads.py`: update the absent-table case (`:288-289`) so the payload call passes no table and the absent-table advisory still renders.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/mcp/test_mcp_tools.py tests/mcp/test_mcp_v2.py tests/jrag/test_read_payloads.py -v`
Expected: FAIL — schema still has `table`; `search_v2` still requires accepting it; any residual `table=` callers raise.

- [ ] **Step 3: Implement the contract change**

Remove `table` from `search_v2`'s signature and delete the graph-only/lexical sql/yaml advisory branch (`:981-984`) and the hybrid `all` fast-fail (`:1003-1010`) — lexical mode simply searches java. In `_row_to_search_hit`, remove any kind-conditional branches that exist solely for sql/yaml rows (the java mapping is the only path; `SearchHit` fields unchanged). In `server.py`, delete the `table` Field (`:666-669`) and reword the description (`:652`). In `read_payloads.search_payload`, stop reading/passing `args.table` (`:564`). Grep `watch/protocol.py` for `table` to confirm no protocol key carries it (search params ride as a generic dict) — no edit expected.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/mcp tests/jrag -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/mcp/ src/java_codebase_rag/read_payloads.py tests/mcp/ tests/jrag/`
Run: `git commit -m "feat(mcp): search_v2 and MCP schema drop the table parameter"`

---

### Task 6: CLI surface — `--table` flag, help, prime wording

**Files:**
- Modify: `src/java_codebase_rag/jrag.py` (search subparser `:1212-1232`; `--table` `:1228-1231`; subparser description `:1217`; `_cmd_search` `:4353+`)
- Modify: `src/java_codebase_rag/prime.py:82`
- Test: `tests/package/test_jrag_orientation.py:273-290`
- Test: any prime-payload content pins (grep `tests/` for `Lance tables` first; update pins if found)

**Interfaces:**
- Consumes: Task 5's table-less `search_v2` and `search_payload`.
- Produces: `jrag search` subparser with no `--table` argument (help text names no tables); `_cmd_search` reads no `args.table`; `jrag tables` prints the single java table (flows from Task 2 — verify only); prime payload's search line reads "Semantic search over the Lance vector index" (singular, no table enumeration). Stale scripts passing `--table` get argparse's standard `unrecognized arguments` error — expected and desired.

- [ ] **Step 1: Update the CLI tests (failing)**

In `tests/package/test_jrag_orientation.py`: delete the `--table all` routing test (`:273-290`); ensure a plain routing test exists — `jrag search <query>` reaches `search_v2` exactly once with no `table` kwarg (add it if the deleted test was the only search-routing coverage). If any prime-payload test pins the phrase "Lance tables", update the pin to the new wording.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/package/test_jrag_orientation.py -v`
Expected: FAIL — subparser still defines `--table`, so the no-flag routing assertion fails or the flag still parses.

- [ ] **Step 3: Implement the CLI change**

Remove `--table` from the search subparser (`:1228-1231`) and any table mention from its description/help (`:1217`, `:1229-1231`); remove `args.table` handling from `_cmd_search`. In `prime.py:82`, change "Semantic search over Lance tables." to "Semantic search over the Lance vector index." Run `.venv/bin/jrag search --help` and `.venv/bin/jrag tables` manually to confirm: no `--table` in help; `tables` lists only `javacodeindex_java_code`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/package -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/jrag.py src/java_codebase_rag/prime.py tests/package/`
Run: `git commit -m "feat(cli): drop --table from jrag search; prime wording singular"`

---

### Task 7: Watcher treats SQL/YAML edits as non-events

**Files:**
- Modify: `src/java_codebase_rag/watch/watcher.py` (docstrings `:13-26`; `_YAML_SUFFIXES` `:71`; prefixes `:76-77`; `_is_migration_sql` `:80-88`; `_is_application_yaml` `:91-102`; `_classify` sql/yaml branches `:266-269`; `reindex` routing `:313-383`)
- Test: `tests/watch/test_watcher.py` (classification table `:160-172`; `:273`; `:290`; `:301`; `:366`)

**Interfaces:**
- Consumes: nothing new (watcher routes to the same pipeline entrypoints).
- Produces: `_classify(path) -> set[str]` returns `set()` for **every** `.sql`, `.yml`, `.yaml` file (migration-shaped or not); `_YAML_SUFFIXES`, `_SQL_MIGRATION_PREFIX`, `_RESOURCES_PREFIX`, `_is_migration_sql`, `_is_application_yaml` no longer exist; `INDEXED_SUFFIXES` and `_GRAPH_INDEXED_KINDS` are unchanged; a watcher event on a `.sql`/`.yml` file triggers **no** cocoindex and **no** graph subprocess.

- [ ] **Step 1: Update the watcher tests (failing)**

In `tests/watch/test_watcher.py`: classification table (`:160-172`) — migration `V1__x.sql` → `set()`, `application.yml`/`application.yaml` → `set()` (non-matching `V1.sql`, `logback.yml`, `.bak` stay `set()`). Replace `test_reindex_sql_is_vectors_only_no_snapshot` (`:273`) and its yaml twin (`:290`) with tests asserting a `.sql`/`.yml` modify event runs **zero** reindex subprocesses. Mixed java+sql event (`:301`) → vectors once + graph once (java only; sql contributes nothing). Graph-only install + sql change (`:366`) stays a clean no-op.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/watch/test_watcher.py -v`
Expected: FAIL — classification still yields `{"sql"}`/`{"yaml"}`; reindex still fires vectors.

- [ ] **Step 3: Implement the watcher change**

Delete the four predicate constants/helpers and the sql/yaml branches in `_classify`; update the module and reindex docstrings that state "sql/yaml changes are vectors only". `reindex()` routing needs no structural change — with empty classification the event never reaches it (verify the routing predicate treats empty kinds as no-op; if an explicit guard is needed, add it as a named early-return).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/watch -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/watch/watcher.py tests/watch/test_watcher.py`
Run: `git commit -m "feat(watch): sql/yaml edits are non-events — no reindex"`

---

### Task 8: Docs sweep

**Files:**
- Modify: `docs/DESIGN.md:32-38` ("What it indexes" table; non-goals `:49-51`)
- Modify: `docs/ARCHITECTURE.md:8` (input line), `:108-112` (stores), `:128-137` (key constants)
- Modify: `docs/CODEBASE_REQUIREMENTS.md:337-356` (§A.6), `:526-545` (§B.5 — delete), `:637` (gap row)
- Modify: `docs/CONFIGURATION.md:337`, `:472`
- Modify: `docs/JRAG-CLI.md:472`, `:505`
- Modify: `docs/AGENT-GUIDE.md:15`, `:208`, `:210`
- Modify: `docs/MANUAL-VERIFICATION-CHECKLIST.md:137`
- Modify: `docs/PRODUCT-VISION.md:45`, `:350`
- Modify: `README.md:130`

**Interfaces:**
- Consumes: the finished behavior of Tasks 1–7.
- Produces: docs describing the target state — no doc claims SQL/YAML indexing, `--table`, or 3 Lance tables.

- [ ] **Step 1: Edit each doc**

DESIGN.md: "What it indexes" reduces to one row — JVM production sources (`.java`/`.kt`) → Lance chunks + graph Symbols; add non-goal "Not a config/migration file indexer — read SQL/YAML files directly." ARCHITECTURE.md: input line drops `db/migration/*.sql · application*.yml`; stores section names 1 Lance table; key-constants row says 1 table. CODEBASE_REQUIREMENTS.md: §A.6 states sources-only with SQL/YAML/`.properties`/XML read directly; delete the §B.5 add-file-types recipe entirely; update the gap row to "not indexed by design". CONFIGURATION.md: drop the FTS-reprocess sql/yaml phrasing and the graph-only sql/yaml caveat. JRAG-CLI.md: remove `--table` from the flag reference and the `--table all` example. AGENT-GUIDE.md: indexed-content line = JVM sources only; remove the `table` param row; add guidance that config/migrations are read directly from the files (file-always-wins). MANUAL-VERIFICATION-CHECKLIST.md: tables check expects `javacodeindex_java_code` only. PRODUCT-VISION.md and README.md: update their mentions/examples.

- [ ] **Step 2: Verify no stragglers**

Run: `grep -rn "java/sql/yaml\|--table\|sqlschemaindex\|yamlconfigindex" docs README.md --exclude-dir=specs --exclude-dir=superpowers --exclude-dir=paper`
Expected: no matches (historical specs/plans under `docs/specs/` and `docs/superpowers/` are excluded — they are records).

- [ ] **Step 3: Commit**

Run: `git add docs/ README.md`
Run: `git commit -m "docs: sources-only indexing — remove sql/yaml mentions across operator and internal docs"`

---

### Task 9: HEAVY integration, full suite, final sweep

**Files:**
- Test: `tests/integration/test_vectors_progress.py` (HEAVY assertions `:329-339`; mocked tests' table expectations)
- Test: `tests/integration/test_lancedb_e2e.py` (HEAVY MCP search e2e)

**Interfaces:**
- Consumes: everything from Tasks 1–8.
- Produces: a green full suite + HEAVY suite on the finished change; release-notes text is carried by the spec (§ Release) — no repo file to edit.

- [ ] **Step 1: Update the HEAVY tests**

`test_vectors_progress.py`: the HEAVY real-cocoindex test asserts all three tables exist and distinct-filename count equals the pre-walk total — change to: exactly one table (`javacodeindex_java_code`) exists, and distinct-filename count equals the **source-file** total (the fixture's `.sql`/`.yml` files are present on disk but uncounted). Update the non-HEAVY mocked tests in the same file wherever they enumerate the table set. `test_lancedb_e2e.py`: the HEAVY MCP `search` e2e over the corpus asserts hits — update to assert java-source hits only (no sql/yaml filenames can appear).

- [ ] **Step 2: Ritual + full suite**

Run: `rm -rf tests/*/.java-codebase-rag tests/*/.java-codebase-rag.{yml,hosts}`
Run: `.venv/bin/python -m pytest -q`
Expected: PASS, zero failures.

- [ ] **Step 3: HEAVY suite**

Run: `rm -rf tests/*/.java-codebase-rag tests/*/.java-codebase-rag.{yml,hosts}` then `JAVA_CODEBASE_RAG_RUN_HEAVY=1 .venv/bin/python -m pytest tests/integration -q`
Expected: PASS.

- [ ] **Step 4: Final straggler sweep**

Run: `grep -rn "sqlschemaindex\|yamlconfigindex\|process_sql_file\|process_yaml_file\|SQL_CHUNK\|YAML_CHUNK\|_is_migration_sql\|_is_application_yaml" src tests README.md docs --exclude-dir=specs --exclude-dir=superpowers --exclude-dir=paper`
Expected: no matches. Also `grep -rn "table_keys\|args.table" src tests` → no matches.

- [ ] **Step 5: Commit**

Run: `git add tests/integration/`
Run: `git commit -m "test(integration): single-table HEAVY assertions; suite green"`
