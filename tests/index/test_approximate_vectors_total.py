"""``_approximate_vectors_total`` counts indexed inputs only — JVM sources.

SQL/YAML are no longer indexed (see
docs/superpowers/specs/active/2026-09-01-drop-sql-yaml-indexing-design.md), so
the pre-walk total must not count Flyway migrations or application YAML even
when those files exist in the repo.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# The flow module imports cocoindex at module top; graph-only installs (Intel
# Mac CI) don't have it — skip collection there like the sibling vector tests.
pytest.importorskip("cocoindex")

from java_codebase_rag.index.java_index_flow_lancedb import (  # noqa: E402
    _approximate_vectors_total,
)


def test_counts_source_files_only(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    java = root / "src" / "main" / "java" / "com" / "x"
    java.mkdir(parents=True)
    (java / "A.java").write_text("package com.x;\n", encoding="utf-8")

    migration = root / "src" / "main" / "resources" / "db" / "migration"
    migration.mkdir(parents=True)
    (migration / "V1__init.sql").write_text(
        "CREATE TABLE users (id INT);\n", encoding="utf-8"
    )
    (root / "src" / "main" / "resources" / "application.yml").write_text(
        "spring:\n  application:\n    name: demo\n", encoding="utf-8"
    )

    # Only the .java file counts: SQL/YAML are unindexed by design.
    assert _approximate_vectors_total(root) == 1
