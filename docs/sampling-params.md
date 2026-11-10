# Parametri di campionamento fissi per modello (Fase 2)

Spec dei parametri di sampling usati dall'harness `eval --mode single`.
I valori vivono in `src/evals/runner.py` (`SAMPLING`, `JUDGE_SAMPLING`) e
vengono registrati in ogni `experiments/<id>/meta.json` (`setup.sampling`,
`setup.judge_sampling`), così ogni run porta con sé la propria configurazione.

Principio: **determinismo dove possibile** — greedy (temperature 0, top_p 1)
per tutti i nodi. Confronti tra modelli devono isolare il modello, non il
sampling; la varianza residua tra campioni a seed diverso è quella che la
baseline riporta come media±sd.

## Nodi generatori

| nodo | modello (calibration/) | temperature | top_p | max_tokens | reasoning | seed_base |
|---|---|---|---|---|---|---|
| heavy | qwen3.8-flash-next-unsloth-ud-q4_k_xl (llama.cpp) | 0.0 | 1.0 | 8192 | n/d (llama.cpp remoto: niente knob per-request) | 1234 |
| mid | Qwen3.8-27B-exl3-3.0 (tabbyAPI) | 0.0 | 1.0 | 4096 | **reasoning OFF**: `chat_template_kwargs.enable_thinking=false` (`thinking_ratio:0.0` da solo è inefficace — D5) | 1234 |
| edge | — non disponibile: fuori scope Fase 2 | 0.0 | 1.0 | 512 | `thinking: false` (definizione, mai usata) | 1234 |

Note:

- `max_tokens` è un *cap*, non un budget: gli item delle tre suite chiedono
  risposte brevi (codice ≤ ~600 tok, righe strutturate, testi ≤ 250 parole).
- `extra_body` passa al provider solo chiavi note all'adapter (Fase 1): il
  mid elimina i parametri non supportati senza far fallire la chiamata.
- Il seed effettivo di ogni campione è `seed_base + sample` (campione 0,1,2
  …): riproducibilità per-campione e varietà tra campioni a parità di greedy
  (i server OpenAI-compat rispettano il seed solo approssimativamente su
  batch continuo — da qui la varianza misurata comunque).

## Giudice (suite `aperti`)

Parametri base condivisi: temperature 0.0, top_p 1.0, seed_base 999 (distinto
dai generatori per tracciabilità), `judge_node_for()` garantisce modello
**diverso** dal generatore (heavy↔mid — vincolo di piano: mai autoscore).
Budget e knob per-node (`judge_sampling_for()`), misurati in live:

| nodo giudice | max_tokens | reasoning | motivo |
|---|---|---|---|
| heavy | 4096 | n/d (nessun knob) | il reasoning occupa ~600-700 tok: con cap 800 l'output veniva troncato **prima** della riga JSON (D5) |
| mid | 2048 | OFF (`enable_thinking=false`, come in generazione) | idem: senza knob efficace il reasoning mangiava il budget |

I risultati `aperti` sono marcati `low_confidence: true` indipendentemente
dal giudice: la rubrica è una misura, non una verità (PLAN §3 Fase 2).

## Riproduzione di una baseline

```bash
uv run harness eval --suite <verificabili|semi|aperti> --mode single \
  --samples 3 --seed 1234            # nodi = calibrati (heavy, mid)
```

A parità di suite/seed/parametri il runner è deterministico **tolto il tempo
reale**: verifica automatizzata in `tests/test_eval_runner.py`
(`test_riproducibilita_stesso_seed_stesse_righe`, nodo mock) e verifica live
documentata in `experiments/reproducibility-check.md`.
