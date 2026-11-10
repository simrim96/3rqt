"""Mini-valutazione fissa (30-50 item) con golden answer verificabili.

Regola di progettazione (criterio di uscita Fase 1): le risposte gold NON sono
digitate a mano ma calcolate in Python nel punto di definizione dell'item, e'
il test di suite che verifica la coerenza golden<->grader (e che i distrattori
vengono bocciati). Ogni item ha risposta estrabile in modo deterministico:
l'istruzione impone "ONLY the answer".

Versione suite: `SUITE_VERSION`. Cambiare gli item => bump della versione, il
report di calibrazione la registra.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

SUITE_VERSION = "mini-1"

_INSTR = "Answer with ONLY the result on a single line, no explanations."


def _item(
    item_id: str, category: str, question: str, golden: object, kind: str = "text"
) -> MiniItem:
    return MiniItem(
        id=item_id,
        category=category,
        prompt=f"{_INSTR}\n\n{question}",
        golden=json.dumps(golden, ensure_ascii=False) if kind == "json" else str(golden),
        kind=kind,
    )


@dataclass(frozen=True)
class MiniItem:
    id: str
    category: str
    prompt: str
    golden: str
    kind: str = "text"  # "text" | "json"


def _json_item(item_id: str, question: str, payload: object, answer: object) -> MiniItem:
    return _item(
        item_id,
        "json",
        f"Input:\n{json.dumps(payload, ensure_ascii=False)}\n\n{question}",
        answer,
        kind="json",
    )


ITEMS: tuple[MiniItem, ...] = (
    # --- aritmetica (12) ---
    _item("arith_01", "arith", "Compute (37 * 89) + 14.", (37 * 89) + 14),
    _item("arith_02", "arith", "Compute 2026 - 1487.", 2026 - 1487),
    _item("arith_03", "arith", "Compute the integer division 144 // 11.", 144 // 11),
    _item("arith_04", "arith", "Compute 7 * 8 * 9 - 26.", 7 * 8 * 9 - 26),
    _item("arith_05", "arith", "Compute (1234 + 5678) * 3.", (1234 + 5678) * 3),
    _item("arith_06", "arith", "Compute 100000 - 99991.", 100000 - 99991),
    _item("arith_07", "arith", "Compute 17*17 + 18*18.", 17 * 17 + 18 * 18),
    _item("arith_08", "arith", "Compute the absolute difference between 31 and 97.", abs(31 - 97)),
    _item("arith_09", "arith", "Compute 2**10 + 2**11.", 2**10 + 2**11),
    _item(
        "arith_10",
        "arith",
        "Compute the mean of 12, 35, 21, 46 as a decimal.",
        (12 + 35 + 21 + 46) / 4,
    ),
    _item("arith_11", "arith", "Compute 999 * 7.", 999 * 7),
    _item("arith_12", "arith", "Compute 5678 modulo 23.", 5678 % 23),
    # --- modular arithmetic (5) ---
    _item("mod_01", "mod", "Compute 7^13 mod 1000.", pow(7, 13, 1000)),
    _item("mod_02", "mod", "Compute 3^40 mod 7919.", pow(3, 40, 7919)),
    _item("mod_03", "mod", "Compute 2^100 mod 1000.", pow(2, 100, 1000)),
    _item("mod_04", "mod", "Compute 11^7 mod 97.", pow(11, 7, 97)),
    _item("mod_05", "mod", "Compute 5^50 mod 997.", pow(5, 50, 997)),
    # --- conversions (5) ---
    _item("conv_01", "conv", "Write 3552 in base 16, lowercase, no prefix.", hex(3552)[2:]),
    _item("conv_02", "conv", "Write 45 in base 2, no prefix.", bin(45)[2:]),
    _item("conv_03", "conv", "How many minutes are in 3 hours and 17 minutes?", 3 * 60 + 17),
    _item("conv_04", "conv", "Convert 15120 seconds to hours, as a decimal.", 15120 / 3600),
    _item("conv_05", "conv", "Convert 7.5 kilometers to meters.", int(7.5 * 1000)),
    # --- string ops (6) ---
    _item("str_01", "string", 'Reverse the word "programming".', "programming"[::-1]),
    _item("str_02", "string", 'How many letters does "serendipity" have?', len("serendipity")),
    _item("str_03", "string", 'Write the first 4 letters of "algorithm".', "algorithm"[:4]),
    _item(
        "str_04",
        "string",
        'Count how many times the letter "a" appears in "abracadabra".',
        "abracadabra".count("a"),
    ),
    _item("str_05", "string", 'Uppercase the word "quiet".', "quiet".upper()),
    _item("str_06", "string", 'Remove all spaces from "h e l l o".', "h e l l o".replace(" ", "")),
    # --- structured extraction (5) ---
    _json_item(
        "json_01",
        'Return JSON {"total": <sum of "scores">} only.',
        {"scores": [17, 4, 9], "team": "rossa"},
        {"total": sum([17, 4, 9])},
    ),
    _json_item(
        "json_02",
        'Return JSON {"max": <largest value>} only.',
        {"a": 3, "b": 12, "c": 7},
        {"max": max([3, 12, 7])},
    ),
    _json_item(
        "json_03",
        'Return JSON {"count": <number of keys>} only.',
        {"x": 1, "y": 2, "z": 3, "w": 4},
        {"count": len({"x": 1, "y": 2, "z": 3, "w": 4})},
    ),
    _json_item(
        "json_04",
        'Return JSON {"population": <value of "pop">} only.',
        {"city": "Rome", "pop": 2873000},
        {"population": 2873000},
    ),
    _json_item(
        "json_05",
        'Return JSON {"length": <number of items in "items">} only.',
        {"items": [4, 8, 15, 16, 23, 42]},
        {"length": len([4, 8, 15, 16, 23, 42])},
    ),
    # --- logic (4) ---
    _item(
        "logic_01",
        "logic",
        "Anna is 3 times as old as Ben. Ben is 8. How old will Anna be in 5 years?",
        3 * 8 + 5,
    ),
    _item(
        "logic_02",
        "logic",
        "Which value is larger, 7^4 or 2400? Answer with the larger value.",
        max(7**4, 2400),
    ),
    _item(
        "logic_03",
        "logic",
        "A number n is 5. If n is odd, replace n with 3n+1. What is n now?",
        3 * 5 + 1,
    ),
    _item(
        "logic_04",
        "logic",
        "How many days between 2025-01-01 and 2025-02-01 (difference)?",
        (date(2025, 2, 1) - date(2025, 1, 1)).days,
    ),
    # --- dates (3) ---
    _item(
        "date_01",
        "date",
        "Which day of the week (English name) was 2024-03-14?",
        date(2024, 3, 14).strftime("%A"),
    ),
    _item(
        "date_02",
        "date",
        "Which day of the week (English name) is 2026-11-10?",
        date(2026, 11, 10).strftime("%A"),
    ),
    _item(
        "date_03",
        "date",
        "Which day-of-year number is 2026-07-04 (1 = Jan 1)?",
        date(2026, 7, 4).timetuple().tm_yday,
    ),
)

assert 30 <= len(ITEMS) <= 50, f"suite fuori range: {len(ITEMS)} item"


def load_items() -> list[MiniItem]:
    return list(ITEMS)


__all__ = ["ITEMS", "SUITE_VERSION", "MiniItem", "load_items"]
