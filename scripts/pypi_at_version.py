#!/usr/bin/env python3
"""Pre-upload idempotency check: is ``<name>`` already at ``<version>`` on PyPI?

The CI release workflow publishes under BOTH PyPI names (``jrag-cli`` then
``java-codebase-rag``); before each upload it runs this helper, and if the name
is already at the target version it SKIPS that upload. That makes a
partial-failure retry converge to "both names at X.Y.Z" instead of erroring on
PyPI's duplicate-rejection 400 — the sync invariant of the dual-name release.

Consumes the PyPI JSON API at ``https://pypi.org/pypi/<name>/json``. The CA
bundle is wired in internally: ``certifi`` when available (the macOS dev box's
default urllib chain fails with ``CERTIFICATE_VERIFY_FAILED``), otherwise the
system CA store (CI runners ship no ``certifi`` but a working system chain).
Callers never set ``SSL_CERT_FILE``, and the helper works in both environments.

Exit codes / output:
    0  stdout ``published``      — name exists AND <version> is already there
                                   (== ``info.version`` OR a key in ``releases``).
    1  stdout ``not-published``  — name exists but <version> is absent, or the
                                   project itself is absent (HTTP 404).
    1  stderr ``unknown: <why>``  — any network/SSL/JSON error. The workflow then
                                   proceeds to attempt the upload and lets PyPI's
                                   own duplicate-rejection (400) be the loud
                                   backstop.

No retry, no caching, no rate-limit handling — intentionally one-shot.

Usage:
    python scripts/pypi_at_version.py <project-name> <X.Y.Z>
"""
from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.request

try:
    # certifi is needed only where the system CA chain is broken (e.g. the macOS
    # dev box); CI runners (Ubuntu) have a working system CA store and the
    # workflow's bare Python env does not install certifi. Optional, not required.
    import certifi

    _CAFILE: str | None = certifi.where()
except ImportError:
    _CAFILE = None

_PYPI_JSON = "https://pypi.org/pypi/{name}/json"


def _fetch(name: str) -> dict | None:
    """Fetch and parse the PyPI JSON metadata for ``name``.

    Returns the parsed JSON dict on success. Returns ``None`` on HTTP 404 (the
    project name isn't registered on PyPI at all). Raises on any other error
    (non-404 HTTP, network/SSL, JSON decode) — the caller turns those into the
    ``unknown`` outcome so the workflow can fall through to a real upload.

    The CA bundle is supplied two ways, both internally so callers set nothing:
      - an ``ssl.create_default_context(cafile=...)`` passed to ``urlopen``
        (``cafile`` is ``certifi.where()`` when certifi is available, else
        ``None`` which loads the system root certs), and
      - ``SSL_CERT_FILE`` set in ``os.environ`` when certifi is available
        (belt-and-suspenders; skipped on CI where the system chain is fine).
    """
    if _CAFILE is not None:
        os.environ.setdefault("SSL_CERT_FILE", _CAFILE)
    ctx = ssl.create_default_context(cafile=_CAFILE)

    url = _PYPI_JSON.format(name=name)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, context=ctx) as resp:
            body = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return json.loads(body)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "unknown: usage: pypi_at_version.py <project-name> <X.Y.Z>",
            file=sys.stderr,
        )
        return 1
    name, version = argv[0], argv[1]

    try:
        data = _fetch(name)
    except Exception as e:  # network / SSL / JSON / non-404 HTTP — fall through.
        print(f"unknown: {type(e).__name__}: {e}", file=sys.stderr)
        return 1

    if data is None:
        print("not-published")
        return 1

    info_version = (data.get("info") or {}).get("version")
    releases = data.get("releases") or {}
    if version == info_version or version in releases:
        print("published")
        return 0

    print("not-published")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
