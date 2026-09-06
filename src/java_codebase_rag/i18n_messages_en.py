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
}
