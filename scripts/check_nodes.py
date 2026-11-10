#!/usr/bin/env python3
"""Verifica i nodi in config/nodes.yaml: chat-completion minimale + fingerprint runtime.

Uso:  uv run python scripts/check_nodes.py [--config config/nodes.yaml] [--timeout 60]
Equivalente a `harness doctor`; mantiene l'output dettagliato (runtime, versione,
modelli caricati) per la baseline della Fase 0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from nodes import load_nodes_config, probe_node  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default=str(REPO_ROOT / "config" / "nodes.yaml"))
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    cfg = load_nodes_config(args.config)
    rc = 0
    for name, node in cfg.nodes.items():
        if not node.enabled:
            print(f"[skip] {name}: placeholder disabilitato (enabled: false)")
            continue
        print(f"[....] {name}: {node.endpoint} model={node.model}")
        st = probe_node(node, name=name, timeout=args.timeout)
        ok = st.reachable and st.chat_ok
        rc |= 0 if ok else 1
        print(f"[{'OK  ' if ok else 'FAIL'}] {name}")
        print(
            f"       runtime:  {st.runtime}"
            + (f" (Server: {st.server_header})" if st.server_header else "")
        )
        print(f"       versione: {st.version or 'n/d'}")
        print(f"       contesto: config={node.ctx}", end="")
        served_ctx = [m.get("meta", {}).get("n_ctx") for m in st.models if isinstance(m, dict)]
        print(f" serviti={served_ctx}")
        print(f"       modelli caricati: {[m.get('id') for m in st.models if isinstance(m, dict)]}")
        print(f"       modello configurato presente: {st.configured_model_present}")
        if st.chat_ok:
            print(f"       chat OK in {st.latency_s}s -> risposta: {st.chat_reply[:60]!r}")
        else:
            print(f"       chat FAIL: {st.error}")
    print("=== tutti i nodi attivi rispondono ===" if rc == 0 else "=== ALMENO UN NODO FALLITO ===")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
