"""Tests for ``scripts/pypi_at_version.py`` — pre-upload idempotency check.

The release workflow publishes under both PyPI names (``jrag-cli`` then
``java-codebase-rag``); before each upload it runs this helper, and if the name
is already at the target version it SKIPS that upload. That makes a
partial-failure retry converge to "both names at X.Y.Z" instead of erroring on
PyPI's duplicate-rejection 400.

These tests pin the three exit-code outcomes:
  - 0 ``published``     — name exists AND version is ``info.version`` OR in ``releases``;
  - 1 ``not-published`` — name exists but version absent, OR project missing (404);
  - 1 ``unknown: ...``  — any network/SSL/JSON error (stderr).

``scripts/`` is NOT on the pytest pythonpath (``pytest.ini`` pins
``pythonpath = src tests``), so the module is loaded from its file path with
``importlib`` — mirroring how the script runs (a file in ``scripts/``) while
keeping the tests fast and network-free. ``_fetch`` is monkeypatched so no real
HTTP is issued.
"""
from __future__ import annotations

import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pypi_at_version.py"


@pytest.fixture
def pypi_mod():
    """Load ``scripts/pypi_at_version.py`` fresh from its file path.

    Uses ``importlib`` (not ``import pypi_at_version``) because ``scripts/`` is
    absent from ``pytest.ini``'s ``pythonpath``. Re-executed per test so a stale
    monkeypatch on ``_fetch`` can never leak across tests.
    """
    spec = importlib.util.spec_from_file_location("pypi_at_version", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_published_when_latest_matches(pypi_mod, monkeypatch, capsys) -> None:
    """``info.version`` equals the target → 0, stdout ``published``."""
    monkeypatch.setattr(
        pypi_mod,
        "_fetch",
        lambda name: {"info": {"version": "0.12.0"}, "releases": {}},
    )
    rc = pypi_mod.main(["x", "0.12.0"])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out.strip() == "published"
    assert err == ""


def test_published_when_in_releases_not_latest(pypi_mod, monkeypatch, capsys) -> None:
    """Target is an older published version (a key in ``releases``) → 0.

    The current ``info.version`` (0.13.0) is higher than the target (0.12.0),
    but 0.12.0 was published and still lists in ``releases`` — that counts as
    already-published for idempotency.
    """
    monkeypatch.setattr(
        pypi_mod,
        "_fetch",
        lambda name: {"info": {"version": "0.13.0"}, "releases": {"0.12.0": [{"filename": "x-0.12.0.tar.gz"}]}},
    )
    rc = pypi_mod.main(["x", "0.12.0"])
    assert rc == 0
    out, err = capsys.readouterr()
    assert out.strip() == "published"


def test_not_published_when_absent(pypi_mod, monkeypatch, capsys) -> None:
    """Project exists but the target version is neither latest nor in releases → 1."""
    monkeypatch.setattr(
        pypi_mod,
        "_fetch",
        lambda name: {"info": {"version": "0.13.0"}, "releases": {"0.13.0": [{"filename": "x-0.13.0.tar.gz"}]}},
    )
    rc = pypi_mod.main(["x", "0.12.0"])
    assert rc == 1
    out, err = capsys.readouterr()
    assert out.strip() == "not-published"


def test_not_published_when_project_missing(pypi_mod, monkeypatch, capsys) -> None:
    """``_fetch`` returns ``None`` (HTTP 404, name not registered) → 1 ``not-published``."""
    monkeypatch.setattr(pypi_mod, "_fetch", lambda name: None)
    rc = pypi_mod.main(["x", "0.12.0"])
    assert rc == 1
    out, err = capsys.readouterr()
    assert out.strip() == "not-published"


def test_unknown_on_network_error(pypi_mod, monkeypatch, capsys) -> None:
    """``_fetch`` raises ``urllib.error.URLError`` → 1, stderr contains ``unknown``.

    A network/SSL failure must NOT crash the script — it returns ``unknown`` so
    the workflow proceeds to attempt the upload and lets PyPI's own
    duplicate-rejection (400) be the loud backstop.
    """
    def _boom(_name):
        raise urllib.error.URLError("tls handshake failed")

    monkeypatch.setattr(pypi_mod, "_fetch", _boom)
    rc = pypi_mod.main(["x", "0.12.0"])
    assert rc == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "unknown" in err


def test_unknown_on_bad_json(pypi_mod, monkeypatch, capsys) -> None:
    """``_fetch`` raises ``json.JSONDecodeError`` → 1, stderr contains ``unknown``."""
    def _bad_json(_name):
        raise json.JSONDecodeError("Expecting value", "<html>500</html>", 0)

    monkeypatch.setattr(pypi_mod, "_fetch", _bad_json)
    rc = pypi_mod.main(["x", "0.12.0"])
    assert rc == 1
    out, err = capsys.readouterr()
    assert out == ""
    assert "unknown" in err
