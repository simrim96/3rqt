"""Test del caricamento del registro nodi (config/nodes.yaml reale + casi limite)."""

import re
from pathlib import Path

import pytest
import yaml

from nodes.config import NodesConfig, load_nodes_config  # noqa: F401 (NodesConfig:Smoke test del tipo pubblico)

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG = REPO_ROOT / "config" / "nodes.yaml"


def test_config_reale_carica():
    cfg = load_nodes_config(REAL_CONFIG)
    assert set(cfg.nodes) == {"heavy", "mid", "edge"}
    assert cfg.nodes["heavy"].enabled
    assert cfg.nodes["heavy"].ctx == 131072
    assert cfg.nodes["mid"].extra_models  # secondo modello servito sullo stesso endpoint
    assert not cfg.nodes["edge"].enabled
    assert cfg.enabled_nodes().keys() == {"heavy", "mid"}


def test_policy():
    cfg = load_nodes_config(REAL_CONFIG)
    assert cfg.policy.quality_first is True
    assert cfg.policy.fallback_role_to == "heavy"
    assert 1 <= cfg.policy.max_rounds <= 32


def test_roles_allowed_coerenti():
    cfg = load_nodes_config(REAL_CONFIG)
    planner_nodes = cfg.nodes_for_role("planner")
    assert "heavy" in planner_nodes
    assert cfg.nodes_for_role("titler") == {}  # solo edge, che e' disabilitato


def test_campo_sconosciuto_bocciato(tmp_path):
    bad = tmp_path / "nodes.yaml"
    bad.write_text(
        "nodes:\n  x:\n    endpoint: http://a/v1\n    model: m\n    family: test\n    typo: 1\n"
    )
    with pytest.raises(ValueError, match="non valida"):
        load_nodes_config(bad)


def test_file_senza_nodes_bocciato(tmp_path):
    bad = tmp_path / "nodes.yaml"
    bad.write_text(yaml.safe_dump({"nope": {}}))
    with pytest.raises(ValueError, match="chiave 'nodes'"):
        load_nodes_config(bad)


# --- G1 (criterio di uscita PLAN Fase 1): gli errori di configurazione comuni
# devono essere intercettati da load_nodes_config con messaggi chiari.


def _nodo_base(**extra):
    node = {"endpoint": "http://a/v1", "model": "m", "family": "test", "ctx": 8192}
    node.update(extra)
    return node


@pytest.mark.parametrize(
    ("yaml_obj", "match"),
    [
        # endpoint: assente, vuoto, non-http, privo di schema
        ({"nodes": {"x": {"model": "m", "family": "test"}}}, "Field required"),
        (
            {"nodes": {"x": {"endpoint": "", "model": "m", "family": "test"}}},
            "endpoint mancante o vuoto",
        ),
        (
            {"nodes": {"x": {"endpoint": "ftp://a/v1", "model": "m", "family": "test"}}},
            "non valido",
        ),
        (
            {"nodes": {"x": {"endpoint": "localhost:8080", "model": "m", "family": "test"}}},
            "non valido",
        ),
        # ctx implausibile: troppo grande (typo con zeri) e troppo piccolo
        ({"nodes": {"x": _nodo_base(ctx=131_072_000)}}, "ctx 131072000 implausibile"),
        ({"nodes": {"x": _nodo_base(ctx=13)}}, "ctx 13 implausibile"),
        # concurrency fuori range
        ({"nodes": {"x": _nodo_base(concurrency=0)}}, "concurrency 0 fuori range"),
        ({"nodes": {"x": _nodo_base(concurrency=33)}}, "concurrency 33 fuori range"),
        # fallback_role_to verso un nodo inesistente
        (
            {"nodes": {"x": _nodo_base()}, "policy": {"fallback_role_to": "fantasma"}},
            r"policy\.fallback_role_to='fantasma'",
        ),
        # family non dichiarata: nessun default di famiglia nel codice (PLAN §0.2)
        ({"nodes": {"x": {"endpoint": "http://a/v1", "model": "m"}}}, "family mancante o vuoto"),
    ],
    ids=[
        "endpoint_assente",
        "endpoint_vuoto",
        "endpoint_non_http",
        "endpoint_senza_schema",
        "ctx_troppo_grande",
        "ctx_troppo_piccolo",
        "concurrency_zero",
        "concurrency_troppo_grande",
        "fallback_ruolo_inesistente",
        "family_assente",
    ],
)
def test_errori_config_comuni_bocciati(tmp_path, yaml_obj, match):
    bad = tmp_path / "nodes.yaml"
    bad.write_text(yaml.safe_dump(yaml_obj, sort_keys=True))
    with pytest.raises(ValueError) as excinfo:
        load_nodes_config(bad)
    messaggio = str(excinfo.value)
    assert "non valida" in messaggio
    # il messaggio deve anche spiegare IL motivo specifico, non solo "non valida"
    assert re.search(match, messaggio), messaggio


def test_config_minima_valida_accettata(tmp_path):
    """Controllo positivo: i validatori non bloccano una config legittima."""
    good = tmp_path / "nodes.yaml"
    good.write_text(
        yaml.safe_dump({"nodes": {"x": _nodo_base()}, "policy": {"fallback_role_to": "x"}})
    )
    cfg = load_nodes_config(good)
    assert cfg.nodes["x"].family == "test"
    assert cfg.policy.fallback_role_to == "x"


def test_nessun_modello_hardcodato_nel_codice():
    """PLAN §0.2: i nomi dei modelli reali vivono solo in config/ e docs/."""
    forbidden = ["qwen3.8-flash-next-unsloth", "Qwen3.8-27B-exl3", "DFlash2"]
    for src_dir in (REPO_ROOT / "src", REPO_ROOT / "scripts"):
        for py in src_dir.rglob("*.py"):
            text = py.read_text(encoding="utf-8").lower()
            for name in forbidden:
                assert name.lower() not in text, f"{name} hardcodato in {py}"
