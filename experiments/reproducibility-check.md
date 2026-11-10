# Verifica di riproducibilità della baseline

Obbligo di piano: riuscire una run a parità di seed/parametri deve dare la
stessa tabella (tolto il tempo reale, colonna 8 di `summary.md`).

## Livello 1 — CI, nodo mock (sempre verde, nessun nodo reale)

`tests/test_eval_runner.py::test_riproducibilita_stesso_seed_stesse_righe`:
due run complete su nodo mock, tabelle `summary.md` identiche riga per riga
dopo normalizzazione del tempo.

## Livello 2 — live mid (tabbyAPI), server dedicato alla run

Due run `semi --nodes mid --max-items 4 --samples 3 --seed 1234` a pochi
secondi di distanza (2026-11-10 10:28Z), poi `scripts/repro_compare.py`:

- `TABLE_EQUAL: True` — tabella identica (tempo normalizzato)
- `ROWS_EQUAL: True` su 12 righe — stesso `answer_sha` E stessi token per
  ogni (item, sample): bit-exact.

## Livello 3 — live heavy (llama.cpp remoto) sotto carico

Due run `verificabili --nodes heavy --max-items 1 --samples 3 --seed 1234`
eseguite MENTRE altri campioni heavy giravano (10:29Z):

- esiti `pass` identici per (item, sample) (`scripts/repro_outcomes.py`,
  confronto ordinato — l'ordine di scrittura segue l'ordine di completamento
  dei campioni concorrenti);
- `answer_sha` e token DIVERSI: llama.cpp in batching continuo non è
  deterministico a livello di virgola (batch composition variabile), e su
  catene di ragionamento lunghe una differenza infinitesima devia il greedy.

Conclusione: il runner è deterministico; l'uguaglianza bit-exact live vale
sul nodo tabbyAPI (mid); sul nodo llama.cpp (heavy) la garanzia osservabile è
«esiti identici, token/SHA no» — la baseline riporta media±sd proprio perché
il server stesso non è una funzione pura. (L'appendice sotto mostra che per
heavy NON dipende dal carico.)

## Appendice — riverifica a server idle (2026-11-10 11:39-11:41Z)

Nessun'altra run in corso su entrambi i nodi. Due run consecutive a stesso
seed/parametri, output isolate in scratch e poi archiviate in
`experiments/repro-probes/`, stesso metodo (`run_dir` + `repro_compare.py` +
`repro_outcomes.py`).

- heavy: `verificabili --nodes heavy --max-items 1 --samples 3 --seed 1234`
  (`repro-probes/heavy-idle-a` vs `heavy-idle-b`): `OUTCOMES_EQUAL: True` ma
  `SHA_TOKENS_EQUAL: False`, `TABLE_EQUAL: False` (tok/campione
  1226.7±159.5 vs 1079.0±192.7; sha diversi su tutte e 3 le righe).
- mid (controllo di parità, prima claim livello 2):
  `semi --nodes mid --max-items 4 --samples 3 --seed 1234`
  (`repro-probes/mid-idle-a` vs `mid-idle-b`): `TABLE_EQUAL: True`,
  `ROWS_EQUAL: True` (12 righe), `SHA_TOKENS_EQUAL: True` — bit-exact
  anche a server idle, come in carico.

Correzione della conclusione del livello 3: la non-riproducibilità bit-exact
di heavy **non è causata dal batching concorrente** — persiste a server
idle. È una proprietà del runtime llama.cpp (numerica dipendente dalla
composizione dei slot/continuous batching, modello MoE): a parità di seed
garantisce esiti (pass/score), non il testo. Conseguenza per Fase 3: i
confronti single-vs-ledger su heavy vanno fatti su esiti e distribuzioni
(media±sd), mai su sha di risposta.
