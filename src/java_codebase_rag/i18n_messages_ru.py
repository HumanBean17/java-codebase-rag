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
    # Absence verdict labels + render prefixes (jrag_render).
    "LBL_ABSENCE_NOT_IN_PROJECT": "нет в проекте",
    "LBL_ABSENCE_EXTERNAL_DEPENDENCY": "внешняя зависимость",
    "LBL_ABSENCE_REFINE_QUERY": "уточните запрос",
    "LBL_ABSENCE_CORRECT_EMPTY": "корректный пустой результат",
    "LBL_VERDICT_PREFIX": "Вердикт: ",
    "LBL_NEXT_PREFIX": "далее: ",
    "LBL_WARNING_PREFIX": "предупреждение: ",
    "LBL_ERROR_PREFIX": "ошибка: ",
    "LBL_ERROR_WORD": "ошибка",
    "LBL_NOT_FOUND_PREFIX": "не найдено: ",
    "LBL_NOT_FOUND_WORD": "не найдено",
    # Truncation notices.
    "MSG_TRUNCATED_OFFSET": "обрезано: результатов больше — используйте --offset {offset}",
    "MSG_TRUNCATED_NARROW": "обрезано: результатов больше — уточните запрос",
    # Did-you-mean (not_found + closest_symbols).
    "MSG_DID_YOU_MEAN_ONE": "Возможно, вы имели в виду: {sym}?",
    "MSG_DID_YOU_MEAN_TWO": "Возможно, вы имели в виду: {a} или {b}?",
    "MSG_DID_YOU_MEAN_MANY": "Возможно, вы имели в виду: {list}?",
    "LBL_OR": " или {last}",
    # Zero-result lines (listing + traversal).
    "MSG_ZERO_LISTING": "{noun}: 0",
    "MSG_EXTERNAL_ENTRYPOINT": "внешняя точка входа — вызывающих в репозитории нет",
    # Row labels.
    "LBL_NO_IDENTIFIER": "(без имени)",
    "LBL_MISSING": "(отсутствует)",
    "LBL_UNRESOLVED": "(не разрешён)",
    "LBL_ROOT_PREFIX": "корень: ",
    # Grouped-traversal headers.
    "LBL_INBOUND": "входящие:",
    "LBL_OUTBOUND": "исходящие:",
    "LBL_SUPERTYPES": "↑ супертипы:",
    "LBL_SUBTYPES": "↓ подтипы:",
    "LBL_STAGE_SEED": "этап 0 (источник):",
    "LBL_STAGE_ROLES": "этап {n} ({roles}):",
    "LBL_STAGE": "этап {n}:",
    # Ambiguous renderer.
    "MSG_AMBIGUOUS_HEADER": {
        "one": "{n} неоднозначное совпадение для '{noun}'",
        "few": "{n} неоднозначных совпадения для '{noun}'",
        "many": "{n} неоднозначных совпадений для '{noun}'",
    },
    "MSG_AMBIGUOUS_HEADER_NO_NOUN": {
        "one": "{n} неоднозначное совпадение",
        "few": "{n} неоднозначных совпадения",
        "many": "{n} неоднозначных совпадений",
    },
    "MSG_NARROW": "Уточните через --kind --java-kind --role --fqn-contains:",
    # Result-kind nouns.
    "LBL_NOUN_MATCHES": "совпадения",
    "LBL_NOUN_CALLERS": "вызывающие стороны",
    "LBL_NOUN_CALLEES": "вызываемые стороны",
    "LBL_NOUN_IMPLEMENTATIONS": "реализации",
    "LBL_NOUN_SUBCLASSES": "подклассы",
    "LBL_NOUN_OVERRIDES": "переопределения",
    "LBL_NOUN_OVERRIDDEN_BY": "переопределяемые",
    "LBL_NOUN_DEPENDENTS": "зависимые",
    "LBL_NOUN_IMPACT": "затронутые",
    "LBL_NOUN_DECOMPOSE": "этапы",
    "LBL_NOUN_DEPENDENCIES": "зависимости",
    "LBL_NOUN_CONNECTION": "связи",
    "LBL_NOUN_HIERARCHY": "иерархия",
    "LBL_NOUN_ROUTE": "маршруты",
    "LBL_NOUN_CLIENT": "клиенты",
    "LBL_NOUN_PRODUCER": "продюсеры",
    "LBL_NOUN_TOPIC": "топики",
    "LBL_NOUN_SYMBOL": "символы",
    "LBL_NOUN_IMPORT": "импорты",
    "LBL_NOUN_MICROSERVICES": "микросервисы",
    "LBL_NOUN_MAP": "карта",
    "LBL_NOUN_CONVENTIONS": "соглашения",
    "LBL_NOUN_OVERVIEW": "обзор",
}
