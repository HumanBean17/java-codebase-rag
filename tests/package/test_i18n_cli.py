"""CLI-level i18n tests: ``--lang`` flag wiring, help localization, locale
lifecycle in the two ``main()`` entrypoints.

In-process ``main()`` calls with ``capsys`` (the ``test_version_flag.py``
style) — no index needed, since ``--help`` and usage-error paths exercise
the parser surface only. Subprocess-level dispatch tests (before-verb
``--lang`` through the real binary) live in Task 10's additions.
"""
from __future__ import annotations

import pytest

from java_codebase_rag import cli, i18n, jrag


@pytest.fixture(autouse=True)
def _clean_locale_state():
    """Every test starts and ends in the default state: en, no override."""
    i18n.reset_locale()
    i18n.set_cli_lang_override(None)
    yield
    i18n.reset_locale()
    i18n.set_cli_lang_override(None)


@pytest.fixture(autouse=True)
def _clean_language_env(monkeypatch):
    monkeypatch.delenv("JAVA_CODEBASE_RAG_LANGUAGE", raising=False)


def test_jrag_help_russian_after_verb_flag(capsys):
    rc = jrag.main(["find", "--lang", "ru", "--help"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Язык интерфейса" in out


def test_jrag_help_english_by_default(capsys):
    rc = jrag.main(["find", "--help"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Interface language" in out
    assert not any("Ѐ" <= ch <= "ӿ" for ch in out)


def test_cli_help_english_by_default(capsys):
    rc = cli.main(["init", "--help"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Interface language" in out
    assert not any("Ѐ" <= ch <= "ӿ" for ch in out)


def test_cli_help_russian(capsys):
    rc = cli.main(["init", "--lang", "ru", "--help"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Язык интерфейса" in out


def test_jrag_invalid_lang_rejected(capsys):
    """argparse ``choices`` rejects ``fr``; the ArgumentError envelope path
    returns 2 (the house contract for usage errors reaching the envelope)."""
    rc = jrag.main(["find", "--lang", "fr", "--help"])

    assert rc == 2
    err = capsys.readouterr().err
    assert err.strip() != ""


def test_env_drives_help_locale(capsys, monkeypatch):
    monkeypatch.setenv("JAVA_CODEBASE_RAG_LANGUAGE", "ru")

    rc = jrag.main(["find", "--help"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Язык интерфейса" in out


def test_dispatch_stash_feeds_help_locale(capsys):
    """The stash set by the dispatch pre-scan seeds help rendering when the
    sub-main runs with the flag already stripped (the console path)."""
    i18n.set_cli_lang_override("ru")

    rc = jrag.main(["find", "--help"])

    assert rc == 0
    out = capsys.readouterr().out
    assert "Язык интерфейса" in out


# ----- Task 5: agent-verb runtime strings and error paths --------------------


def test_error_envelope_russian_usage_error(capsys, tmp_path, monkeypatch):
    """Usage-error stderr prefix localizes; the envelope keeps the stdlib's
    English message text (documented out-of-scope: argparse fragments)."""
    monkeypatch.chdir(tmp_path)
    i18n.set_cli_lang_override("ru")

    rc = jrag.main(["callers"])

    assert rc == 2
    res = capsys.readouterr()
    assert res.err.startswith("jrag: ошибка:")
    assert "callers" in res.out  # cmd prefix on the envelope message stays literal


def test_error_envelope_russian_internal_error(capsys, tmp_path, monkeypatch):
    def _boom(args):
        raise RuntimeError("boom")

    monkeypatch.setattr(jrag, "_cmd_status", _boom)

    rc = jrag.main(["status", "--lang", "ru", "--index-dir", str(tmp_path)])

    assert rc == 2
    out = capsys.readouterr().out
    assert "внутренняя ошибка: boom" in out
    assert "internal error" not in out


def test_missing_index_russian_message(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    empty = tmp_path / "no-index"
    empty.mkdir()

    rc = jrag.main(["status", "--lang", "ru", "--index-dir", str(empty)])

    assert rc == 2
    out = capsys.readouterr().out
    assert "Нет индекса" in out
    assert "jrag init --source-root" in out  # remediation keeps its literal command


def test_ambiguous_plural_russian():
    from java_codebase_rag.i18n import ntr

    i18n.set_locale("ru")
    try:
        assert ntr("MSG_AMBIGUOUS_CANDIDATES", 3) == "3 кандидата"
        assert ntr("MSG_AMBIGUOUS_CANDIDATES", 5) == "5 кандидатов"
        assert ntr("MSG_AMBIGUOUS_CANDIDATES", 1) == "1 кандидат"
    finally:
        i18n.reset_locale()
    assert ntr("MSG_AMBIGUOUS_CANDIDATES", 1) == "1 candidate"
    assert ntr("MSG_AMBIGUOUS_CANDIDATES", 5) == "5 candidates"


def test_auto_scope_warning_russian(capsys):
    """The envelope warning value localizes (stderr line + warnings[] value)."""
    from java_codebase_rag.jrag import _auto_scope_notice
    import argparse as _ap

    args = _ap.Namespace(_service_auto="chat-core")
    i18n.set_locale("ru")
    try:
        notices = _auto_scope_notice(args)
    finally:
        i18n.reset_locale()
    assert notices == [
        "auto-scope: --service chat-core (определён по cwd; "
        "передайте --no-auto-scope, чтобы отключить)"
    ]


# ----- Task 6: operator CLI strings ------------------------------------------


def test_cli_arg_error_stdlib_fragment_stays_english(capsys, tmp_path, monkeypatch):
    """Operator usage errors route through stock argparse ``error()`` (usage
    dump + ``<prog>: error:``), a stdlib fragment that stays English by spec.
    The jrag-authored ``LBL_JRAG_ERROR_STDERR`` wrapper localizes the paths
    that reach it; this pins the boundary."""
    monkeypatch.chdir(tmp_path)
    rc = cli.main(["erase", "--lang", "ru", "--bogus"])

    assert rc == 2
    err = capsys.readouterr().err
    assert "error: unrecognized arguments: --bogus" in err


def test_cli_internal_error_russian(capsys, tmp_path, monkeypatch):
    import json as _json

    def _boom(ns):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "_cmd_tables", _boom)
    monkeypatch.chdir(tmp_path)

    rc = cli.main(["tables", "--lang", "ru", "--index-dir", str(tmp_path)])

    assert rc == 2
    out = capsys.readouterr().out
    payload = _json.loads(out)
    assert set(payload) == {"success", "exit_code", "message"}  # keys stay English
    assert "внутренняя ошибка: boom" in payload["message"]


def test_refresh_deprecation_russian(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def _stub_reprocess(ns):
        return 0

    monkeypatch.setattr(cli, "_cmd_reprocess", _stub_reprocess)
    rc = cli.main(["refresh", "--lang", "ru"])

    assert rc == 0
    err = capsys.readouterr().err
    assert "устарела" in err
    assert "reprocess" in err


def test_erase_prompt_russian(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    monkeypatch.chdir(tmp_path)
    empty_idx = tmp_path / ".java-codebase-rag"
    empty_idx.mkdir()

    rc = cli.main(["erase", "--lang", "ru", "--index-dir", str(tmp_path)])

    assert rc == 2
    err = capsys.readouterr().err
    assert "Будет удалено" in err
    assert "Отменено" in err


def test_increment_warning_lazy_russian():
    from java_codebase_rag.cli import _INCREMENT_WARNING_LINES

    i18n.set_locale("ru")
    try:
        ru = cli._increment_warning_lines()
        assert any("ВНИМАНИЕ" in line for line in ru)
        assert any("jrag reprocess" in line for line in ru)  # literal command survives
    finally:
        i18n.reset_locale()
    # EN parity: the lazy function reproduces the frozen constant exactly.
    assert cli._increment_warning_lines() == list(_INCREMENT_WARNING_LINES)


def test_advisory_functions_english_parity():
    """EN output of the localized advisory functions equals the frozen module
    constants (drift guard); MCP paths keep consuming the constants directly."""
    from java_codebase_rag import pipeline
    from java_codebase_rag.cli import (
        _REFRESH_DEPRECATION,
        _REPROCESS_DRIFT_VECTORS_ONLY,
    )

    assert pipeline.vectors_skipped_graph_only() == pipeline.VECTORS_SKIPPED_GRAPH_ONLY
    assert pipeline.vectors_skipped_bm25() == pipeline.VECTORS_SKIPPED_BM25
    assert pipeline.retrieval_bm25_hint() == pipeline.RETRIEVAL_BM25_HINT
    assert cli._refresh_deprecation() == _REFRESH_DEPRECATION
    assert cli._reprocess_drift_vectors_only() == _REPROCESS_DRIFT_VECTORS_ONLY


def test_advisory_functions_russian():
    from java_codebase_rag import pipeline

    i18n.set_locale("ru")
    try:
        assert "векторы пропущены" in pipeline.vectors_skipped_bm25()
        assert "bm25" in pipeline.retrieval_bm25_hint()
    finally:
        i18n.reset_locale()
