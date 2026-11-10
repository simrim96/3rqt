# Three Racqwen in a Trenchcoat

Harness che coordina 3 modelli Qwen sostituibili su macchine diverse, con
ruoli legati a capacità misurate. Piano completo: [`docs/PLAN.md`](docs/PLAN.md).

## Setup

```bash
uv sync          # Python 3.12, deps + dev deps
uv run harness --help
uv run pytest    # suite test
make check       # lint (ruff) + test  == gate CI
uv run python scripts/check_nodes.py   # ovvero: uv run harness doctor
```

## Struttura (PLAN §2)

- `config/` — `nodes.yaml` (heavy/mid/edge), `roles.yaml` (parametri per ruolo)
- `src/nodes` — registro nodi + adapter OpenAI-compatibile
- `src/roles` — definizioni ruolo (config-driven)
- `src/ledger` — stato su filesystem per task (deep mode)
- `src/sandbox` — esecuzione codice/test (Fase 3+, sandbox vera in Fase 9)
- `src/scheduler` — code per nodo (scheletro; Fase 4)
- `src/evals` — suite e runner di valutazione (Fase 2)
- `src/cli` — entrypoint `harness`
- `scripts/check_nodes.py` — health check dei nodi (runtime/versione/modelli)
- `experiments/` — esperimenti numerati (README dentro)
- `tests/` — test per ogni componente

## Regole di lavoro (PLAN §0, vincolanti)

- Nessun commit automatico: i commit li fa l'umano.
- Nessun nome di modello/runtime hardcodato nel codice: tutto da `config/`.
- Ogni feature ha un test.
- Non toccare i servizi attivi sui nodi senza ok esplicito.

## Stato

Fase 0 completata: repo, tooling, piano operativo, health check nodi.
Vedi i riepiloghi dei task nel Kanban per la baseline.
