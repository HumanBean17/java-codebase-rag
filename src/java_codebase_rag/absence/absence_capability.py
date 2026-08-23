"""Capability predicates over build-time GraphMeta counts (capability-absent).

Structural empty detection: an MCP query on an edge type (or node kind) whose
build-time count is zero index-wide can never return results. These pure
predicates read the ``counts_json`` dict written at graph build time
(``build_ast_graph.py`` ``counts``) — never the live ``edge_counts`` from
``LadybugGraph.meta()``, which zeroes on query failure and would invite false
capability-absent verdicts.

Fail-open contract (spec D3/D4): a missing counts key is UNKNOWN, never zero;
unknown edge labels never contribute to an absence claim. ``capability_absent``
may be emitted only when the counts read succeeded AND every requested stored
edge label maps to a key present with value 0.
"""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)

__all__ = [
    "EDGE_COUNT_KEYS",
    "KIND_COUNT_KEYS",
    "decompose_edge_types",
    "zero_edge_types",
    "requested_types_absent",
    "kind_node_count",
    "get_capability_counts",
    "clear_capability_cache",
]

# Stored edge label -> counts_json key (build_ast_graph.py:3940 ``counts``).
EDGE_COUNT_KEYS: dict[str, str] = {
    "EXTENDS": "extends",
    "IMPLEMENTS": "implements",
    "INJECTS": "injects",
    "DECLARES": "declares",
    "OVERRIDES": "overrides",
    "CALLS": "calls",
    "EXPOSES": "exposes",
    "DECLARES_CLIENT": "declares_client",
    "DECLARES_PRODUCER": "declares_producer",
    "HTTP_CALLS": "http_calls",
    "ASYNC_CALLS": "async_calls",
}

# find() kind -> counts_json node-count key.
KIND_COUNT_KEYS: dict[str, str] = {
    "client": "clients",
    "producer": "producers",
    "route": "routes",
}

# Composed dot-key prefixes (mcp_v2 / EDGE-NAVIGATION virtual keys): the
# dispatch hop is ignored; the terminal stored label decides the claim.
_DOT_KEY_PREFIXES = ("DECLARES.", "OVERRIDDEN_BY.")


def decompose_edge_types(edge_types: list[str]) -> list[str]:
    """Map requested edge types to stored labels; drop unknowns.

    Exact stored labels pass through. ``DECLARES.X`` / ``OVERRIDDEN_BY.X``
    compose to terminal label ``X`` (the dispatch hop never governs a
    structural-absence claim). Unknown labels and unknown terminals are
    dropped — they cannot support an absence claim.
    """
    out: list[str] = []
    for raw in edge_types:
        etype = str(raw).strip()
        if not etype:
            continue
        for prefix in _DOT_KEY_PREFIXES:
            if etype.startswith(prefix):
                etype = etype[len(prefix):]
                break
        if etype in EDGE_COUNT_KEYS and etype not in out:
            out.append(etype)
    return out


def zero_edge_types(counts: dict) -> set[str]:
    """Stored labels whose counts key exists with value 0.

    Missing keys are excluded (fail-open): an unreadable/absent counter must
    never be read as "this index has none".
    """
    zero: set[str] = set()
    for label, key in EDGE_COUNT_KEYS.items():
        if key in counts:
            try:
                if int(counts[key]) == 0:
                    zero.add(label)
            except (TypeError, ValueError):
                continue
    return zero


def requested_types_absent(edge_types: list[str], counts: dict) -> bool:
    """True iff every requested stored label is present-and-zero in counts.

    Empty decision set (all unknown labels), any missing key, or any non-zero
    count -> False (the empty result is node-specific, not structural).
    """
    labels = decompose_edge_types(edge_types)
    if not labels:
        return False
    for label in labels:
        key = EDGE_COUNT_KEYS[label]
        if key not in counts:
            return False
        try:
            if int(counts[key]) != 0:
                return False
        except (TypeError, ValueError):
            return False
    return True


def kind_node_count(kind: str | None, counts: dict) -> int | None:
    """Node-count for a find() kind, or None when unknown/unreadable."""
    key = KIND_COUNT_KEYS.get(str(kind).strip().lower()) if kind else None
    if key is None or key not in counts:
        return None
    try:
        return int(counts[key])
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------- #
# Counts accessor — light GraphMeta row read with built_at-keyed cache        #
# --------------------------------------------------------------------------- #

# db_path -> (built_at, counts). The single-row GraphMeta read happens on every
# call (cheap); the cache avoids re-parsing counts_json per empty-result call.
# Mirrors the per-process cache pattern of absence_vocab._vocab_cache.
_counts_cache: dict[str, tuple[int, dict]] = {}


def get_capability_counts(graph: Any) -> dict[str, int] | None:
    """Read build-time counts from the GraphMeta node; None on any failure.

    Fail-open: unreadable meta must never support a capability-absent claim.
    Failures do not poison the cache.
    """
    try:
        db_path = str(getattr(graph, "db_path", ""))
        rows = graph._rows(  # noqa: SLF001 - absence-module precedent (absence_diagnosis)
            "MATCH (m:GraphMeta) RETURN m.counts_json AS cj, m.built_at AS built_at"
        )
        if not rows:
            return None
        row = rows[0]
        built_at = int(row.get("built_at") or 0)
        cached = _counts_cache.get(db_path)
        if cached is not None and cached[0] == built_at:
            return cached[1]
        cj = row.get("cj")
        if not isinstance(cj, str) or not cj.strip():
            return None
        parsed = json.loads(cj)
        if not isinstance(parsed, dict):
            return None
        _counts_cache[db_path] = (built_at, parsed)
        return parsed
    except Exception:  # noqa: BLE001 — fail-open, never raise
        log.debug("capability counts read failed", exc_info=True)
        return None


def clear_capability_cache() -> None:
    """Test hook: empty the per-process counts cache."""
    global _counts_cache
    _counts_cache = {}
