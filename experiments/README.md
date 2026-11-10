# Esperimenti

Un esperimento = una domanda precisa + disegno + dati grezzi + risultato.
Niente esperimenti senza domanda scritta PRIMA di eseguire (anti-hunting,
PLAN §0/§7): se il disegno non regge, l'esperimento non si fa.

Convenzione: `<NN>-<slug>/` con `domanda.md` (ipotesi, metriche, soglia di
"basta"), `run.sh` o script riproducibile, `results/` (ignorato da git;
commitare solo tabelle riassuntive dentro `domanda.md` o `REPORT.md`).

Elenco:

- `01-baseline-single-call/` — passata singola per nodo su 3 suite, 3 campioni/item, seed 1234 (Fase 2; artefatti grezzi nei direttori `<ts>-eval-<suite>-single/` companion). La calibrazione di Fase 1 vive in `calibration/` (non ha direttorio dedicato).
- `repro-probes/` — sonde di riproducibilità live a server idle (heavy+mid), commento in `reproducibility-check.md`.
- `reproducibility-check.md` — verifica riproducibilità del runner (mock CI + live mid/heavy, con appendice idle 2026-11-10).

Direttori `<ts>-eval-<suite>-single/`: run live autoritative della baseline
(elencate in `docs/2026-11-10-fase2-baseline.md`); uno con `SUPERSEDED.md`
non è autoritativo (run contaminata da caduta nodo heavy ~10:36Z).
