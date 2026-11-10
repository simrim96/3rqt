# Baseline single-call — Fase 2 (2026-11-10)

Ipotesi: quantificare il pavimento single-call (accuracy, varianza tra campioni,
token, tempo reale) per nodo × suite, prima del ledger di Fase 3.
Setup: `harness eval --suite <s> --mode single --samples 3 --seed 1234`, nodi reali
heavy+mid, sampling greedy documentato in `docs/sampling-params.md` (cap corretti,
vedi `docs/DECISIONS.md` D5). Aperti: giudice = altro nodo, punteggio `low_conf`.

| nodo | suite | item | camp. | pass-rate | tok/camp (med±std) | s/camp (med±std) | run |
|---|---|---|---|---|---|---|---|
| heavy | verificabili | 25 | 75 | 94.7% | 3081.6±2603.7 | 84.5±78.1 | 20261110T093103Z-eval-verificabili-single |
| | | | | item instabili tra campioni: vv_fib_04 | | | |
| heavy | semi | 12 | 36 | 91.7% | 554.3±150.2 | 19.5±20.7 | 20261110T105245Z-eval-semi-single |
| heavy | aperti | 8 | 24 | 100.0% | 6077.9±3130.3 | 178.7±178.5 | 20261110T105729Z-eval-aperti-single |
| mid | verificabili | 25 | 75 | 88.0% | 355.9±71.6 | 4.2±1.9 | 20261110T094443Z-eval-verificabili-single |
| mid | semi | 12 | 36 | 83.3% | 289.2±74.3 | 1.7±0.6 | 20261110T095002Z-eval-semi-single |
| mid | aperti | 8 | 24 | 79.2% | 4112.8±1487.5 | 94.6±54.2 | 20261110T105254Z-eval-aperti-single |
| | | | | item instabili tra campioni: op_explain_01 | | | |

Instabilità tra i 3 campioni: 2.2% degli item (nodi×suite) cambia esito;
è la varianza che il confronto modalità di Fase 3 dovrà battere.

## Decisione

- La modalità single ha un pavimento misurato e riproducibile: baseline per la ledger.
- Gli item aperti sono `low_confidence` per costruzione (giudice = altro modello).
- Verifica riproducibilità (stesso seed, sottoinsieme ripetuto):
  `experiments/reproducibility-check.md` (mid bit-exact; heavy esiti-identici
  anche a server idle; sonde grezze in `experiments/repro-probes/`).
