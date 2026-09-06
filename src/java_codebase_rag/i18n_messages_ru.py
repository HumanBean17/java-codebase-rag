"""Russian runtime catalog (MSG_/ERR_/LBL_/HINT_ keys).

Values mirror :mod:`i18n_messages_en`; plural keys carry the three Russian
forms (``one``/``few``/``many``). Style: formal lowercase «вы», imperative
next-actions, «ёлочки» quotes, Arabic numerals. Command names, flag names,
and setting values stay literal English (see the plan's glossary).
"""
from __future__ import annotations

from typing import Any

MESSAGES: dict[str, Any] = {
    # Bootstrap keys (removed in the operator-CLI task once real keys land).
    "MSG_TEST_GREETING": "индекс готов",
    "MSG_TEST_PLURAL": {
        "one": "{n} совпадение",
        "few": "{n} совпадения",
        "many": "{n} совпадений",
    },
    "LBL_TEST_PREFIX": "Вердикт: ",
    # Unified dispatcher help section header.
    "MSG_UNIFIED_OPERATOR_HEADER": (
        "Команды оператора (индексация и обслуживание; подробности — "
        "`jrag <command> --help`):\n"
    ),
}
