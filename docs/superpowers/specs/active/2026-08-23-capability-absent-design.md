# Capability-absent: structural empty-result signaling for edge navigation

- **Date:** 2026-08-23
- **Status:** in_progress

## Motivation

Cross-service edges (`HTTP_CALLS`, `ASYNC_CALLS`) and other
brownfield-resolver-sourced edges are annotation-driven by design: they appear
when call sites are declared via brownfield annotations or built-in detection
and resolved against routes. Most real projects carry no such annotations, so
their indexes contain **zero** of these edges. That is the correct product
stance — precision over fabrication.

The failure is in the read path's communication:

- The MCP API surface is **static**: the server instructions
  (`server.py:_INSTRUCTIONS`) advertise all 12 edge labels unconditionally;
  `docs/EDGE-NAVIGATION.md` and `docs/AGENT-GUIDE.md` document cross-service
  traversal as a first-class capability.
- When an agent queries one of these edge types it gets an empty result whose
  `absence` diagnosis is almost always `verdict=refine_query`
  (`absence_diagnosis.py:_diagnose_neighbors`) — "inspect `edge_summary`",
  i.e. *your query may be wrong, try again*. Agents treat empty results as a
  query problem and retry with variations, burning calls on a query that can
  never succeed.
- The hints layer makes it worse: the Row 4 advisory on empty
  brownfield-resolver-sourced edges (`mcp_hints.py:664-670`) says absence
  "may mean unresolved (no matching annotation/target), not absent from the
  codebase" — actively encouraging further digging.
- Meanwhile the index **already knows the truth**: `GraphMeta` stores
  build-time per-edge-type and per-node-kind counts (`counts_json`,
  `build_ast_graph.py:3940`), `cross_service_resolution`, and match
  breakdowns. Nothing at answer time consults this, and the only surface that
  exposes it (`GraphMetaOutput`, `server.py:60`) is CLI-only (`cli.py:807`).

**Goal of the diagnosis:** make the agent query right and hold correct
expectations about tool output — not coach it into annotating or reindexing
(operator territory, already covered by `docs/CONFIGURATION.md` §4).

## Goal & scope

**Goal.** When a query targets an edge type (or node kind) that structurally
cannot return results in this index, the agent learns it immediately, in
machine-readable form, on both of two surfaces:

1. **Per-call absence diagnosis** (live safety net): `verdict=correct_empty`,
   `cause=capability_absent`, message = fact + expectation + redirect.
2. **Connect-time instructions** (prevention): the MCP server's instructions
   list zero-edge types up front so a well-behaved agent never wastes the
   first call.

**In scope.** New `AbsenceCause` literal; capability check in `diagnose()`;
`edge_types` kwarg; build-time-counts accessor with per-process cache; dynamic
instructions; Row 4 advisory reconciliation; agent-facing doc updates; tests.

**Out of scope.** A new MCP tool; graph schema or `ONTOLOGY_VERSION` changes;
`neighbors` filtering by `attrs.match`; changes to extraction/resolution
itself; refreshing instructions mid-session; the case of
`cross_service_calls_total=0` with non-zero `HTTP_CALLS` (results are
non-empty there — `intra_service` edges are returned — a different problem).

## Decisions

- **D1 — Reuse `correct_empty`, add cause `capability_absent`.** No new
  verdict; consumers already map `correct_empty` → "the zero is correct, stop"
  (`docs/AGENT-GUIDE.md` empty-results row).
- **D2 — Detect from build-time `counts_json`, never live `edge_counts`.**
  `LadybugGraph.meta()` zeroes `edge_counts` on query failure
  (`ladybug_queries.py:604-616`); using it risks false capability-absent
  diagnoses. `counts_json` is written once at build time and is present in
  every meta fallback mode, including legacy graphs.
- **D3 — Fail-open.** Unreadable meta or missing count keys (older indexes)
  → skip the capability check, fall through to today's behavior. The
  catastrophic failure mode is a false "structural absence"; it must be
  impossible. Mirrors the module's existing never-false-absent philosophy.
- **D4 — All-zero rule.** `capability_absent` fires only when **every**
  requested stored edge label (after dot-key decomposition) has count 0. Any
  requested type with edges → the empty is node-specific → existing paths
  unchanged.
- **D5 — `find` generalization.** `find(kind=client|producer|route)` with
  zero nodes of that kind index-wide → same verdict/cause, regardless of
  filter values (no nodes exist for any filter to miss). `kind=symbol` is
  never capability-absent (symbols always exist).
- **D6 — Message = fact + expectation + redirect.** (a) "This index contains
  0 `HTTP_CALLS` edges"; (b) any query on this edge type returns empty
  regardless of arguments — don't retry or vary it; (c) what to use instead,
  derived from which edge types *are* non-zero (e.g. "`EXPOSES` for inbound
  routes, `CALLS` for method-level flow"). No annotation/reindex coaching.
- **D7 — Hints stay payload-pure.** `mcp_v2` injects the computed zero-set
  into the neighbors hint payload; the hints layer remains a pure function of
  its payload (no I/O, no meta reads).

## Detection behavior (core change)

### Capability helper — new `absence/absence_capability.py`

Pure functions over the build-time counts dict; no I/O:

- `zero_edge_types(counts) -> set[str]` — stored edge labels with count 0.
  Feeds the instructions surface and the hints payload.
- `requested_types_absent(edge_types, counts) -> bool` — decomposes composed
  dot-keys to their terminal stored label and applies D4.

  | Requested (example) | Decomposed terminal label(s) |
  | --- | --- |
  | `HTTP_CALLS` | `HTTP_CALLS` |
  | `DECLARES.DECLARES_CLIENT` | `DECLARES_CLIENT` |
  | `DECLARES.EXPOSES`, `OVERRIDDEN_BY.EXPOSES` | `EXPOSES` |
  | `OVERRIDDEN_BY.DECLARES_PRODUCER` | `DECLARES_PRODUCER` |
  | mixed `["HTTP_CALLS","ASYNC_CALLS"]` | both; absent only if both are 0 |

  The dispatch hop (`DECLARES` / `OVERRIDES`) is ignored — a type with no
  members yields an empty result for node-level reasons and the terminal
  label's count is what governs the structural claim.
- `kind_node_count(kind, counts) -> int | None` — `client→clients`,
  `producer→producers`, `route→routes`; `None` for symbol/unknown kinds.

Counts reach callers via a light `GraphMeta` row read (single row: no live
per-edge count queries), cached per process and invalidated by `built_at` so
a reindex refreshes it. Exact accessor shape is plan-level.

### `AbsenceDiagnosis` contract extension

- `AbsenceCause` gains the literal `capability_absent`
  (`absence/absence_types.py`).
- `diagnose()` gains an optional `edge_types: list[str] | None` kwarg
  (additive; only `neighbors` passes it today).

### Precedence in `_diagnose_inner`

1. External-subject detection — unchanged, still wins.
2. **Capability check (new)** —
   `neighbors`: `requested_types_absent(...)`; `find`: D5 rule. Both emit
   `verdict=correct_empty`, `cause=capability_absent`, D6 message.
3. Node-level analysis (`_diagnose_neighbors`) and all remaining paths —
   unchanged.

### Call-site wiring

- `mcp_v2.py` `neighbors` empty branch (~:1859) passes `edge_types`.
- `mcp_v2.py` `find` empty branch (~:1220) relies on existing
  `filt`/`filter_kind`; the helper reads the kind from `filter_kind`.

### Message contract (illustrative)

```json
{
  "verdict": "correct_empty",
  "cause": "capability_absent",
  "message": "This index contains 0 HTTP_CALLS edges — no HTTP client call
             sites were found. Any query on HTTP_CALLS returns empty
             regardless of arguments; don't retry it. For service-to-service
             flow use the edge types this index does have (e.g. EXPOSES for
             inbound routes, CALLS for method-level flow)."
}
```

Exact wording is plan-level; the three elements (fact, expectation,
redirect) and their order are the contract.

## Connect-time instructions

`server.py:_INSTRUCTIONS` becomes a builder over the same counts read:

- Base text unchanged.
- When zero-count edge types exist, one appended sentence:
  *"Zero-edge types in this index (always return empty — don't query):
  `HTTP_CALLS`, `ASYNC_CALLS`."*
- Graph disabled or meta unreadable → byte-identical to today's string.
- Accepted limit: instructions are fixed per connection; a mid-session
  `jrag reprocess` doesn't refresh them until reconnect. The per-call
  diagnosis is the live safety net.

## Hints reconciliation

- `mcp_v2` adds `zero_edge_types` to the neighbors hint payload.
- When the requested brownfield-resolver-sourced edge type is in that set,
  the Row 4 advisory text is **replaced** with the structural one-liner
  ("0 `HTTP_CALLS` edges index-wide — empty is structural"), so the hints and
  absence channels agree instead of contradicting.
- Payload without `zero_edge_types` → Row 4 unchanged (backward-compatible
  with any other payload producer).

## Documentation

- `docs/AGENT-GUIDE.md` empty-results row (~:280): document
  `cause=capability_absent` → "zero edges of this type in this index — stop,
  use the suggested alternative."
- Grep `skills/` and `agents/` for verbatim copies of absence semantics;
  update in this repo (source of truth — deployed copies refresh via
  install/update).
- `docs/ARCHITECTURE.md`: one line in the read-path/absence section.
- `docs/EDGE-NAVIGATION.md`: unchanged (generated from `EDGE_SCHEMA`, which
  does not change).
- `docs/CONFIGURATION.md`: unchanged — no new knobs; the check rides the
  existing `absence_diag_enabled` master toggle.

## Compatibility

No graph schema change, no `ONTOLOGY_VERSION` bump, no rebuild required. The
feature only reads `counts_json`, which every existing index already stores.
Legacy indexes missing newer count keys fail open (D3) to today's behavior.

## Tests

- **Unit** (`tests/absence/`):
  - helper: dot-key decomposition table; all-zero vs. mixed requested lists;
    missing-count-keys fail-open.
  - `diagnose()`: precedence (external → capability → node-level);
    `neighbors` with `edge_types=["HTTP_CALLS"]` on zero-count index →
    `correct_empty`/`capability_absent`; `find(kind="client")` with zero
    clients → same; `kind="symbol"` never capability-absent.
  - instructions builder: appended sentence when zero types exist;
    byte-identical fallback when meta unavailable.
- **Hints** (`tests/mcp/test_mcp_hints.py`): Row 4 replaced when
  `zero_edge_types` present and applicable; unchanged when absent.
- **Integration** (`tests/absence/test_absence_mcp_integration.py` + a graph
  integration test): fresh temp-dir index of a client-less fixture →
  empty `neighbors(..., ["HTTP_CALLS"])` carries the structural diagnosis;
  `find(kind="client")` likewise.
- Repo test rules apply: erase stale manual indexes under `tests/`, run the
  relevant subset during development, full suite once at the end.

## Files touched (design-level)

| File | Change |
| --- | --- |
| `src/java_codebase_rag/absence/absence_types.py` | add `capability_absent` cause literal |
| `src/java_codebase_rag/absence/absence_capability.py` | new: counts predicates + decomposition |
| `src/java_codebase_rag/absence/absence_diagnosis.py` | `edge_types` kwarg; capability step in precedence |
| `src/java_codebase_rag/mcp/mcp_v2.py` | neighbors/find wiring; `zero_edge_types` in hints payload |
| `src/java_codebase_rag/mcp/mcp_hints.py` | Row 4 advisory replacement |
| `src/java_codebase_rag/mcp/server.py` | instructions builder |
| `docs/AGENT-GUIDE.md`, `docs/ARCHITECTURE.md` | agent-facing + internal doc updates |
| `skills/`, `agents/` (if they carry absence semantics) | verbatim sync in-repo |
| `tests/absence/`, `tests/mcp/test_mcp_hints.py` | unit + integration coverage |

## TL;DR

Agents retry empty cross-service edge queries because the read path labels
structural empties as `refine_query`. The index's build-time counts already
know which edge types have zero edges; this change consults them: empty
`neighbors`/`find` results on a structurally-absent edge type or node kind get
`verdict=correct_empty`, `cause=capability_absent`, and a fact + expectation +
redirect message; connect-time instructions list zero-edge types up front; the
contradicting Row 4 hint is reconciled. No schema change, no rebuild, fail-open
on unreadable counts.
