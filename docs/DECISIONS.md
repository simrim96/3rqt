# Decisioni operative (log)

Registra qui ogni scelta concordata con l'utente che vincola le fasi. I worker le rispettano; modifiche solo con nuovo ingresso firmato "UTENTE".

## D1 (2026-11-10, aggiornata in D7) — Slot edge: telefono Android via USB → SOPPIANTATA da D7 (piano B)
- Edge = telefono dell'utente, non Raspberry.
- Connessione **cablata USB-C** per ridurre la latenza: USB tethering (RNDIS/NCM, interfaccia `usb0`/`rndis0` sul laptop) oppure `adb forward tcp:<porta> tcp:<porta>` se il tethering è indisponibile. Endpoint dichiarato in `config/nodes.yaml` come nodo normale (OpenAI-compatibile).
- Stack参考 (verificare doc corrente a tempo di implementazione, regola §0.3): Termux + llama.cpp build nativa → `llama-server --host 0.0.0.0 -c <=4096 -t 4 -fit off`; modello fascia 0.4–0.6B GGUF Q4 (dimensionare su SoC/RAM reali del telefono in fase di calibrazione; hot/cap termico: usare `-t 4` e budget brevi).
- Il nodo edge è `availability: best_effort`; il piano lo prevede già.
- **Requisiti hw minimi per un telefono (piano B)** — nessuna dipendenza da modelli specifici, feature da leggere da `/proc/cpuinfo` (mai dedurle dal nome core): big core ARM con **dotprod** (A76/A77/A78/X1 o superiori), **i8mm** preferibile, ≥2 big core, ≥6GB RAM (≥3GB liberi), Android 11+ (verificare limite ai processi figli: Android 12+ lo impone), connessione cablata (D1). Soglie operative: prefill ≥15 tok/s in sostenuta, task edge <60s end-to-end, termica sotto controllo (D7). Il telefono in dotazione all'utente rientra in una fascia entry (big core A75 senza dotprod, 4GB) quindi **atteso non qualificato** — la qualificazione B.15 decide, non la presunzione. Se non qualificato: profilo 2 nodi senza edge (F7) o attendere il nodo primario.

## D2 (2026-11-10) — Fast path: tolleranza regressione = zero
- Criterio F6 confermato: **nessuna regressione statisticamente significativa** sui task che il fast path instrada (default del piano).
- L'eventuale miglioramento è obiettivo di esperimento, non assunzione: va misurato nella suite, che deve includere task estratti dai progetti reali dell'utente (già in piano F2).

## D3 (2026-11-10) — Sandbox: podman di default, worktree come fallback
- Overhead prestazionale irrilevante: il workload sandbox è CPU-bound (test/build/lint) e il costo del container è ~0–2% runtime + avvio ~0.2–0.5s (riducibile con immagine warm), contro latenze LLM di secondi.
- Default: **podman rootless**, `--network=none`, tmpfs, `--rm` (riduce anche l'attrito delle approve del terminale).
- Fallback profilo portabilità (macchine senza podman): git worktree + `systemd-run --scope` con limiti CPU/Mem/Time.
- Nessuna sandbox tocca l'inferenza: i nodi LLM restano fuori dal sandbox.

## D4 (2026-11-10, Fase 2) — Suite verificabili: dataset in-repo, non LiveCodeBench scaricato
- L'ambiente di sviluppo non può scaricare il dataset HF di LiveCodeBench (rete limitata; vincolo §0 sui sorgenti verificabili in-repo).
- Costruiti 25 item equivalenti (2×25=50 stdin/stdout unit-test in sandbox, golden = output della soluzione di riferimento in `solutions/`, content-addressed nella versione suite), ispirati a LiveCodeBench release_v6 + task "reali" parametrizzati, come previsto dal corpo del task Fase 2.
- Ripercussione sui numeri: i punteggi verificabili non sono confrontabili direttamente con leaderboard LCB; il confronto valido è tra modalità (single vs ledger) sulle stesse suite.

## D5 (2026-11-10, Fase 2) — Budget token: cap 8192 (heavy) / 4096 (mid), non il cap "breve" iniziale
- Prima baseline (esperiments/20261110T083700Z-*, SUPERSEDED.md) con heavy 4096 / mid 2048: molti campioni fallivano con token costanti == prompt+cap → truncation, non errori di capacità.
- Probe live (vv_reverse_02 su mid): testo 107 char ma completion 1436 token con thinking_ratio=0.0 → entrambi i modelli emettono comunque chain-of-thought; il knob non elimina il ragionamento.
- Decisione: cap 8192/4096 (comunque budget contenuti, ctx 144k/72k lo consente); `docs/sampling-params.md` aggiornata; il fallimento per truncation resta possibile ma solo su ragionamenti patologici.
- Il writer dei risultati è ora incrementale (un crash non perde i campioni completati) e `run_sample` cattura qualunque eccezione come riga d'errore: il loop di baseline non può morendo silenziosa come osservato in attempt 3.
- Follow-up misurato: su tabbyAPI il knob giusto è `chat_template_kwargs.enable_thinking=false` (probe: completion 1436→50 token). Baseline mid rieseguita senza reasoning; heavy resta CON reasoning (llama.cpp remoto non espone knob per-request) → parametri fissi PER MODELLO come da PLAN.
- Secondo fix live: `JUDGE_SAMPLING.max_tokens=800` tronca il giudice heavy prima della riga `scores` (misurato: reasoning ~626 tok) → `judge_sampling_for()`: heavy 4096, mid 2048 + `enable_thinking=false`; meta registra il sampling giudice per nodo.

## D7 (2026-11-10, UTENTE) — Hardware edge: Raspberry Pi 5 primario, telefono piano B
- Decisione UTENTE con PLAN v2.2: primario **Raspberry Pi 5 con raffreddamento attivo ed Ethernet** (8GB consigliato; 4GB ammesso se le misure lo confermano). Acquirente l'utente; non ancora disponibile.
- Il telefono in dotazione (piano B, requisiti in D1) si qualifica solo passando la qualificazione B.15 (velocità sostenuta 15 min, riconnessione, 24h uptime). È per ora l'unico hw edge fisico su cui eseguire i test di qualificazione (esito atteso: non qualificato, da verificare con misure reali).
- Il modello 0.4–0.6B **non è più un requisito** (v2.2/B.13): nucleo edge = encoder embedding 20–120M + reranker su top-K; `generative_ids: false` di default. Il ruolo edge va a un nodo fisico solo se batte a valle il baseline **BM25 + pinned** (B.14); altrimenti `on_not_qualified: baseline_only` (configurazione valida).
- Razionale tecnico (misure + doc): big core A75/A55 **senza dotprod/i8mm** → prefill 15–30 t/s e throttling sostenuto; A76 dell'RPi5 ha dotprod → classe minima utile per lo scoring B.13. Mini-PC x86 16GB scartato dall'utente: tradisce lo scopo "hw scarsissimo" del terzo nodo.
- Sorveglianza obbligatoria (B.15 + divieti v2.2): telefono mai incustodito sotto carico in carica continua; test di qualificazione telefono con limiti espliciti (stop a ≥45°C); verificare versione Android per il limite ai processi figli (Android 12+).
