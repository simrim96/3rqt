"""Caricamento e validazione di config/nodes.yaml (schema PLAN §4).

Errori comuni intercettati in fase di caricamento (criterio di uscita Fase 1):
endpoint mancante/vuoto/non-http, contesto implausibile (typos tipo 131072000
o 13), concorrenza fuori range, `policy.fallback_role_to` verso nodo inesistente
e ruoli non allowlistati rispetto a config/roles.yaml.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

Availability = Literal["always", "best_effort", "manual"]

_CTX_MIN = 512
_CTX_MAX = 4_194_304  # 4M: sopra e' quasi sempre un typo
_ENDPOINT_RE = re.compile(r"^https?://\S+$")


class Node(BaseModel):
    """Uno slot logico di calcolo: endpoint OpenAI-compatibile + vincoli."""

    model_config = {"populate_by_name": True, "extra": "forbid"}

    endpoint: str
    model: str
    # Default neutro (PLAN §0.2: nessun nome di famiglia nel codice): la famiglia
    # va dichiarata in config; il validatore _non_vuoto boccia il default vuoto.
    family: str = Field(default="", validate_default=True)
    ctx: int | None = None
    concurrency: int = 1
    availability: Availability = "best_effort"
    roles_allowed: list[str] = Field(default_factory=list)
    extra_models: list[str] = Field(default_factory=list)
    api_key: str | None = None
    enabled: bool = True  # estensione nostra: placeholder disabilitabili

    @field_validator("endpoint")
    @classmethod
    def _endpoint_valido(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v:
            raise ValueError("endpoint mancante o vuoto")
        if not _ENDPOINT_RE.match(v):
            raise ValueError(
                f"endpoint {v!r} non valido: serve un URL assoluto http(s)://host[:porta][/v1]"
            )
        return v

    @field_validator("model", "family")
    @classmethod
    def _non_vuoto(cls, v: str, info) -> str:
        if not v.strip():
            raise ValueError(f"{info.field_name} mancante o vuoto")
        return v.strip()

    @field_validator("ctx")
    @classmethod
    def _ctx_plausibile(cls, v: int | None) -> int | None:
        if v is None:
            return v
        if not _CTX_MIN <= v <= _CTX_MAX:
            raise ValueError(
                f"ctx {v} implausibile (atteso tra {_CTX_MIN} e {_CTX_MAX}: "
                "controlla zeri o unita' di misura)"
            )
        return v

    @field_validator("concurrency")
    @classmethod
    def _concorrenza_ok(cls, v: int) -> int:
        if not 1 <= v <= 32:
            raise ValueError(f"concurrency {v} fuori range (1..32)")
        return v


class Policy(BaseModel):
    model_config = {"extra": "forbid"}

    quality_first: bool = True
    max_rounds: int = 8
    fallback_role_to: str | None = None
    reassign_roles_on_calibration: bool = True


class NodesConfig(BaseModel):
    model_config = {"extra": "forbid"}

    nodes: dict[str, Node]
    policy: Policy = Field(default_factory=Policy)

    @model_validator(mode="after")
    def _fallback_esistente(self) -> NodesConfig:
        fb = self.policy.fallback_role_to
        if fb is not None and fb not in self.nodes:
            raise ValueError(
                f"policy.fallback_role_to={fb!r} non corrisponde a nessun nodo "
                f"(nodi disponibili: {sorted(self.nodes)})"
            )
        return self

    def enabled_nodes(self) -> dict[str, Node]:
        return {name: n for name, n in self.nodes.items() if n.enabled}

    def nodes_for_role(self, role: str) -> dict[str, Node]:
        return {name: n for name, n in self.enabled_nodes().items() if role in n.roles_allowed}

    def config_hash(self) -> str:
        """Hash stabile del contenuto (per tracciare calibrazioni e capability)."""
        import hashlib
        import json

        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


def validate_roles_allowlist(cfg: NodesConfig, roles: Mapping[str, object]) -> None:
    """Ogni ruolo citato in roles_allowed deve esistere in roles.yaml (PLAN §4)."""
    unknown: dict[str, list[str]] = {}
    for node_name, node in cfg.nodes.items():
        for role in node.roles_allowed:
            if role not in roles:
                unknown.setdefault(role, []).append(node_name)
    if unknown:
        dettagli = "; ".join(f"{r} (nodi: {', '.join(n)})" for r, n in sorted(unknown.items()))
        raise ValueError(f"ruoli non dichiarati in roles.yaml: {dettagli}")


def load_nodes_config(path: str | Path) -> NodesConfig:
    """Carica e valida il registro dei nodi. Errori chiari, mai default silenziosi."""
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or "nodes" not in raw:
        raise ValueError(f"{path}: atteso un mapping con chiave 'nodes'")
    try:
        return NodesConfig.model_validate(raw)
    except ValidationError as exc:  # pragma: no cover - messaggio puramente diagnostico
        raise ValueError(f"{path}: configurazione non valida\n{exc}") from exc


def load_harness_config(
    nodes_path: str | Path, roles_path: str | Path | None = None
) -> tuple[NodesConfig, dict]:
    """Carica nodes.yaml + roles.yaml e valida l'allowlist incrociata.

    Se `roles_path` e' omesso si cerca `roles.yaml` accanto ai nodi; se non
    esiste si salta la cross-validation (con warning nel campo `warning`).
    Ritorna (config_nodi, ruoli). La validazione allowlist e' obbligatoria
    quando il file ruoli esiste.
    """
    from roles import load_roles_config

    nodes_path = Path(nodes_path)
    cfg = load_nodes_config(nodes_path)
    if roles_path is None:
        cand = nodes_path.parent / "roles.yaml"
        roles_path = cand if cand.exists() else None
    if roles_path is None:
        return cfg, {}
    roles = load_roles_config(roles_path)
    validate_roles_allowlist(cfg, roles)
    return cfg, roles
