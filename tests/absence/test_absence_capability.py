"""Tests for absence_capability.py — pure predicates over build-time counts.

The counts dict mirrors GraphMeta ``counts_json`` (build_ast_graph.py:3940):
lowercase keys, one per stored edge label plus node-kind totals. Fail-open is
the core contract: a missing key is UNKNOWN, never zero.
"""

from __future__ import annotations

from java_codebase_rag.absence.absence_capability import (
    EDGE_COUNT_KEYS,
    KIND_COUNT_KEYS,
    clear_capability_cache,
    decompose_edge_types,
    get_capability_counts,
    kind_node_count,
    requested_types_absent,
    zero_edge_types,
)
from java_codebase_rag.absence.absence_types import AbsenceCause


class _StubGraph:
    """Minimal graph stand-in: db_path + canned _rows results for meta reads."""

    def __init__(self, rows: list[dict] | None = None, *, raises: bool = False) -> None:
        self.db_path = "/tmp/stub_ladybug"
        self._canned_rows = rows
        self._raises = raises
        self.rows_calls = 0

    def _rows(self, query: str, params: dict | None = None) -> list[dict]:
        self.rows_calls += 1
        if self._raises:
            raise RuntimeError("graph unavailable")
        return self._canned_rows

_STORED_EDGE_LABELS = {
    "EXTENDS", "IMPLEMENTS", "INJECTS", "DECLARES", "OVERRIDES", "CALLS",
    "EXPOSES", "DECLARES_CLIENT", "DECLARES_PRODUCER", "HTTP_CALLS",
    "ASYNC_CALLS",
}


class TestCountKeyMaps:
    def test_edge_count_keys_cover_all_stored_labels(self) -> None:
        assert set(EDGE_COUNT_KEYS) == _STORED_EDGE_LABELS

    def test_edge_count_keys_values_are_lowercase_counts_keys(self) -> None:
        for label, key in EDGE_COUNT_KEYS.items():
            assert key == key.lower(), (label, key)

    def test_kind_count_keys(self) -> None:
        assert KIND_COUNT_KEYS == {
            "client": "clients", "producer": "producers", "route": "routes",
        }


class TestDecomposeEdgeTypes:
    def test_stored_label_passes_through(self) -> None:
        assert decompose_edge_types(["HTTP_CALLS"]) == ["HTTP_CALLS"]

    def test_declares_dot_key_decomposes_to_terminal(self) -> None:
        assert decompose_edge_types(
            ["DECLARES.DECLARES_CLIENT", "ASYNC_CALLS"]
        ) == ["DECLARES_CLIENT", "ASYNC_CALLS"]

    def test_overridden_by_dot_key_decomposes_to_terminal(self) -> None:
        assert decompose_edge_types(["OVERRIDDEN_BY.EXPOSES"]) == ["EXPOSES"]

    def test_mixed_stored_list(self) -> None:
        assert decompose_edge_types(["HTTP_CALLS", "CALLS"]) == [
            "HTTP_CALLS", "CALLS",
        ]

    def test_unknown_labels_dropped(self) -> None:
        assert decompose_edge_types(["NOT_AN_EDGE", "DECLARES.BOGUS"]) == []

    def test_composed_key_emits_no_dispatch_hop(self) -> None:
        out = decompose_edge_types(["DECLARES.DECLARES_CLIENT", "OVERRIDDEN_BY.EXPOSES"])
        assert out == ["DECLARES_CLIENT", "EXPOSES"]
        assert "DECLARES" not in out and "OVERRIDES" not in out

    def test_bare_dispatch_labels_are_stored_labels(self) -> None:
        # DECLARES/OVERRIDES are only dispatch hops as dot-key prefixes; as
        # bare requests they are plain stored labels and pass through.
        assert decompose_edge_types(["DECLARES", "OVERRIDES"]) == ["DECLARES", "OVERRIDES"]


class TestRequestedTypesAbsent:
    COUNTS = {"http_calls": 0, "async_calls": 0, "calls": 812}

    def test_single_zero_label_absent(self) -> None:
        assert requested_types_absent(["HTTP_CALLS"], self.COUNTS) is True

    def test_all_zero_list_absent(self) -> None:
        assert requested_types_absent(
            ["HTTP_CALLS", "ASYNC_CALLS"], self.COUNTS
        ) is True

    def test_mixed_with_nonzero_not_absent(self) -> None:
        assert requested_types_absent(
            ["HTTP_CALLS", "CALLS"], self.COUNTS
        ) is False

    def test_composed_key_ignores_dispatch_hop(self) -> None:
        counts = {"declares_client": 0, "declares": 9}
        assert requested_types_absent(["DECLARES.DECLARES_CLIENT"], counts) is True

    def test_mixed_composed_and_stored(self) -> None:
        counts = {"exposes": 5, "async_calls": 0}
        assert requested_types_absent(
            ["DECLARES.EXPOSES", "ASYNC_CALLS"], counts
        ) is False

    def test_missing_key_fails_open(self) -> None:
        assert requested_types_absent(["HTTP_CALLS"], {"calls": 5}) is False

    def test_unknown_label_not_absent(self) -> None:
        assert requested_types_absent(["NOT_AN_EDGE"], self.COUNTS) is False


class TestZeroEdgeTypes:
    def test_returns_zero_labels_only(self) -> None:
        assert zero_edge_types({"calls": 5, "http_calls": 0}) == {"HTTP_CALLS"}

    def test_missing_key_is_not_zero(self) -> None:
        assert zero_edge_types({"calls": 5}) == set()

    def test_all_nonzero_is_empty_set(self) -> None:
        assert zero_edge_types({"calls": 5, "exposes": 2}) == set()


class TestKindNodeCount:
    def test_zero_count(self) -> None:
        assert kind_node_count("client", {"clients": 0}) == 0

    def test_nonzero_count(self) -> None:
        assert kind_node_count("route", {"routes": 4}) == 4

    def test_missing_key_is_none(self) -> None:
        assert kind_node_count("producer", {"routes": 4}) is None

    def test_symbol_kind_is_none(self) -> None:
        assert kind_node_count("symbol", {"clients": 0}) is None

    def test_none_kind_is_none(self) -> None:
        assert kind_node_count(None, {"clients": 0}) is None


class TestCauseLiteral:
    def test_capability_absent_in_cause_literal(self) -> None:
        assert "capability_absent" in AbsenceCause.__args__


class TestGetCapabilityCounts:
    """Accessor: light GraphMeta row read, built_at-keyed cache, fail-open."""

    def setup_method(self) -> None:
        clear_capability_cache()

    def _row(self, cj: str | None, built_at: int) -> list[dict]:
        row: dict = {"built_at": built_at}
        if cj is not None:
            row["cj"] = cj
        return [row]

    def test_parses_counts_json(self) -> None:
        g = _StubGraph(self._row('{"calls": 3, "http_calls": 0}', 7))
        assert get_capability_counts(g) == {"calls": 3, "http_calls": 0}

    def test_cache_hit_same_built_at_returns_same_object(self) -> None:
        g = _StubGraph(self._row('{"calls": 3, "http_calls": 0}', 7))
        first = get_capability_counts(g)
        second = get_capability_counts(g)
        assert first is second
        assert g.rows_calls == 2  # the row read always happens; parse is cached

    def test_built_at_change_reparses(self) -> None:
        rows = self._row('{"calls": 3, "http_calls": 0}', 7)
        g = _StubGraph(rows)
        first = get_capability_counts(g)
        rows[0]["built_at"] = 8
        rows[0]["cj"] = '{"calls": 4, "http_calls": 1}'
        second = get_capability_counts(g)
        assert second == {"calls": 4, "http_calls": 1}
        assert second is not first

    def test_empty_rows_fails_open(self) -> None:
        assert get_capability_counts(_StubGraph([])) is None

    def test_missing_counts_json_fails_open(self) -> None:
        assert get_capability_counts(_StubGraph(self._row(None, 7))) is None

    def test_invalid_json_fails_open(self) -> None:
        assert get_capability_counts(_StubGraph(self._row("not json{", 7))) is None

    def test_rows_raising_fails_open(self) -> None:
        assert get_capability_counts(_StubGraph(raises=True)) is None

    def test_clear_cache_forces_reparse(self) -> None:
        g = _StubGraph(self._row('{"calls": 3, "http_calls": 0}', 7))
        first = get_capability_counts(g)
        clear_capability_cache()
        second = get_capability_counts(g)
        assert second == first
        assert second is not first
