"""Unit tests for the ``java_codebase_rag.i18n`` key-catalog runtime.

Covers: locale state (default en), ``tr``/``ntr`` lookup + formatting, the
CLDR Russian plural rule (one/few/many), argv lang scanning/stripping, the
CLI override stash, help-time locale precedence, catalog parity and shape,
and a static guard that every literal ``tr("...")``/``ntr("...")`` call site
uses a key that exists in the EN catalogs.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from java_codebase_rag import i18n
from java_codebase_rag import i18n_messages_en
from java_codebase_rag import i18n_messages_help_en
from java_codebase_rag import i18n_messages_help_ru
from java_codebase_rag import i18n_messages_ru

_SRC_ROOT = Path(__file__).resolve().parent.parent.parent / "src" / "java_codebase_rag"

_TR_CALL_RE = re.compile(r"\b[n]?tr\(\s*\"([A-Z0-9_]+)\"")


@pytest.fixture(autouse=True)
def _clean_locale_state():
    """Every test starts and ends in the default state: en, no override."""
    i18n.reset_locale()
    i18n.set_cli_lang_override(None)
    yield
    i18n.reset_locale()
    i18n.set_cli_lang_override(None)


def test_default_locale_is_english():
    assert i18n.get_locale() == "en"


def test_set_locale_valid_and_invalid():
    i18n.set_locale("ru")
    assert i18n.get_locale() == "ru"
    with pytest.raises(ValueError):
        i18n.set_locale("fr")
    i18n.reset_locale()
    assert i18n.get_locale() == "en"


def test_tr_english_and_russian():
    assert i18n.tr("MSG_TEST_GREETING") == "index ready"
    i18n.set_locale("ru")
    assert i18n.tr("MSG_TEST_GREETING") == "индекс готов"


def test_tr_placeholder_formatting(monkeypatch):
    monkeypatch.setitem(i18n_messages_en.MESSAGES, "MSG_TEST_SCRATCH", "{n} files")
    monkeypatch.setitem(i18n_messages_ru.MESSAGES, "MSG_TEST_SCRATCH", "файлов: {n}")
    assert i18n.tr("MSG_TEST_SCRATCH", n=3) == "3 files"
    i18n.set_locale("ru")
    assert i18n.tr("MSG_TEST_SCRATCH", n=3) == "файлов: 3"


def test_tr_missing_key_raises():
    with pytest.raises(KeyError):
        i18n.tr("MSG_NOPE")


def test_tr_missing_placeholder_propagates(monkeypatch):
    """A template placeholder the caller did not supply is a programming error."""
    monkeypatch.setitem(i18n_messages_en.MESSAGES, "MSG_TEST_SCRATCH", "{n} files")
    with pytest.raises(KeyError):
        i18n.tr("MSG_TEST_SCRATCH")


def test_ntr_english_plurals():
    assert i18n.ntr("MSG_TEST_PLURAL", 1) == "1 match"
    assert i18n.ntr("MSG_TEST_PLURAL", 0) == "0 matches"
    assert i18n.ntr("MSG_TEST_PLURAL", 5) == "5 matches"


def test_ntr_russian_plurals():
    i18n.set_locale("ru")
    assert i18n.ntr("MSG_TEST_PLURAL", 1) == "1 совпадение"
    assert i18n.ntr("MSG_TEST_PLURAL", 2) == "2 совпадения"
    assert i18n.ntr("MSG_TEST_PLURAL", 5) == "5 совпадений"
    assert i18n.ntr("MSG_TEST_PLURAL", 11) == "11 совпадений"
    assert i18n.ntr("MSG_TEST_PLURAL", 21) == "21 совпадение"
    assert i18n.ntr("MSG_TEST_PLURAL", 22) == "22 совпадения"
    assert i18n.ntr("MSG_TEST_PLURAL", 101) == "101 совпадение"
    assert i18n.ntr("MSG_TEST_PLURAL", 111) == "111 совпадений"
    assert i18n.ntr("MSG_TEST_PLURAL", 0) == "0 совпадений"


def test_plural_form_table():
    ru_expect = {
        1: "one", 2: "few", 5: "many", 11: "many", 12: "many", 14: "many",
        21: "one", 22: "few", 25: "many", 100: "many", 101: "one", 111: "many",
    }
    for n, form in ru_expect.items():
        assert i18n.plural_form("ru", n) == form, f"plural_form('ru', {n})"
    assert i18n.plural_form("en", 1) == "one"
    assert i18n.plural_form("en", 2) == "other"


def test_scan_lang_forms():
    assert i18n.scan_lang(["--lang", "ru"]) == "ru"
    assert i18n.scan_lang(["--lang=ru"]) == "ru"
    assert i18n.scan_lang(["-L", "ru"]) == "ru"
    assert i18n.scan_lang(["find", "x"]) is None
    assert i18n.scan_lang(["--lang"]) is None  # missing value
    assert i18n.scan_lang(["--lang", "fr"]) is None  # invalid value


def test_strip_lang_before_verb():
    verbs = frozenset({"find"})
    value, stripped = i18n.strip_lang_before_verb(["--lang", "ru", "find", "x"], verbs)
    assert value == "ru"
    assert stripped == ["find", "x"]

    value, stripped = i18n.strip_lang_before_verb(["find", "--lang", "ru", "x"], verbs)
    assert value is None
    assert stripped == ["find", "--lang", "ru", "x"]

    value, stripped = i18n.strip_lang_before_verb(["--lang=ru", "status"], verbs)
    assert value == "ru"
    assert stripped == ["status"]


def test_override_stash():
    assert i18n.cli_lang_override() is None
    i18n.set_cli_lang_override("ru")
    assert i18n.cli_lang_override() == "ru"
    i18n.set_cli_lang_override(None)
    assert i18n.cli_lang_override() is None


def test_init_help_locale_precedence(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # no project YAML above a bare tmp dir
    monkeypatch.delenv("JAVA_CODEBASE_RAG_LANGUAGE", raising=False)
    assert i18n.init_help_locale(None) == "en"

    monkeypatch.setenv("JAVA_CODEBASE_RAG_LANGUAGE", "ru")
    assert i18n.init_help_locale(None) == "ru"
    assert i18n.init_help_locale("en") == "en"  # scan beats env
    monkeypatch.delenv("JAVA_CODEBASE_RAG_LANGUAGE")

    assert i18n.init_help_locale("fr") == "en"  # invalid scan ignored
    monkeypatch.setenv("JAVA_CODEBASE_RAG_LANGUAGE", "fr")
    assert i18n.init_help_locale(None) == "en"  # invalid env ignored
    i18n.reset_locale()


def test_catalog_parity():
    for en, ru, label in (
        (i18n_messages_en.MESSAGES, i18n_messages_ru.MESSAGES, "runtime"),
        (i18n_messages_help_en.MESSAGES, i18n_messages_help_ru.MESSAGES, "help"),
    ):
        missing_in_ru = sorted(set(en) - set(ru))
        missing_in_en = sorted(set(ru) - set(en))
        assert not missing_in_ru, f"{label}: keys missing in RU catalog: {missing_in_ru}"
        assert not missing_in_en, f"{label}: keys missing in EN catalog: {missing_in_en}"


def test_catalog_no_key_in_both_runtime_and_help():
    for en, ru, label in (
        (i18n_messages_en.MESSAGES, i18n_messages_help_en.MESSAGES, "en"),
        (i18n_messages_ru.MESSAGES, i18n_messages_help_ru.MESSAGES, "ru"),
    ):
        overlap = sorted(set(en) & set(ru))
        assert not overlap, f"{label}: keys in both runtime and help catalogs: {overlap}"


def test_catalog_plural_shape():
    for catalog, locale, expected_forms, label in (
        (i18n_messages_en.MESSAGES, "en", {"one", "other"}, "en runtime"),
        (i18n_messages_help_en.MESSAGES, "en", {"one", "other"}, "en help"),
        (i18n_messages_ru.MESSAGES, "ru", {"one", "few", "many"}, "ru runtime"),
        (i18n_messages_help_ru.MESSAGES, "ru", {"one", "few", "many"}, "ru help"),
    ):
        for key, value in catalog.items():
            if not isinstance(value, dict):
                continue
            assert set(value) == expected_forms, (
                f"{label}/{key}: forms {sorted(value)} != {sorted(expected_forms)}"
            )
            for form, template in value.items():
                assert "{n}" in template, f"{label}/{key}/{form}: missing {{n}}"


def test_tr_call_sites_use_known_keys():
    known = set(i18n_messages_en.MESSAGES) | set(i18n_messages_help_en.MESSAGES)
    offenders: list[str] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        for match in _TR_CALL_RE.finditer(path.read_text(encoding="utf-8")):
            key = match.group(1)
            if key not in known:
                offenders.append(f"{path.name}: {key}")
    assert not offenders, f"tr/ntr call sites with unknown keys: {offenders}"
