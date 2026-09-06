"""Russian argparse-help catalog (HELP_* keys).

Mirrors :mod:`i18n_messages_help_en`; argparse boilerplate headings
(``usage:``/``options:``) stay English by design (spec out-of-scope).
"""
from __future__ import annotations

from typing import Any

MESSAGES: dict[str, Any] = {
    "HELP_FLAG_LANG": (
        "Язык интерфейса: вывод, справка, ошибки (по умолчанию en; также "
        "JAVA_CODEBASE_RAG_LANGUAGE или language: в YAML)."
    ),
}
