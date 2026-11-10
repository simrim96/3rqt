"""Grader deterministico per la mini-suite: normalizzazione + confronto esatto.

Estrae la risposta dall'output del modello (ultima riga non vuota, pulita da
markdown/punteggiatura), normalizza in base al tipo di item e confronta con la
golden answer. Nessun LLM-as-judge: verificabilita' totale (guardrail PLAN §0).
"""

from __future__ import annotations

import json
import re

from evals.mini.items import MiniItem

_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def extract_answer(text: str) -> str:
    """Ultima riga non vuota, rimossi markup markdown e punteggiatura finale."""
    if not text or not text.strip():
        return ""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if not lines:
        return ""
    ans = lines[-1]
    ans = re.sub(r"^[*`#>\-]+\s*", "", ans)
    ans = re.sub(r"\s*[*`]+$", "", ans)
    ans = ans.strip().strip("`").strip()
    # "Answer: 42" -> "42"
    m = re.match(r"^(?:answer|risposta|result|the answer is)\s*[:=]\s*(.+)$", ans, re.IGNORECASE)
    if m:
        ans = m.group(1).strip()
    return ans.rstrip(".。;").strip()


def _norm_num(s: str) -> str | None:
    m = _NUM_RE.search(s.replace(",", ""))
    if not m:
        return None
    val = float(m.group(0))
    return str(int(val)) if val == int(val) else repr(val)


def _norm_json(s: str) -> str | None:
    m = _JSON_RE.search(s)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def normalize(kind: str, raw: str) -> str:
    s = extract_answer(raw)
    if kind == "json":
        return _norm_json(s) or s.lower()
    if _NUM_RE.fullmatch(s.replace(",", "").strip()) or re.fullmatch(r"[-+\d., ]+", s or "x"):
        return _norm_num(s) or s.lower()
    return s.lower()


def grade(item: MiniItem, output: str) -> bool:
    return normalize(item.kind, output) == normalize(item.kind, item.golden)


__all__ = ["extract_answer", "grade", "normalize"]
