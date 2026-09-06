"""English runtime catalog (MSG_/ERR_/LBL_/HINT_ keys).

Values are ``str`` templates (``{placeholder}`` formatting) or, for plural
keys, dicts of forms (en: ``one``/``other``). EN entries are the byte-exact
pre-i18n strings — golden payloads and render tests pin them.
"""
from __future__ import annotations

from typing import Any

MESSAGES: dict[str, Any] = {
    # Unified dispatcher help section header (byte-exact pre-i18n string).
    "MSG_UNIFIED_OPERATOR_HEADER": (
        "Operator commands (indexing & maintenance; run `jrag <command> --help` "
        "for details):\n"
    ),
    # Absence verdict labels + render prefixes (jrag_render).
    "LBL_ABSENCE_NOT_IN_PROJECT": "not in project",
    "LBL_ABSENCE_EXTERNAL_DEPENDENCY": "external dependency",
    "LBL_ABSENCE_REFINE_QUERY": "refine your query",
    "LBL_ABSENCE_CORRECT_EMPTY": "correct empty",
    "LBL_VERDICT_PREFIX": "Verdict: ",
    "LBL_NEXT_PREFIX": "next: ",
    "LBL_WARNING_PREFIX": "warning: ",
    "LBL_ERROR_PREFIX": "error: ",
    "LBL_ERROR_WORD": "error",
    "LBL_NOT_FOUND_PREFIX": "not found: ",
    "LBL_NOT_FOUND_WORD": "not found",
    # Truncation notices.
    "MSG_TRUNCATED_OFFSET": "truncated: more results — use --offset {offset}",
    "MSG_TRUNCATED_NARROW": "truncated: more results — narrow your query",
    # Did-you-mean (not_found + closest_symbols).
    "MSG_DID_YOU_MEAN_ONE": "Did you mean: {sym}?",
    "MSG_DID_YOU_MEAN_TWO": "Did you mean: {a} or {b}?",
    "MSG_DID_YOU_MEAN_MANY": "Did you mean: {list}?",
    "LBL_OR": ", or {last}",
    # Zero-result lines (listing + traversal).
    "MSG_ZERO_LISTING": "0 {noun}",
    "MSG_EXTERNAL_ENTRYPOINT": "external entrypoint — no in-repo callers",
    # Row labels.
    "LBL_NO_IDENTIFIER": "(no identifier)",
    "LBL_MISSING": "(missing)",
    "LBL_UNRESOLVED": "(unresolved)",
    "LBL_ROOT_PREFIX": "root: ",
    # Grouped-traversal headers.
    "LBL_INBOUND": "inbound:",
    "LBL_OUTBOUND": "outbound:",
    "LBL_SUPERTYPES": "↑ supertypes:",
    "LBL_SUBTYPES": "↓ subtypes:",
    "LBL_STAGE_SEED": "stage 0 (seed):",
    "LBL_STAGE_ROLES": "stage {n} ({roles}):",
    "LBL_STAGE": "stage {n}:",
    # Ambiguous renderer. EN one == other on purpose: the pre-i18n string was
    # "{n} ambiguous matches" for every n; byte-stability outranks grammar.
    "MSG_AMBIGUOUS_HEADER": {
        "one": "{n} ambiguous matches for '{noun}'",
        "other": "{n} ambiguous matches for '{noun}'",
    },
    "MSG_AMBIGUOUS_HEADER_NO_NOUN": {
        "one": "{n} ambiguous matches",
        "other": "{n} ambiguous matches",
    },
    "MSG_NARROW": "Narrow with --kind --java-kind --role --fqn-contains:",
    # Error paths in jrag.main() and authored envelope messages (Task 5).
    "ERR_USAGE_WORD": "usage error",
    "ERR_INTERNAL": "internal error: {exc}",
    "LBL_JRAG_ERROR_STDERR": "jrag: error: ",
    "MSG_INTERRUPTED": "\nInterrupted.\n",
    "MSG_NO_INDEX": "No index at {path}. Run: jrag init --source-root <root>",
    "ERR_INDEX_META_FAILED": "Index meta read failed: {error}",
    "ERR_INVALID_FILTER": "invalid filter: {message}",
    "ERR_DESCRIBE_FAILED": "describe failed",
    "ERR_NEIGHBORS_FAILED": "neighbors_v2 failed",
    "ERR_SEARCH_FAILED": "search failed",
    "ERR_OUTLINE_FAILED": "outline failed: {exc}",
    "ERR_READ_FAILED": "could not read {path}: {exc}",
    "ERR_FILE_NOT_FOUND": (
        "file not found: '{file}' (looked at the literal path and at "
        "<source_root>/{file})"
    ),
    "ERR_NO_BACKEND": (
        "no language backend registered for '{file}' "
        "(suffix '{suffix}' not in registry)"
    ),
    "ERR_INVALID_FRAMEWORK": (
        "invalid framework: '{framework}' (normalized to '{normalized}'); "
        "expected one of: {valid}"
    ),
    "ERR_OVERVIEW_AS_ROUTE": (
        "overview --as route expects a Route; resolved kind is '{kind}'."
    ),
    "MSG_AMBIGUOUS_CANDIDATES": {"one": "{n} candidate", "other": "{n} candidates"},
    # Auto-scope notices (stderr line + envelope warnings[] value).
    "MSG_AUTO_SCOPE_STDERR": "[jrag] auto-scope: --service {svc} (cwd)",
    "WARN_AUTO_SCOPE": (
        "auto-scope: --service {svc} (inferred from cwd; "
        "pass --no-auto-scope to disable)"
    ),
    # Watch lifecycle lines.
    "MSG_WATCH_UP": "jrag watch: up (pid {pid}, socket {sock})",
    "MSG_WATCH_DOWN": "jrag watch: down (no daemon at {sock})",
    "MSG_WATCH_STOPPED": "jrag watch: stopped (pid {pid})",
    "MSG_WATCH_DETACHED": "jrag watch: detached (pid {pid}, socket {sock}, log {log})",
    "MSG_WATCH_CHILD_EXITED": "jrag watch: child exited before serving (see {log})",
    "MSG_WATCH_START_TIMEOUT": "jrag watch: failed to start within {seconds}s (see {log})",
    "MSG_WATCH_LAST_REINDEX": "  last reindex: {kind} at {when} (total {count})",
    "MSG_WATCH_LAST_REINDEX_NONE": "  last reindex: none (total {count})",
    "LBL_WATCH_MODE": "  mode: {label}",
    # vocab-index stderr lines.
    "ERR_VOCAB_STDERR": "[error] {exc}",
    "ERR_VOCAB_BUILD_FAILED": "[error] Vocabulary index build failed: {exc}",
    # Operator CLI: lazy advisory twins of the frozen module constants (the
    # constants stay English forever — MCP consumes them directly; spec D2/D4).
    "MSG_INCREMENT_WARNING": (
        "WARNING: AST graph (LadybugDB) incremental rebuild is not yet implemented.\n"
        "The graph reflects the index state from the last `init` or `reprocess`,\n"
        "which means `find`, `neighbors`, and `describe` may return stale results\n"
        "for files changed since then.\n"
        "\n"
        "Lance vector index has been updated incrementally and is current.\n"
        "\n"
        "For an up-to-date graph, run:\n"
        "    jrag reprocess\n"
        "\n"
        "Track progress on LadybugDB incremental rebuild:\n"
        "    {url}"
    ),
    "MSG_REFRESH_DEPRECATION": (
        "WARN: 'refresh' is deprecated; use 'reprocess'. "
        "This alias will be removed in the next release."
    ),
    "MSG_REPROCESS_DRIFT_VECTORS_ONLY": (
        "jrag reprocess: rebuilt vectors only; graph (code_graph.lbug) was NOT rebuilt "
        "and may now reflect a stale source snapshot."
    ),
    "MSG_REPROCESS_DRIFT_GRAPH_ONLY": (
        "jrag reprocess: rebuilt graph only; vectors (Lance tables under "
        "{index_dir}) were NOT rebuilt and may now reflect a stale source snapshot."
    ),
    "MSG_VECTORS_SKIPPED_GRAPH_ONLY": (
        "jrag: vectors skipped — vector stack not installed on this platform "
        "(graph-only mode). The graph is built/refreshed; semantic search is unavailable."
    ),
    "MSG_VECTORS_SKIPPED_BM25": (
        "jrag: vectors skipped — retrieval mode is bm25; building graph only."
    ),
    "MSG_RETRIEVAL_BM25_HINT": (
        "Tip: can't download the embedding model? Switch to keyword search: "
        "jrag install --retrieval bm25 (or set JAVA_CODEBASE_RAG_RETRIEVAL=bm25) "
        "— indexing and search then work fully offline."
    ),
    "MSG_DEPRECATION_NOTICE": (
        "jrag: 'java-codebase-rag' is now 'jrag'; this alias continues to work. "
        "Set JRAG_NO_DEPRECATION=1 to silence.\n"
    ),
    # Operator erase flow.
    "MSG_ERASE_WILL_DELETE": "Will delete:",
    "MSG_ERASE_NOTHING": "  (nothing to delete under resolved index dir)",
    "MSG_ERASE_CONFIRM": "Delete these paths? [y/N]: ",
    "MSG_ERASE_NON_INTERACTIVE": (
        "jrag erase: non-interactive stdin; pass --yes to confirm."
    ),
    "MSG_ERASE_ABORTED": "Aborted.",
    "MSG_ERASE_COCO_MISSING": (
        "jrag erase: cocoindex CLI not found next to this Python; "
        "skipped `cocoindex drop` — cocoindex.db (if any) was not removed by CocoIndex."
    ),
    "MSG_ERASE_DROPPED": "jrag: erase: dropped Lance tables: {tables}",
    "MSG_WARN_RM_FAILED": "warning: failed to remove {path}: {exc}",
    # Reprocess selective-mode TTY lines.
    "MSG_REBUILT_VECTORS": "Rebuilt: vectors",
    "MSG_SKIPPED_GRAPH": (
        "Skipped: graph (use `jrag reprocess --graph-only` or `reprocess` to refresh)"
    ),
    "MSG_REBUILT_GRAPH": "Rebuilt: graph",
    "MSG_REPROCESS_COMPLETED_VECTORS": "reprocess completed (vectors only; graph not rebuilt)",
    "MSG_REPROCESS_COMPLETED_GRAPH": "reprocess completed (graph only; vectors not rebuilt)",
    "MSG_REPROCESS_COMPLETED": "reprocess completed",
    "MSG_REPROCESS_COMPLETED_BM25": "reprocess completed (graph-only; vectors skipped — retrieval mode is bm25)",
    "MSG_SKIPPED_VECTORS": (
        "Skipped: vectors (use `jrag reprocess --vectors-only` or `reprocess` to refresh)"
    ),
    # Result-kind nouns (EN values are the identity tokens passed at the seam).
    "LBL_NOUN_MATCHES": "matches",
    "LBL_NOUN_CALLERS": "callers",
    "LBL_NOUN_CALLEES": "callees",
    "LBL_NOUN_IMPLEMENTATIONS": "implementations",
    "LBL_NOUN_SUBCLASSES": "subclasses",
    "LBL_NOUN_OVERRIDES": "overrides",
    "LBL_NOUN_OVERRIDDEN_BY": "overridden-by",
    "LBL_NOUN_DEPENDENTS": "dependents",
    "LBL_NOUN_IMPACT": "impact",
    "LBL_NOUN_DECOMPOSE": "decompose",
    "LBL_NOUN_DEPENDENCIES": "dependencies",
    "LBL_NOUN_CONNECTION": "connection",
    "LBL_NOUN_HIERARCHY": "hierarchy",
    "LBL_NOUN_ROUTE": "route",
    "LBL_NOUN_CLIENT": "client",
    "LBL_NOUN_PRODUCER": "producer",
    "LBL_NOUN_TOPIC": "topic",
    "LBL_NOUN_SYMBOL": "symbol",
    "LBL_NOUN_IMPORT": "import",
    "LBL_NOUN_MICROSERVICES": "microservices",
    "LBL_NOUN_MAP": "map",
    "LBL_NOUN_CONVENTIONS": "conventions",
    "LBL_NOUN_OVERVIEW": "overview",
}
