"""Ruoli: planner, worker, verifier, reviewer, router, edge (Fasi 3+).

Definizizioni e parametri in config/roles.yaml; assegnazione ai nodi dalla
calibrazione (Fase 1). Nessun nome di modello nel codice (PLAN §0.2).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError


class Role(BaseModel):
    description: str = ""
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


def load_roles_config(path: str | Path) -> dict[str, Role]:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "roles" not in raw:
        raise ValueError(f"{path}: atteso un mapping con chiave 'roles'")
    try:
        return {name: Role.model_validate(cfg or {}) for name, cfg in raw["roles"].items()}
    except ValidationError as exc:
        raise ValueError(f"{path}: configurazione ruoli non valida\n{exc}") from exc


__all__ = ["Role", "load_roles_config"]
