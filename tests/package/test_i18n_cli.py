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
