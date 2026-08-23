"""Tests for dynamic connect-time MCP instructions (capability-absent).

``_build_instructions`` appends one zero-edge-type sentence when the index has
zero-count edge types; otherwise the server instructions are byte-identical to
the static ``_INSTRUCTIONS`` constant. Banned vocabulary (operator remedies an
agent cannot act on): reindex / annotate / @Codebase.
"""

from __future__ import annotations

from java_codebase_rag.mcp.server import _INSTRUCTIONS, _build_instructions, create_mcp_server


class TestBuildInstructions:
    def test_none_returns_base_byte_identical(self) -> None:
        assert _build_instructions(None) == _INSTRUCTIONS

    def test_empty_list_returns_base_byte_identical(self) -> None:
        assert _build_instructions([]) == _INSTRUCTIONS

    def test_zero_types_appended_sentence(self) -> None:
        out = _build_instructions(["ASYNC_CALLS", "HTTP_CALLS"])
        assert out.startswith(_INSTRUCTIONS)
        assert "Zero-edge types in this index" in out
        assert "`ASYNC_CALLS`, `HTTP_CALLS`" in out  # sorted, backticked
        assert "don't query" in out

    def test_single_zero_type(self) -> None:
        out = _build_instructions(["ASYNC_CALLS"])
        assert "`ASYNC_CALLS`" in out

    def test_no_banned_vocabulary(self) -> None:
        out = _build_instructions(["ASYNC_CALLS", "HTTP_CALLS"])
        for banned in ("reindex", "annotat", "@Codebase"):
            assert banned not in out.lower()


class _StubInstructionsGraph:
    """Minimal graph for the server wiring path (Task-2 stub shape)."""

    db_path = "/tmp/stub_instructions_ladybug"

    def __init__(self, cj: str) -> None:
        self._cj = cj

    def _rows(self, query: str, params: dict | None = None) -> list[dict]:
        return [{"cj": self._cj, "built_at": 1}]


class TestCreateServerWiring:
    def test_instructions_reflect_zero_edge_types(self, monkeypatch) -> None:
        from java_codebase_rag.graph.ladybug_queries import LadybugGraph

        monkeypatch.setattr(LadybugGraph, "exists", classmethod(lambda cls: True))
        monkeypatch.setattr(
            LadybugGraph,
            "get",
            classmethod(lambda cls: _StubInstructionsGraph('{"calls": 5, "http_calls": 0}')),
        )
        mcp = create_mcp_server()
        assert "Zero-edge types in this index" in mcp.instructions
        assert "`HTTP_CALLS`" in mcp.instructions

    def test_instructions_base_when_graph_absent(self, monkeypatch) -> None:
        from java_codebase_rag.graph.ladybug_queries import LadybugGraph

        monkeypatch.setattr(LadybugGraph, "exists", classmethod(lambda cls: False))
        mcp = create_mcp_server()
        assert mcp.instructions == _INSTRUCTIONS
