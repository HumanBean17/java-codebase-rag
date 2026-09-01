# Drop SQL/YAML vector indexing — sources only

**Status:** draft

## Context

jrag is a navigation layer for JVM systems: a deterministic tree-sitter graph
plus hybrid vector retrieval over **source files**. Today the vector side also
chunks and embeds two non-source file classes:

- SQL — Flyway migrations (`**/src/main/resources/db/migration/*.sql`) →
  `sqlschemaindex_sql_schema`
- YAML — Spring config (`**/src/main/resources/application*.yml|.yaml`) →
  `yamlconfigindex_yaml_config`

These never touch the navigation layer. The graph has no SQL or YAML node
kinds and no edges joining them to Java (no migration↔entity, no
`@Value`↔config-key links); `iter_source_files()` walks registered language
backends (`.java`/`.kt`) only. The two tables are pure generic file RAG —
text + embedding — which host agents already do better by grepping and reading
the files directly. `db/migration` and `application*.yml` are small,
conventionally-located file sets where deterministic grep beats embeddings,
and DDL/keys are not natural language. DESIGN.md's non-goal line already draws
this boundary elsewhere ("Not a test/build/CI indexer — read those files
directly"); SQL/YAML is an inconsistent carve-out from an earlier generic-RAG
phase. In the hybrid `search` fusion, SQL/YAML rows enter only via the
dense-vector list (BM25 and graph-expand are Symbol-only), so they mostly
dilute an identifier-anchored ranking.

Supporting inventory facts:

- **No config knob exists.** The file-type decision is hardcoded in three
  mirrored places — the flow's `walk_dir` matchers, the pre-walk predicates in
  `_approximate_vectors_total`, and the watcher's classification predicates
  (`watcher.py`) — plus a docs mirror. It was never a supported capability.
- SQL/YAML rows are special-cased in ~6 read-path spots (lexical-fallback
  early-returns, graph-only advisories, FQN-dedup passthrough, language
  backfill, `table` enum handling).
- The `table` selector (`Literal["java","sql","yaml","all"]`) is agent-facing:
  MCP `search` input schema, `search_v2`, CLI `jrag search --table`, and the
  daemon protocol all carry it.
- The eval harness is already java-only (`eval/runner.py` searches
  `table_keys=["java"]`); no eval ground truth touches SQL/YAML.

What is honestly lost: fuzzy-semantic discovery of config keys and DDL
fragments ("where is the pool size configured"). That degrades to grep +
direct file reads — acceptable for these file types, and consistent with the
file-always-wins principle.

## Goal

Remove SQL and YAML indexing entirely. The only indexed inputs are JVM
production sources (`.java`/`.kt`); the only vector table is
`javacodeindex_java_code`. The `search` contract becomes single-table with no
`table` selector. Existing indexes are migrated automatically (orphaned tables
dropped on the next pipeline run).

## Non-goals

- No graph/ontology change — nodes, edges, and `ONTOLOGY_VERSION` are
  untouched (graph bytes are identical before and after).
- No new config knob selecting indexed file types (hard removal, not a flag).
- No new file types (`.properties`, Liquibase, XML) — the add-file-types
  extension recipe is removed, not redirected.
- No change to jrag's own configuration files (`.java-codebase-rag.yml`,
  installer host configs) — they are config handling, not indexed content.
- No change to the ignore system (`LayeredIgnore`, builtin patterns) — it
  keeps filtering source files as today.
- Historical specs under `docs/specs/` are records and are not edited.

## Design

### Write path (vectors)

The CocoIndex flow (`index/java_index_flow_lancedb.py`) indexes JVM sources
only. Deleted: the SQL and YAML `walk_dir` blocks, `process_sql_file` /
`process_yaml_file`, `SqlLanceChunk` / `YamlLanceChunk`, the two table mounts
and drains, and the duplicated SQL/YAML predicates inside
`_approximate_vectors_total` (progress counting covers source files only).
`SQL_CHUNK` / `YAML_CHUNK` constants go from
`index/java_index_v1_common.py`. The flow's ignore-context sites drop 4→2
(java, kotlin). `LANCE_TABLE_NAMES` (`lance_optimize.py`) shrinks 3→1; the
optimize loop already treats absent tables as `skipped`.

### Read path (single-table contract)

`table` is removed end to end: MCP `search` input schema, `search_v2`,
`search_payload` / daemon protocol threading, and the CLI
(`jrag search --table` flag; `jrag tables` lists the one remaining table).
Removed SQL/YAML-specific branches: the multi-table fusion in `run_search`,
`_apply_chunk_hints` language backfill, lexical-fallback early-returns,
graph-only advisories, and the hybrid `all` fast-fail. Kind-agnostic
fallbacks that are not provably SQL/YAML-only (e.g. the FQN-less dedup
passthrough in `search_scoring`) stay unless verified dead — no collateral
behavior change to the java path. Stale callers that still pass `table=`
get a loud schema/validation error — honest by design; host agents re-read
MCP schemas each session.

### Watcher

`_classify` loses the `sql`/`yaml` kinds and their predicates
(`_YAML_SUFFIXES`, `_SQL_MIGRATION_PREFIX`, `_RESOURCES_PREFIX`,
`_is_migration_sql`, `_is_application_yaml`). Editing a `.sql`/`.yml`/`.yaml`
file becomes a non-event — no vector or graph reindex, same as editing a
`.md`. This also stops the wasted vector reindexes the old classification
triggered. `_GRAPH_INDEXED_KINDS` is unaffected.

### Migration of existing indexes

Orphaned `.lance` table dirs would otherwise survive even `jrag erase`,
because erase drops tables by listing `LANCE_TABLE_NAMES`:

1. **One-time legacy drop.** The first pipeline run (`init` / `increment` /
   `reprocess`) under the new version detects the two legacy table dirs in
   the index dir and drops them — idempotent, logged once.
2. **`erase` drops by scanning.** `erase` is generalized to drop every
   `*.lance` table found in the index dir by directory scan, not by listing
   the constant — future-proof against any later table removal.

### Compatibility

No `ONTOLOGY_VERSION` bump: the graph and its extraction are byte-identical,
and forcing full graph rebuilds for a vector-only change serves nothing.
CocoIndex's own flow-spec change detection handles the vector rebuild. The
package version bumps; release notes flag the removed MCP field and CLI flag.

### Tests

Existing SQL/YAML assertions are deleted or flipped negative:

- `tests/watch/test_watcher.py` — classification table: `.sql` /
  `application*.yml` → unindexed (∅); the "vectors-only, no snapshot" tests
  become "no reindex at all"; the graph-only no-op test adjusts.
- `tests/search/test_search_lancedb.py` — SQL/YAML dedup and hint-row tests
  removed; the `TABLES` ↔ `LANCE_TABLE_NAMES` parity pin updated to 1 table.
- `tests/search/test_search_lexical.py` — SQL/YAML `[]` assertions removed.
- `tests/mcp/test_mcp_tools.py` — schema asserts no `table` field;
  `test_mcp_v2.py` — the `table="yaml"` happy path removed;
  `tests/package/test_jrag_orientation.py` — the `--table all` routing test
  removed.
- HEAVY `tests/integration/test_vectors_progress.py` — asserts exactly one
  table and a distinct-filename count from source files only;
  `test_lancedb_e2e.py` — ignore-context pin 4→2.
- New contract tests: `init` on the fixture corpus yields exactly one Lance
  table and zero chunks traceable to `.sql`/`.yml` files; a watcher event on
  `.sql`/`.yml` triggers no reindex; orphan cleanup (pre-create the two
  legacy `.lance` dirs → run pipeline → dropped and logged); `erase` drops by
  scan.
- Fixture corpora keep their `.sql`/`.yml` files — realistic repos contain
  unindexed files, and the negative assertions depend on them.

### Docs

- `docs/DESIGN.md` — "What it indexes" reduces to JVM production sources
  (`.java`/`.kt`); add the non-goal "not a config/migration file indexer —
  read SQL/YAML directly".
- `docs/ARCHITECTURE.md` — overview diagram input line; stores section (one
  Lance table); `LANCE_TABLE_NAMES` constants row.
- `docs/CODEBASE_REQUIREMENTS.md` — §A.6 states sources-only (SQL, YAML,
  `.properties`, XML all read directly); §B.5 add-file-types recipe deleted;
  the gap row updated.
- `docs/CONFIGURATION.md` — FTS reprocess note and the graph-only SQL/YAML
  caveat removed.
- `docs/JRAG-CLI.md` — `--table` flag and the `--table all` example removed.
- `docs/AGENT-GUIDE.md` — indexed-content line and `table` param updated;
  add positive guidance: config and migrations → read the files directly
  (file-always-wins).
- `docs/MANUAL-VERIFICATION-CHECKLIST.md` — tables check expects java only.
- `docs/PRODUCT-VISION.md`, `README.md` — mention/example updated.
- `src/java_codebase_rag/prime.py` — orientation line "Semantic search over
  Lance tables" reworded to the singular index.
- Any lingering deployed-artifact copies that still reference `--table`
  (e.g. under `tests/bank-chat-system/.claude/`) are updated or removed if
  still present.

### Release

Version bump; release notes state: SQL/YAML are no longer indexed (grep/read
the files directly), the MCP `search` `table` field and CLI `--table` flag
are removed, and legacy tables are cleaned up automatically on the next
pipeline run. Dual PyPI publish per `.claude/skills/publish-pip/SKILL.md`.
`docs/MIGRATION.md` gets a row only if it references the dropped tables.

## Open Questions

- **Removal depth** — resolved: hard removal, no flag, no two-stage
  deprecation.
- **`search` API contract** — resolved: clean sweep; `table` parameter
  removed everywhere in the same change.
- **Orphaned tables** — resolved: active one-time drop on pipeline run, plus
  `erase` by directory scan.

## TLDR

SQL/YAML indexing is pure generic file RAG bolted onto a JVM navigation layer
— no graph nodes, no edges, hardcoded in three places, dilutive to hybrid
ranking. This spec removes it completely: one vector table over JVM sources
only, `table` selector gone from MCP/CLI/daemon, watcher treats `.sql`/`.yml`
edits as non-events, existing indexes drop the orphaned tables automatically,
no `ONTOLOGY_VERSION` bump. Agents grep/read config and migrations directly.
