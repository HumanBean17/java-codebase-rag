# Capability-Absent Structural Empty Signaling — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tell agents that an empty edge-type/node-kind query is structural (zero edges index-wide) — `correct_empty`/`capability_absent` with a fact + expectation + redirect message — instead of today's `refine_query` retry bait; list zero-edge types in connect-time MCP instructions.

**Architecture:** The build-time `counts_json` on the `GraphMeta` node already records per-edge-type and per-node-kind totals. A new pure-predicate module (`absence_capability.py`) interprets those counts; `diagnose()` gains an `edge_types` kwarg and a capability step (precedence: external → capability → node-level); `mcp_v2` passes edge types on empty neighbors and injects a zero-set into the hints payload; the Row 4 hint advisory is replaced when structural; server instructions gain a zero-edge-type sentence. Everything reads, nothing writes — no schema change, no rebuild.

**Tech Stack:** Python 3.10+ (repo `.venv`), pydantic v2 models, pytest with session-scoped LadybugDB fixtures, FastMCP.

## Global Constraints

- Python: always `.venv/bin/python` / `.venv/bin/pytest` from repo root. Never system `python`/`pip`.
- Before test runs: `rm -rf tests/*/.java-codebase-rag tests/*/.java-codebase-rag.yml tests/*/.java-codebase-rag.hosts` (stale manual indexes hijack project-root discovery).
- Never commit anything under `tests/*/.java-codebase-rag*`.
- Run only the task-relevant test subset during development; run the full suite once, at the end.
- No graph schema changes, no `ONTOLOGY_VERSION` bump, no new config knobs; `counts_json` is consumed read-only.
- **Fail-open contract (verbatim from spec D3/D4):** `capability_absent` may be emitted only when the GraphMeta counts read succeeded AND every requested stored edge label maps to a counts key that is present with value 0 (for `find`: the kind's node-count key present with value 0). Unreadable meta, missing key, or unknown label → skip the capability check and fall through to existing behavior.
- Agent-facing message/advisory/instruction text must NOT contain the strings `reindex`, `annotat`, or `@Codebase` (operator territory, per spec D6).
- If `jrag`/`java-codebase-rag` serve stale behavior while pytest passes: run `.venv/bin/pip install -e ".[dev]"` — don't report it.
- On-disk names `.java-codebase-rag*` and env vars `JAVA_CODEBASE_RAG_*` are backward-compat — do not touch.
- Work happens on branch `feat/capability-absent` (already holds the spec commits).

---

### Task 1: Capability predicates — pure functions over the counts dict

**Files:**
- Create: `src/java_codebase_rag/absence/absence_capability.py`
- Modify: `src/java_codebase_rag/absence/absence_types.py:27` (`AbsenceCause` literal)
- Test: `tests/absence/test_absence_capability.py` (new)

**Interfaces:**

Produces (consumed by Tasks 2, 3, 4, 5, 6):

- `EDGE_COUNT_KEYS: dict[str, str]` — stored edge label → `counts_json` key, exactly:
  `EXTENDS→extends, IMPLEMENTS→implements, INJECTS→injects, DECLARES→declares, OVERRIDES→overrides, CALLS→calls, EXPOSES→exposes, DECLARES_CLIENT→declares_client, DECLARES_PRODUCER→declares_producer, HTTP_CALLS→http_calls, ASYNC_CALLS→async_calls` (11 entries).
- `KIND_COUNT_KEYS: dict[str, str]` — `{"client": "clients", "producer": "producers", "route": "routes"}`.
- `decompose_edge_types(edge_types: list[str]) -> list[str]` — each entry: an exact stored label (key of `EDGE_COUNT_KEYS`) passes through; `DECLARES.X` or `OVERRIDDEN_BY.X` → terminal label `X`; anything else (unknown label or unknown terminal) is dropped. Dispatch hops (`DECLARES`, `OVERRIDES`) never appear in the output.
- `zero_edge_types(counts: dict) -> set[str]` — stored labels whose `EDGE_COUNT_KEYS` key exists in `counts` with `int(value) == 0`. Labels with a *missing* key are excluded (fail-open).
- `requested_types_absent(edge_types: list[str], counts: dict) -> bool` — decompose `edge_types`; True iff the decomposed set is non-empty AND every label's count key is present AND equals 0. Empty set (all unknown), any missing key, or any non-zero → False.
- `kind_node_count(kind: str | None, counts: dict) -> int | None` — `KIND_COUNT_KEYS.get(kind)`; return `int(counts[key])` if the key exists in counts, else `None`. Unknown kind (`symbol`, `None`, anything) → `None`.
- `AbsenceCause` (in `absence_types.py`) gains the literal `"capability_absent"`; the existing five literals are unchanged.

- [ ] **Step 1: Write the failing tests**

New file `tests/absence/test_absence_capability.py`. Scenarios (plain dicts, no graph):

1. `EDGE_COUNT_KEYS` covers exactly the 11 stored labels listed above (set equality against a literal list in the test).
2. `decompose_edge_types(["HTTP_CALLS"]) == ["HTTP_CALLS"]`; `["DECLARES.DECLARES_CLIENT", "ASYNC_CALLS"] == ["DECLARES_CLIENT", "ASYNC_CALLS"]`; `["OVERRIDDEN_BY.EXPOSES"] == ["EXPOSES"]`; `["NOT_AN_EDGE", "DECLARES.BOGUS"] == []`; mixed `["HTTP_CALLS", "CALLS"]` → both.
3. `requested_types_absent`: with `{"http_calls": 0, "async_calls": 0, "calls": 812}` → `["HTTP_CALLS"]` True, `["HTTP_CALLS","ASYNC_CALLS"]` True, `["HTTP_CALLS","CALLS"]` False; with `{"declares_client": 0, "declares": 9}` → `["DECLARES.DECLARES_CLIENT"]` True (dispatch hop ignored); with counts missing the `http_calls` key → `["HTTP_CALLS"]` False (fail-open); `["NOT_AN_EDGE"]` False.
4. `zero_edge_types({"calls": 5, "http_calls": 0}) == {"HTTP_CALLS"}`; `{"calls": 5}` → empty set (missing key not zero).
5. `kind_node_count`: `("client", {"clients": 0}) == 0`; `("route", {"routes": 4}) == 4`; `("producer", {"routes": 4}) is None` (missing key); `("symbol", {...}) is None`.
6. `AbsenceCause` accepts `"capability_absent"`: assert it is in the Literal's `__args__` (import from `absence_types`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/absence/test_absence_capability.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named '...absence_capability'`.

- [ ] **Step 3: Write minimal implementation**

Create `absence_capability.py` with the six contracts above. Pure functions over dicts — no I/O, no imports beyond stdlib `json` (used by Task 2) and typing. Add `"capability_absent"` to the `AbsenceCause` Literal in `absence_types.py` (keep alphabetical-ish ordering consistent with the file's style).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/absence/test_absence_capability.py tests/absence/test_absence_types.py -v`
Expected: PASS (including the pre-existing types tests — no literal regression).

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/absence/absence_capability.py src/java_codebase_rag/absence/absence_types.py tests/absence/test_absence_capability.py`
Run: `git commit -m "feat(absence): capability predicates over build-time counts + capability_absent cause"`

---

### Task 2: Counts accessor — light GraphMeta row read with built_at cache

**Files:**
- Modify: `src/java_codebase_rag/absence/absence_capability.py`
- Test: `tests/absence/test_absence_capability.py`

**Interfaces:**

Consumes: Task 1 module (same file).

Produces (consumed by Tasks 3, 4, 6):

- `get_capability_counts(graph: Any) -> dict[str, int] | None` — executes `MATCH (m:GraphMeta) RETURN m.counts_json AS cj, m.built_at AS built_at` via `graph._rows(query)` (module-private access with `# noqa: SLF001`, same precedent as `_neighbors_meaningful_empty` in `absence_diagnosis.py:462`). Returns the parsed counts dict, or `None` on: exception, empty rows, missing `counts_json`, unparseable JSON, or a non-dict parse result.
- Module-level cache `_counts_cache: dict[str, tuple[int, dict]]` keyed by `str(graph.db_path)` holding `(built_at, counts)`. Every call performs the (cheap, single-row) query; if the cached `built_at` equals the row's, return the cached dict object; otherwise parse and store. Failures return `None` and never write the cache.
- `clear_capability_cache() -> None` — test hook emptying `_counts_cache` (mirrors the reset pattern at `absence_vocab.py:402`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/absence/test_absence_capability.py`. Use a stub graph class with a `db_path: str` attribute and a `_rows(self, query, params=None)` method returning canned rows (settable per-test):

1. Row `{"cj": '{"calls": 3, "http_calls": 0}', "built_at": 7}` → returns `{"calls": 3, "http_calls": 0}`.
2. Cache identity: call twice with unchanged `built_at` → the second return **is** the first return object (`is` assertion); then change canned `built_at` to 8 with new JSON → third call returns the freshly parsed dict.
3. Fail-open to `None`: rows `[]`; row without `cj`; `cj` = `"not json{"`; `_rows` raising an exception.
4. `clear_capability_cache()` empties the cache (next call re-parses even with same `built_at` — assert via a fresh object identity or by counting `_rows` calls).
Call `clear_capability_cache()` in a fixture/`setup` so tests are order-independent.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/absence/test_absence_capability.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_capability_counts'`.

- [ ] **Step 3: Write minimal implementation**

Extend `absence_capability.py` with the accessor + cache + clear hook per the contracts above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/absence/test_absence_capability.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/absence/absence_capability.py tests/absence/test_absence_capability.py`
Run: `git commit -m "feat(absence): get_capability_counts accessor with built_at-keyed cache"`

---

### Task 3: `diagnose()` capability step — kwarg, precedence, message

**Files:**
- Modify: `src/java_codebase_rag/absence/absence_diagnosis.py` (`diagnose` at :73, `_diagnose_inner` at :115)
- Test: `tests/absence/test_absence_diagnosis.py`

**Interfaces:**

Consumes: `get_capability_counts`, `requested_types_absent`, `kind_node_count`, `decompose_edge_types` from Task 1/2; existing `AbsenceDiagnosis`.

Produces (consumed by Task 4; also the agent-facing contract):

- `diagnose(*, tool, query, filt, filter_kind, root_node, scope, vocab, graph, cfg, edge_types: list[str] | None = None)` — one new keyword-only param, default `None`; threaded into `_diagnose_inner`. Existing call sites compile unchanged.
- Import style: `absence_diagnosis.py` imports `get_capability_counts` (and the predicates) into its module namespace so tests can monkeypatch `java_codebase_rag.absence.absence_diagnosis.get_capability_counts`.
- New step in `_diagnose_inner`, placed **after** the external-detection block (:128-138) and **before** the `root_node` branch (:140):
  - `counts = get_capability_counts(graph)`; `None` → skip (fail-open, zero behavior change).
  - `tool == "neighbors"` and `edge_types` non-empty and `requested_types_absent(edge_types, counts)` → return the capability diagnosis.
  - `tool == "find"` and `filter_kind` set and `kind_node_count(filter_kind, counts) == 0` → return the capability diagnosis. Fires regardless of filter values (spec D5). `kind="symbol"` can never fire (`kind_node_count` returns `None`).
- Capability diagnosis shape: `AbsenceDiagnosis(verdict="correct_empty", cause="capability_absent", message=_capability_message(...))`; no other fields.
- `_capability_message(subject: str, redirect_labels: list[str]) -> str` (module-private):
  - `subject` for neighbors: the absent stored labels joined `" / "` (e.g. `HTTP_CALLS`, `HTTP_CALLS / ASYNC_CALLS`); for find: `"<Kind> nodes"` (e.g. `Client nodes`).
  - Required content, in order: (1) `"This index contains 0 <subject>..."`; (2) `"Any query on <subject> returns empty regardless of arguments — don't retry it."`; (3) a redirect sentence naming `redirect_labels` (backticked, comma-joined) as what to use instead.
  - `redirect_labels`: up to 3 labels from `["CALLS", "EXPOSES", "DECLARES", "INJECTS"]` that are non-zero in `counts`, in that preference order; if none are non-zero, the redirect sentence says to use `find`/`search` for symbols instead.
  - Banned strings (Global Constraints): `reindex`, `annotat`, `@Codebase`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/absence/test_absence_diagnosis.py`. All new tests monkeypatch `java_codebase_rag.absence.absence_diagnosis.get_capability_counts` to return synthetic dicts (mirror the file's existing `_diagnose(**overrides)` helper; pass `edge_types` through it). Build a `NodeRef` for root_node cases as the existing tests do:

1. **neighbors structural**: `tool="neighbors"`, `root_node=<method-symbol NodeRef>`, `edge_types=["HTTP_CALLS"]`, counts `{"http_calls": 0, "calls": 812}` → `verdict == "correct_empty"`, `cause == "capability_absent"`, message contains `"0 HTTP_CALLS"`, `"regardless of arguments"`, `"don't retry"`, and `"CALLS"` (redirect); message does not contain `"reindex"` or `"annotat"`.
2. **mixed list not structural**: same but `edge_types=["HTTP_CALLS", "CALLS"]` → `cause != "capability_absent"` (falls to node-level path; assert the verdict is whatever the node-level path yields, i.e. refine_query or correct_empty/meaningful_empty).
3. **fail-open**: counts patched to return `None` → `cause != "capability_absent"`.
4. **external wins**: `root_node` with `kind="unresolved_call_site"` and counts with everything zero → `verdict == "external_dependency"`.
5. **find structural**: `tool="find"`, `filter_kind="client"`, `filt={"target_path_contains": "x"}`, counts `{"clients": 0, "calls": 5}` → `correct_empty`/`capability_absent`, message contains `"0 Client nodes"`.
6. **find symbol never structural**: `filter_kind="symbol"`, counts `{"clients": 0}` → `cause != "capability_absent"`.
7. **composed key**: `edge_types=["DECLARES.DECLARES_CLIENT"]`, counts `{"declares_client": 0, "calls": 3}` → capability_absent with subject containing `DECLARES_CLIENT`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/absence/test_absence_diagnosis.py -v -k capability`
Expected: FAIL — `TypeError: diagnose() got an unexpected keyword argument 'edge_types'` (or assertion failure since the branch doesn't exist).

- [ ] **Step 3: Write minimal implementation**

Add the `edge_types` kwarg, the import of Task 1/2 names, the capability step in `_diagnose_inner` at the specified position, and `_capability_message` per the contracts above.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/absence/test_absence_diagnosis.py tests/absence/test_absence_mcp_integration.py -v`
Expected: PASS — including all pre-existing absence tests (the new step is invisible when `edge_types` is None or counts are real on bank-chat, which has clients).

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/absence/absence_diagnosis.py tests/absence/test_absence_diagnosis.py`
Run: `git commit -m "feat(absence): capability_absent step in diagnose() (external > capability > node-level)"`

---

### Task 4: MCP wiring + client-less integration fixture

**Files:**
- Modify: `src/java_codebase_rag/mcp/mcp_v2.py:1859-1884` (neighbors empty branch)
- Modify: `tests/conftest.py` (new session fixtures, mirror the pattern at :201-219)
- Test: `tests/absence/test_absence_mcp_integration.py`

**Interfaces:**

Consumes: `neighbors_v2` / `find_v2` signatures as used by existing tests in the integration file (direct call with `graph=` kwarg); Task 3 `edge_types` kwarg; `get_capability_counts`.

Produces:

- `neighbors_v2` empty branch passes `edge_types=requested_edge_types` into `diagnose(...)`. Non-empty results: unchanged (diagnosis not called).
- conftest fixtures: `ladybug_db_path_capability_absent` — session-scoped, builds LadybugDB from `tests/fixtures/call_graph_smoke` via `build_ladybug_to(root, db_path, max_pass=6)` (full pass range so client/route passes run and their zero counts are genuine); `ladybug_graph_capability_absent` — wraps that path in `LadybugGraph(str(db_path))` (mirror `ladybug_graph_route_extraction_smoke`, conftest.py:216).

- [ ] **Step 1: Write the failing tests**

Append to `tests/absence/test_absence_mcp_integration.py`, using the new `ladybug_graph_capability_absent` fixture:

1. **Fixture sanity guard** (first test): `get_capability_counts(ladybug_graph_capability_absent)` is not `None`, has `http_calls == 0`, `async_calls == 0`, `clients == 0`, and `calls > 0`. If this fails, the fixture grew HTTP clients — swap the fixture directory, don't relax the assert.
2. **neighbors structural end-to-end**: acquire any Symbol id from the graph (mirror how existing neighbors tests in this file obtain ids — `find_v2(kind="symbol", graph=...)` first hit is fine); `neighbors_v2(ids=[that_id], direction="out", edge_types=["HTTP_CALLS"], graph=fixture)` → `out.results == []`, `out.absence.verdict == "correct_empty"`, `out.absence.cause == "capability_absent"`, message contains `"don't retry"`.
3. **neighbors non-structural on same index**: same id, `edge_types=["CALLS"]` chosen so this node yields empty (e.g. a symbol with no outbound CALLS; if every symbol has calls, use `["DECLARES"]` on a method symbol) → `cause != "capability_absent"` (node-level path).
4. **find structural**: `find_v2(kind="client", graph=fixture)` → empty results, `absence.cause == "capability_absent"`, message contains `"0 Client nodes"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/absence/test_absence_mcp_integration.py -v -k capability`
Expected: FAIL — test 2/4 assertions on `absence.cause` (the kwarg isn't wired yet, so neighbors yields the old `refine_query`; find isn't wired to pass anything new — note `find` needs no code change in `mcp_v2` since `filter_kind` already flows; only the neighbors call site changes).

- [ ] **Step 3: Write minimal implementation**

In `mcp_v2.py` neighbors empty branch, add `edge_types=requested_edge_types` to the `diagnose(...)` call. Add the two conftest fixtures.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/absence/test_absence_mcp_integration.py tests/mcp/test_mcp_v2.py -v`
Expected: PASS (bank-chat MCP tests unaffected — counts are real and non-zero for clients there).

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/mcp/mcp_v2.py tests/conftest.py tests/absence/test_absence_mcp_integration.py`
Run: `git commit -m "feat(mcp): neighbors passes edge_types to diagnose; client-less integration fixture"`

---

### Task 5: Hints payload key + Row 4 advisory replacement

**Files:**
- Modify: `src/java_codebase_rag/mcp/mcp_v2.py` (neighbors `neigh_payload` dict, ~:1877-1891)
- Modify: `src/java_codebase_rag/mcp/mcp_hints.py:664-670` (Row 4 block)
- Test: `tests/mcp/test_mcp_hints.py`

**Interfaces:**

Consumes: `zero_edge_types`, `get_capability_counts` from Task 1/2; `generate_hints("neighbors", payload)` (existing entry point used by the tests).

Produces:

- `neigh_payload` gains `"zero_edge_types"`: on the empty-results path only (`not sliced`), computed as `sorted(zero_edge_types(counts))` when `get_capability_counts(graph)` returns a dict, else `[]`. Non-empty results path: key omitted (hints layer treats missing as `[]` via `payload.get`).
- Row 4 block in `mcp_hints.py`: read `zero_types = payload.get("zero_edge_types") or []`; when the requested brownfield-resolver-sourced edge that would trigger Row 4 is in `zero_types`, append instead of today's text the replacement advisory: `"edges on '<EDGE>' number 0 index-wide — this empty is structural, not a query problem; don't retry"` (with `<EDGE>` the actual label). Payload without the key, or with the edge not in the set → today's advisory text, unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/mcp/test_mcp_hints.py`, mirroring the existing `generate_hints("neighbors", payload)` style (e.g. `test_structured_hint_neighbors_empty_wrong_kind` at :928). Payload: `results=[]`, `requested_edge_types=["HTTP_CALLS"]`, `requested_direction="out"`, `offset=0`, `subject_record={"client_kind": "feign", ...}` (a `client_kind` key makes `_subject_node_label` return `"Client"` — see `mcp_hints.py:198-205`; pad with the fields existing neighbors-empty tests use):

1. Payload **with** `zero_edge_types=["HTTP_CALLS"]` → advisories contain a string with `"index-wide"` and `"structural"`; no advisory contains `"may mean unresolved"`.
2. Payload **without** the key → advisories contain today's text (`"may mean unresolved"`).
3. Payload with `zero_edge_types=["ASYNC_CALLS"]` (edge not in set) → today's text.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/mcp/test_mcp_hints.py -v -k "row4 or structural or zero"`
Expected: FAIL — test 1 (replacement not implemented; today's text emitted).

- [ ] **Step 3: Write minimal implementation**

`mcp_v2.py`: inject `zero_edge_types` into `neigh_payload` per contract. `mcp_hints.py`: Row 4 branch reads the payload key and swaps the advisory text per contract.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/mcp/test_mcp_hints.py -v`
Expected: PASS — including all pre-existing hint tests (payloads without the key are unchanged).

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/mcp/mcp_v2.py src/java_codebase_rag/mcp/mcp_hints.py tests/mcp/test_mcp_hints.py`
Run: `git commit -m "feat(hints): structural Row 4 advisory when edge type is zero index-wide"`

---

### Task 6: Dynamic connect-time instructions

**Files:**
- Modify: `src/java_codebase_rag/mcp/server.py:47-57` (`_INSTRUCTIONS`), `:607-610` (`create_mcp_server`)
- Test: `tests/mcp/test_mcp_instructions.py` (new)

**Interfaces:**

Consumes: `zero_edge_types`, `get_capability_counts` from Task 1/2; `LadybugGraph.exists()` / `LadybugGraph.get()` acquisition pattern from `_graph_meta_output` (server.py:248-257).

Produces:

- `_build_instructions(zero_types: list[str] | None) -> str` — pure function (parameter deliberately not named `zero_edge_types`, which would shadow the imported predicate): when the list is `None` or empty, returns the current `_INSTRUCTIONS` string **byte-identical**; otherwise returns `_INSTRUCTIONS` + one space-joined appended sentence: `"Zero-edge types in this index (always return empty — don't query): \`<A>\`, \`<B>\`."` where `<A>/<B>` are the sorted labels, backticked, comma-space-joined.
- `create_mcp_server()`: before constructing `FastMCP`, resolve the zero list — if `LadybugGraph.exists()`, `try: graph = LadybugGraph.get(); counts = get_capability_counts(graph); zero = sorted(zero_edge_types(counts)) if counts else []` / `except Exception: zero = []`; else `zero = []` — then `FastMCP("java-codebase-rag", instructions=_build_instructions(zero))`. `FastMCP` exposes the value as `.instructions` (verified).

- [ ] **Step 1: Write the failing tests**

New file `tests/mcp/test_mcp_instructions.py`:

1. `_build_instructions(None) == _INSTRUCTIONS` and `_build_instructions([]) == _INSTRUCTIONS` (exact equality).
2. `_build_instructions(["ASYNC_CALLS", "HTTP_CALLS"])` starts with `_INSTRUCTIONS`, contains `"Zero-edge types in this index"`, contains `` "`ASYNC_CALLS`, `HTTP_CALLS`" `` (sorted, backticked), and contains `"don't query"`.
3. Built sentence contains none of the banned strings (`reindex`, `annotat`, `@Codebase`).
4. Wiring smoke: monkeypatch `LadybugGraph.exists` → True and `LadybugGraph.get` → an object whose `_rows` returns `[{"cj": '{"http_calls": 0, "calls": 5}', "built_at": 1}]` with a `db_path` attribute (reuse the Task 2 stub-graph shape); call `create_mcp_server()`; assert `"Zero-edge types" in mcp.instructions`. Also monkeypatch `exists` → False in a second test and assert `mcp.instructions == _INSTRUCTIONS`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/mcp/test_mcp_instructions.py -v`
Expected: FAIL — `ImportError: cannot import name '_build_instructions'`.

- [ ] **Step 3: Write minimal implementation**

Add `_build_instructions` and the `create_mcp_server` wiring per contracts. Keep `_INSTRUCTIONS` as a module constant (untouched text).

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/mcp/ -v`
Expected: PASS across the MCP test directory.

- [ ] **Step 5: Commit**

Run: `git add src/java_codebase_rag/mcp/server.py tests/mcp/test_mcp_instructions.py`
Run: `git commit -m "feat(mcp): zero-edge-type list in connect-time instructions"`

---

### Task 7: Documentation

**Files:**
- Modify: `docs/AGENT-GUIDE.md:280` (recovery-playbook row "Empty `neighbors`")
- Modify: `docs/ARCHITECTURE.md:35` (module map row "Hints + absence")

**Interfaces:**

Consumes: final message/advisory wording from Tasks 3-6.

Produces: operator/agent-facing doc text only.

- [ ] **Step 1: Update AGENT-GUIDE recovery playbook**

In the "Empty `neighbors`" row, extend the `absence.verdict` parenthetical: after `correct_empty` → `the zero is correct`, add `; cause=capability_absent → this index contains 0 edges/nodes of that type — structural, stop and use the message's suggested alternatives instead of retrying`. Run `grep -n "correct_empty" docs/AGENT-GUIDE.md` and apply the same one-clause extension to any other row that enumerates the verdicts (the "Cannot find symbol" and "Empty `search`" rows point back to this row — they need no change).

- [ ] **Step 2: Update ARCHITECTURE module map**

Add `absence_capability.py` to the "Hints + absence" module list at `docs/ARCHITECTURE.md:35` (comma-joined, file order preserved).

- [ ] **Step 3: Verify no shipped-artifact drift**

Run: `grep -rn "correct_empty" skills/ agents/` — confirmed empty today; if it ever hits, sync those copies verbatim in this repo (they deploy as-is).

- [ ] **Step 4: Commit**

Run: `git add docs/AGENT-GUIDE.md docs/ARCHITECTURE.md`
Run: `git commit -m "docs: capability_absent cause in AGENT-GUIDE playbook + ARCHITECTURE module map"`

---

### Task 8: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Clean stale manual indexes**

Run: `rm -rf tests/*/.java-codebase-rag tests/*/.java-codebase-rag.yml tests/*/.java-codebase-rag.hosts`

- [ ] **Step 2: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS, zero failures. Fix any fallout from the new `edge_types` kwarg or the hint payload key (fail-open contracts mean the blast radius should be nil; if a test pins old behavior contradicted by this design, update the test to the new contract — do not weaken fail-open paths).

- [ ] **Step 3: Sanity-check the CLI surface**

Run: `.venv/bin/jrag --help` (or the repo's canonical smoke command from `docs/JRAG-CLI.md`) — confirms no import-time breakage from the absence/server changes.

- [ ] **Step 4: Commit any fallout fixes**

Run: `git add -A && git commit -m "test: full-suite fallout fixes for capability-absent"` (only if Step 2 produced fixes; otherwise skip).
