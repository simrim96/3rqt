"""Estrazione e confronto delle risposte.

- ``extract_code_block``: primo blocco ```python (fallback: testo intero).
- ``extract_final_line``: l'ultima riga non vuota parsabile come JSON object
  (i ragionamenti intermedi contengono JSON provvisori: vince l'ultimo).
- ``validate_row`` / ``canonicalize_row``: mini-sottinsieme JSON Schema per il
  vincolo "una riga" (type con pipe, enum, any_of, required,
  additionalProperties) + normalizzazione canonica: un golden e una risposta
  semanticamente equivalenti producono la STESSA stringa canonica.
"""

from __future__ import annotations

import json
import re
from typing import Any

_FENCE_PY = re.compile(r"```(?:python|py)\n(.*?)```", re.DOTALL | re.IGNORECASE)
_TYPES = {"string", "integer", "number", "boolean", "null"}


def extract_code_block(text: str) -> str:
    match = _FENCE_PY.search(text or "")
    return match.group(1).strip() if match else (text or "").strip()


def extract_final_line(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Restituisce (riga, None) o (None, motivo_errore)."""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for line in reversed(lines):
        if line.startswith("```"):
            continue
        candidate = line
        if candidate.startswith("Answer:"):
            candidate = candidate[len("Answer:") :].strip()
        try:
            obj = json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj, None
        return None, "last_json_line_not_object"
    return None, "no_json_line"


def _type_ok(value: Any, t: str) -> bool:
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    if t == "null":
        return value is None
    return False


def _types_of(prop: dict[str, Any]) -> list[str]:
    types = prop.get("type", "string")
    types = types.split("|") if isinstance(types, str) else list(types)
    return [t.strip() for t in types]


def validate_row(row: dict[str, Any], schema: dict[str, Any]) -> str | None:
    """None se la riga e' valida per lo schema, altrimenti il motivo."""
    if schema.get("type") != "object":
        return "schema_type_not_object"
    props: dict[str, Any] = schema.get("properties", {})
    for req in schema.get("required", []):
        if req not in row:
            return f"missing_field:{req}"
    if schema.get("additionalProperties") is False:
        extra = set(row) - set(props)
        if extra:
            return f"extra_fields:{sorted(extra)}"
    for key, value in row.items():
        prop = props.get(key)
        if prop is None:
            continue
        types = _types_of(prop)
        if not any(_type_ok(value, t) for t in types):
            return f"bad_type:{key}:expected={'|'.join(types)}:got={type(value).__name__}"
        if "enum" in prop and value not in prop["enum"]:
            return f"enum_violation:{key}={value!r}"
    return None


def _norm_value(value: Any, prop: dict[str, Any]) -> Any:
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    any_of = prop.get("any_of")
    if any_of and value in any_of:
        return any_of[0]  # alternativa equivalente -> forma canonica
    if isinstance(value, str):
        value = value.strip()
        if any_of and value in any_of:
            return any_of[0]
    if prop.get("type") == "integer" and isinstance(value, float) and value.is_integer():
        value = int(value)
    return value


def canonicalize_row(row: dict[str, Any], schema: dict[str, Any]) -> str:
    """Serializzazione canonica: chiavi dell'Schema presenti, ordinate, senza
    spazi; campi dichiarati con default omessi se pari al default."""
    props: dict[str, Any] = schema.get("properties", {})
    out: dict[str, Any] = {}
    for key in sorted(set(props) & set(row)):
        value = _norm_value(row[key], props[key])
        if "default" in props[key] and value == props[key]["default"]:
            continue
        out[key] = value
    return json.dumps(out, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def match_row(
    row: dict[str, Any], schema: dict[str, Any], golden_canonicals: set[str]
) -> tuple[bool, str, str | None]:
    """(pass, riga_canonica, motivo). Il confronto e' sulle righe canoniche."""
    error = validate_row(row, schema)
    if error:
        return False, "", error
    canon = canonicalize_row(row, schema)
    return canon in golden_canonicals, canon, None if canon in golden_canonicals else "mismatch"


__all__ = [
    "canonicalize_row",
    "extract_code_block",
    "extract_final_line",
    "match_row",
    "validate_row",
]
