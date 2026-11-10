# 01 — Baseline single-call (Fase 2)

## Domanda (scritta PRIMA dell'esecuzione, 2026-11-10)

Con un solo chiamore per nodo reale (heavy, mid), senza ledger:

1. che pass-rate raggiungono le tre suite (verificabili / semi / aperti)?
2. quanta varianza c'è tra ≥3 campioni a seed diverso a sampling greedy?
3. quanto costa in token e tempo reale un campione medio per suite?

**Ipotesi**: heavy > mid su verificabili (più contesto di ragionamento) e su
aperti; mid competitivo su semi (output brevi e strutturati); varianza bassa
su verificabili/semi (greedy), alta su aperti (rubrica + giudice).

**Metriche**: pass-rate medio ± sd per (nodo × suite) su 3 campioni/item;
token totali e wall-time per campione; per gli aperti anche punteggio rubrica.

**Soglia di "basta"**: tutte le celle nodo×suite popolate (3 suite × 2 nodi ×
≥3 campioni/item); tabella e riproducibilità verificate; `make check` verde.

## Setup

- Nodi: heavy `http://llm-server:8080/v1` (ctx 144k), mid
  `http://localhost:8080/v1` (ctx 72k, concorrenza 1). Edge fuori scope.
- Parametri: `docs/sampling-params.md` (greedy; cap 8192/4096; reasoning mid
  OFF via `enable_thinking=false`, heavy ON per assenza di knob — D5).
- Giudice incrociato (heavy↔mid), budget per-nodo (D5).
- `--samples 3 --seed 1234`; suite versionate con golden data in
  `src/evals/suites/<nome>/`.
- Esecuzione: `run.sh` (questo stesso script); output in
  `experiments/<ts>-eval-<suite>-single/` (results.jsonl + summary.md +
  meta.json con git hash + fingerprint runtime).

## Risultati

Run autoritative (0 errori riga; le sostituite hanno `SUPERSEDED.md`):

| nodo | suite | item | camp. | pass-rate | tok/camp (med±std) | s/camp (med±std) | run |
|---|---|---|---|---|---|---|---|
| heavy | verificabili | 25 | 75 | 94.7% | 3081.6±2603.7 | 84.5±78.1 | `20261110T093103Z` |
| heavy | semi | 12 | 36 | 91.7% | 554.3±150.2 | 19.5±20.7 | `20261110T105245Z` |
| heavy | aperti (low_conf) | 8 | 24 | 100.0% | 6077.9±3130.3 | 178.7±178.5 | `20261110T105729Z` |
| mid | verificabili | 25 | 75 | 88.0% | 355.9±71.6 | 4.2±1.9 | `20261110T094443Z` |
| mid | semi | 12 | 36 | 83.3% | 289.2±74.3 | 1.7±0.6 | `20261110T095002Z` |
| mid | aperti (low_conf) | 8 | 24 | 79.2% | 4112.8±1487.5 | 94.6±54.2 | `20261110T105254Z` |

Totale: 270 righe di risultato, 0 errori nelle run autoritative. Tabella
completa e righe instabili in `docs/2026-11-10-fase2-baseline.md`
(`scripts/summarize_fase2.py`). Instabilità tra campioni: 2 item su 90
celle item×nodo cambiano esito tra i 3 campioni (2,2% delle righe):
`vv_fib_04` (heavy), `op_explain_01` (mid).

Note: (a)heavy→giudice mid 24/24 vs mid→giudice heavy 19/24: la
severità dei due giudici non è calibrata, gli aperti restano
`low_confidence` per costruzione; (b) il costo heavy su aperti è ~1,5× i
token e ~2× il tempo di mid a parità di item; (c) mid vince su costo
(≈5-10× meno token/tempo) con gap di qualità minimo su semi.

## Decisione

- Ipotesi confermata su verificabili (94,7 > 88,0) e aperti (100 > 79,2,
  low_conf); su semi mid è competitivo in termini di COSTO (8,4 pt in meno
  con ~2× meno token e ~11× meno tempo), non di accuracy.
- Ipotesi "varianza alta su aperti" NON confermata: con greedy + soglia di
  rubrica l'instabilità è bassa ovunque (2,2%). Il rischio sugli aperti è
  il bias incrociato del giudice, non la varianza tra campioni.
- Soglia di detection per Fase 3: un guadagno del ledger è credibile solo
  se supera il pavimento di varianza misurato qui; su heavy il confronto
  va fatto su esiti/distribuzioni, mai su sha (heavy non è bit-riproducibile
  nemmeno idle — `experiments/reproducibility-check.md`, appendice).
- Parametri di sampling: confermati `docs/sampling-params.md` (D5). Nessun
  cambio default: la baseline è il pavimento, i default cambieranno solo
  con misure successive.
