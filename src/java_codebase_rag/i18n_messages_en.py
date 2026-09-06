"""English runtime catalog (MSG_/ERR_/LBL_/HINT_ keys).

Values are ``str`` templates (``{placeholder}`` formatting) or, for plural
keys, dicts of forms (en: ``one``/``other``). EN entries are the byte-exact
pre-i18n strings — golden payloads and render tests pin them.
"""
from __future__ import annotations

from typing import Any

MESSAGES: dict[str, Any] = {
    # Bootstrap keys (removed in the operator-CLI task once real keys land).
    "MSG_TEST_GREETING": "index ready",
    "MSG_TEST_PLURAL": {"one": "{n} match", "other": "{n} matches"},
    "LBL_TEST_PREFIX": "Verdict: ",
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
