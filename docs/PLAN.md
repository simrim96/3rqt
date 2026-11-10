# Three Racqwen in a Trenchcoat: piano d'azione per l'agente

Documento operativo da dare all'agente di sviluppo. Priorità assoluta: **qualità dei risultati**. Seconda priorità: velocità ed efficienza nella divisione dei task. Ogni ottimizzazione di velocità è ammessa solo se una misura dimostra che la qualità non cala.

## 0. Regole di lavoro per l'agente

1. Lavora per fasi. Non iniziare una fase finché i criteri di uscita della precedente non sono soddisfatti e documentati.
2. Nessun nome di modello, runtime o macchina hardcodato nel codice. Tutto passa dalla configurazione.
3. Prima di usare un flag, un'API o una versione di un runtime (llama.cpp, vLLM, Strata o altro), leggi la documentazione corrente. Non fidarti della memoria: questi strumenti cambiano in fretta.
4. Ogni affermazione del tipo "questa scelta migliora la qualità" deve essere supportata da un esperimento registrato in `experiments/`. Senza misura, la scelta resta provvisoria.
5. Scrivi test per ogni componente. Un componente senza test non è finito.
6. Se un requisito è ambiguo, fai una domanda sola e precisa all'utente invece di indovinare.
7. Registra tutto: ogni chiamata a un modello, ogni decisione di routing, ogni esito di verifica. Deve essere possibile rieseguire (replay) una sessione.

## 1. Obiettivo e principi di progetto

L'harness coordina **tre modelli sostituibili** su macchine diverse, assegnando loro ruoli in base alle capacità misurate e non ai nomi.

I tre slot logici, con i modelli di partenza dell'utente:

- **Slot A, "heavy"**: modello più capace e veloce, sul server. Partenza: Qwen3.8-Flash-Next, servito con Strata.
- **Slot B, "mid"**: modello denso medio, su un portatile con risorse limitate e condivise. Partenza: Qwen3.8-27B via llama.cpp.
- **Slot C, "edge"**: nodo di selezione e recupero: encoder piccolo per gli embedding (ordine di 20-120 milioni di parametri, da misurare) e, solo se le misure lo giustificano, un modello da 0.4-0.6B. Hardware consigliato: Raspberry Pi 5 con raffreddamento attivo ed Ethernet, oppure un mini-PC x86 con AVX2. Un telefono solo se supera la qualificazione della Specifica B (punto 15).

Principi:

- **I ruoli sono legati a capacità, non a modelli.** Cambiando i modelli o le macchine si modifica solo il file di configurazione.
- **Verifica deterministica prima, giudizio dei modelli dopo.** Dove esiste un oracolo (test, build, linter, schema), questo vince sempre sul parere di un modello.
- **Contesti freschi e memoria esplicita.** Il lavoro lungo si coordina tramite un *ledger* su filesystem (piano, note, stato, soluzione corrente), non tramite conversazioni lunghe. La fonte del guadagno è la scomposizione con contesto persistente, non la conversazione lunga.
- **Due percorsi di esecuzione.** *Fast path* (una chiamata, bassa latenza) e *deep mode* (orchestrazione con ledger, massima qualità). La deep mode è il default per i task difficili; il fast path non deve mai degradare la qualità sui task che lo richiedono.
- **Degradazione controllata.** Se un nodo cade o è occupato, i suoi ruoli passano a un altro nodo e il sistema continua.

Principi aggiunti dalla revisione v2:

- Nessuna ottimizzazione opzionale blocca il percorso critico. Se la versione ottimizzata non è pronta, il worker usa quella disponibile e prosegue.
- Le risorse libere producono tentativi extra (priorità P2), che entrano nel ledger solo se migliorano il punteggio sull'oracolo.
- Il modello piccolo **seleziona, non scrive**: ciò che arriva ai modelli grandi è testo originale, con la possibilità di espandere ogni omissione.

## 2. Architettura

Componenti:

1. **Node registry e adapter**: descrive ogni nodo (endpoint, modello, contesto, concorrenza, capacità) dietro un'unica interfaccia compatibile con le API OpenAI.
2. **Calibratore**: misura le prestazioni reali di ogni nodo (velocità, latenza, qualità su una mini-valutazione, supporto a tool calling e output strutturato).
3. **Assegnatore di ruoli**: associa i ruoli ai nodi in base ai risultati della calibrazione e ai vincoli dell'utente.
4. **Ledger**: stato condiviso su filesystem per ogni task.
5. **Orchestratore**: cicli planner, worker, verifier; scheduler con code per nodo.
6. **Esecutore sicuro (sandbox)**: esegue codice e test in isolamento.
7. **Router e escalation**: sceglie il percorso e promuove un task al livello superiore su segnali oggettivi.
8. **Gestore del contesto (tier edge)**: titoli, tag, retrieval/rerank, compressione estrattiva delle note.
9. **Harness di valutazione**: misura qualità, costo in token e tempo.
10. **Telemetria e replay**.

Stack suggerito (modificabile se l'agente motiva la scelta): Python 3.12, `uv`, `asyncio`, `httpx` o SDK OpenAI, `pydantic` per gli schemi, YAML per la configurazione, SQLite per telemetria e code, git worktree o container per la sandbox.

Struttura del repository:

```
threeracqwen/
  config/            # profili di esempio (nodes.yaml, roles.yaml)
  src/
    nodes/           # adapter, health check, calibrazione
    roles/           # planner, worker, verifier, reviewer, router, edge
    ledger/          # schema e operazioni sul ledger
    sandbox/         # esecuzione isolata
    scheduler/       # code, concorrenza, fallback
    evals/           # suite di valutazione e runner
    cli/
  experiments/       # un file per esperimento: ipotesi, setup, risultati, decisione
  tests/
  docs/
```

## 3. Fasi di lavoro

### Fase 0: preparazione e baseline di riferimento

Azioni:

- Crea il repository, il tooling e la CI minima.
- Analizza il metodo di riferimento esterno (doc privato, fuori repo) e documenta come funziona il ledger, come si scompone un problema e come si esegue il benchmark.
- Verifica che ogni nodo dell'utente risponda a una chiamata chat-completions e annota il runtime, la versione e i flag usati.

Criteri di uscita: repo funzionante; documento di riferimento scritto; tutti i nodi raggiungibili da un semplice script.

### Fase 1: nodi, configurazione e calibrazione

Azioni:

- Definisci lo schema di configurazione (vedi sezione 4) e validalo con `pydantic`.
- Implementa l'adapter unico: chat, streaming, annullamento, timeout, retry con backoff, conteggio token.
- Implementa il comando `harness doctor`, che controlla raggiungibilità, modello caricato, contesto massimo effettivo, supporto a tool calling, supporto a output strutturato (grammatica o JSON schema) e template di chat.
- Implementa il calibratore: misura tokens/s in generazione, tempo al primo token, comportamento sotto carico (1, 2, 4 richieste concorrenti), consumo di contesto, stabilità su generazioni lunghe. Esegue anche una mini-valutazione fissa (30-50 domande/task con risposta verificabile) e salva i punteggi.
- Salva i risultati in `calibration/<nodo>.json` con data e versione del runtime.

Criteri di uscita: `harness doctor` e `harness calibrate` funzionano su tutti i nodi reali e su nodi finti (mock) con latenza simulata; i test di configurazione coprono errori comuni (endpoint assente, contesto sbagliato).

**Aggiornamento v2.1 di questa fase: curva di velocità contro lunghezza del prompt e budget di contesto per nodo.**

Perché: il contesto massimo configurato e il contesto realmente usato sono cose diverse. Il massimo decide solo quanta memoria viene riservata per la KV cache; la lunghezza reale del prompt decide il tempo di prefill e quanta KV va letta a ogni passo di decodifica. Il riassunto estrattivo (Specifica B) riduce la seconda. Quanto convenga dipende da ogni nodo e va misurato, non assunto.

Azioni:

- `harness calibrate` esegue per ogni nodo uno **sweep di lunghezza del prompt** (almeno 4K, 16K, 32K, 64K e il massimo configurato; più punti attorno ai confini noti del nodo) e registra per ogni lunghezza: tempo al primo token, tokens/s in decodifica, uso di VRAM e RAM, a freddo e con prefisso riusato. I prompt devono essere diversi tra le ripetizioni (nessun riuso accidentale della cache) e la temperatura fissa.
- Dallo sweep ricava automaticamente per ogni nodo il **`target_prompt_tokens`**: la lunghezza oltre la quale la velocità cala in modo significativo (il "ginocchio" della curva), oppure il limite fisico se non c'è un ginocchio. Il valore è salvato in `calibration/<nodo>.json` e usato da scheduler e riassunto (Specifica A punto 6 bis, Specifica B punto 11).
- Se la curva è piatta, il nodo non beneficia del riassunto in velocità: registralo, e valuta se il riassunto abbia comunque senso per la qualità o per la finestra.

**Nota operativa sul nodo Flash-Next con Strata.** La configurazione attuale dell'utente è contesto massimo 131.072 token, KV in int8 e `kv_resident` 32.768 token in VRAM. L'interpretazione di lavoro è che i primi 32K token di KV stanno in VRAM e il resto viene gestito in streaming dalla RAM, quindi un confine di velocità è atteso intorno ai 32K. L'agente deve **verificare il significato esatto dei parametri nella documentazione corrente di Strata** (non dalla memoria), annotare cosa ha trovato e usare lo sweep per confermare se il ginocchio c'è davvero. Non assumere un valore di `target_prompt_tokens` prima di aver misurato.

**Criteri di uscita aggiuntivi.**

- Esiste una curva misurata (tempo al primo token e tokens/s contro lunghezza) per ogni nodo, salvata e riproducibile.
- `target_prompt_tokens` è calcolato per ogni nodo e visibile in `harness doctor`.
- Il significato dei parametri di memoria di Strata è documentato in `docs/` con la fonte letta.

**Aggiornamento v2.2 di questa fase: qualificazione dei nodi con risorse limitate (ruolo edge).**

Perché: un nodo piccolo (Raspberry, mini-PC, telefono) può sembrare adatto sulla carta e fallire nell'uso continuo per surriscaldamento, interruzioni di rete o chiusura dei processi da parte del sistema operativo. Le sigle dei core non bastano a prevedere le prestazioni: le funzioni CPU vanno lette dal dispositivo.

Azioni:

- `harness calibrate` rileva e registra le caratteristiche della CPU di ogni nodo. Su Linux e Android legge i flag di `/proc/cpuinfo` (ad esempio `asimddp` per il dot product e `i8mm` su ARM; AVX2 e simili su x86). Non dedurre le funzioni dal nome del core: sui core ARM A55 e A75 il dot product è opzionale e dipende dal chip.
- **Test di velocità sostenuta**: carico continuo per almeno 10-15 minuti, con registrazione dei tokens/s nel tempo per rilevare il throttling termico. Conta il valore minimo sostenuto, non il picco.
- **Misura del flusso di contenuto**: quanti token nuovi al minuto entrano nel ledger durante task di esempio (dalle Fasi 2 e 3). Il rapporto tra capacità sostenuta e flusso decide se un nodo può ricevere il ruolo edge.
- **Heartbeat e rilevamento della perdita di connessione**: un nodo che scompare viene dichiarato non disponibile, senza bloccare nulla.

**Criteri di uscita aggiuntivi.**

- I flag CPU di ogni nodo sono registrati e visibili in `harness doctor`.
- Esiste la curva di velocità sostenuta (almeno 10-15 minuti) per ogni nodo candidato al ruolo edge.
- Il rapporto capacità/flusso è calcolato e documentato.

### Fase 2: harness di valutazione e baseline single-call (prima di tutto il resto)

Questa fase viene prima dell'orchestrazione perché senza misura non si può dire se l'orchestrazione migliora qualcosa.

Azioni:

- Costruisci tre insiemi di task:
  1. **Verificabili**: un sottoinsieme di problemi di programmazione con test eseguibili (ad esempio da LiveCodeBench) più task di codice presi dai progetti reali dell'utente, ciascuno con test o criteri automatici.
  2. **Semi-verificabili**: task con output strutturato o controllabile (estrazione, trasformazioni, query).
  3. **Aperti**: scrittura, analisi, ricerca. Qui la valutazione usa una rubrica e un giudice di modello diverso dal generatore, e i risultati sono marcati come *a bassa confidenza*.
- Per ogni task registra: esito (pass/fail o punteggio), token consumati, tempo reale, numero di chiamate, escalation.
- Esegui la **baseline single-call** per ogni modello disponibile, con più campioni per stimare la varianza.
- Fissa i parametri di campionamento per modello (temperatura, top-p, budget di ragionamento) e documentali.

Criteri di uscita: tabella baseline per ogni modello su ogni insieme; varianza stimata; runner riproducibile con seed e versioni registrate.

### Fase 3: ledger e orchestrazione con un solo modello

Obiettivo: riprodurre il meccanismo di riferimento (ledger + orchestrazione) e verificare sul setup dell'utente se migliora la qualità.

Azioni:

- Definisci il ledger per task (sezione 4): piano, note, stato dei sotto-task, soluzione corrente, registro delle verifiche.
- Implementa il ciclo: il **planner** scompone e scrive il piano; ogni **worker** parte da un contesto fresco, legge ledger e file rilevanti, lavora su un solo sotto-task, scrive note e aggiorna la soluzione; il **verifier** esegue i test.
- Regole sul ledger: scritture atomiche, versionamento (git interno al workspace), nessun worker modifica il piano; solo il planner lo fa.
- Limiti: massimo numero di round, budget di token e di tempo per task, rilevamento di loop (stesso errore ripetuto N volte) con uscita controllata.
- Esegui l'esperimento: stesso modello, `single` contro `ledger`, sugli insiemi della Fase 2.

Criteri di uscita: risultato registrato con intervalli di confidenza. Se il ledger non migliora la qualità per un dato modello, documentalo e non attivarlo per quel modello nel profilo.

### Fase 4: esecuzione multi-nodo e scheduling

Azioni:

- Implementa la coda dei sotto-task con etichette del planner: difficoltà stimata, dimensione del contesto necessaria, tipo (codice, analisi, trasformazione).
- Implementa lo scheduler: ogni nodo ha una concorrenza massima e una disponibilità (`always` o `best_effort`). I worker prelevano i task compatibili con le proprie capacità.
- Gestisci i guasti: timeout, nodo irraggiungibile, nodo che si riempie di memoria. Il task torna in coda con un contatore di tentativi e può essere riassegnato a un nodo diverso. Le operazioni devono essere idempotenti.
- Il planner viene assegnato al nodo con il punteggio migliore su compiti di pianificazione e agenti nella calibrazione, non per nome.

Criteri di uscita: test con 1, 2 e 3 nodi (reali e mock); uccidendo un nodo a metà task il task termina comunque; log completi del percorso di ogni sotto-task.

**Aggiornamento v2:** lo scheduler di questa fase implementa la Specifica A (piano a DAG, priorità P0/P1/P2, assegnazione pull-based, monitor delle risorse del laptop). I criteri di uscita della specifica si sommano a quelli di questa fase.

### Fase 5: verifica e revisione incrociata

Azioni:

- **Livello 1, deterministico**: test, build, linter, validazione di schema. Un risultato rosso blocca l'accettazione.
- **Livello 2, revisione incrociata**: un modello *diverso* dall'autore rilegge il risultato con una checklist. Non basta la domanda "è corretto?": il revisore deve indicare problemi concreti o generare test aggiuntivi.
- **Livello 3, task senza oracolo**: giudice di modello diverso con rubrica fissa, più confronto fra due candidati prodotti da nodi diversi. Il risultato viene marcato a bassa confidenza e mostrato come tale all'utente.
- Esperimenti da eseguire e registrare:
  1. Autoverifica contro verifica incrociata.
  2. Planner = modello A contro planner = modello B.
  3. Worker misti contro worker dello stesso modello.
  4. Numero di round di correzione oltre il quale i guadagni si fermano.

Criteri di uscita: per ogni esperimento, tabella dei risultati e decisione scritta. Le impostazioni vincenti diventano i default nei profili.

### Fase 6: router, fast path, tier edge

Azioni:

- **Router a due stadi**: prima regole economiche (lunghezza, presenza di codice, strumenti richiesti, parole chiave), poi un classificatore piccolo solo per i casi ambigui. In dubbio, il router sceglie il livello superiore: un errore verso l'alto costa tempo, un errore verso il basso costa qualità.
- **Escalation su segnali oggettivi**: test falliti, JSON non valido dopo un tentativo di riparazione, loop, probabilità basse sui token, disaccordo fra esecutore e revisore. Non usare mai l'autovalutazione del modello come unico segnale.
- **Tier edge** (modello minuscolo): titoli, tag, rilevamento di lingua, embedding e reranking per il retrieval, compressione **estrattiva** delle note del ledger (selezione di frasi, non riscrittura). Regola ferrea: nulla di ciò che produce il tier edge entra nel ledger come fatto senza validazione; per il retrieval conta il recall, e se il contesto recuperato è insufficiente si promuove il task.
- Misura il router: percentuale di richieste instradate in basso che poi falliscono, e costo del router rispetto al tempo che fa risparmiare.

Criteri di uscita: il fast path non peggiora la qualità oltre la tolleranza concordata (default: nessuna differenza statisticamente significativa rispetto alla baseline sui task che instrada); tabella dei costi del router.

**Aggiornamento v2:** il tier edge implementa la Specifica B (riassunto estrattivo con unità e ID stabili, unità pinned, ricostruzione con marcatori di omissione, strumento `expand`). Sostituisce ogni riferimento precedente a una compressione generica delle note.

### Fase 7: portabilità

Azioni:

- Fornisci almeno quattro profili di esempio: tre nodi; due nodi (senza edge); un solo nodo; nodi con modelli diversi da quelli di partenza.
- Rendi i template di chat, i parametri di campionamento e le istruzioni di ruolo **per famiglia di modello**, in file separati, così cambiare modello significa aggiungere un file di profilo e non modificare codice.
- `harness doctor` e `harness calibrate` devono suggerire l'assegnazione dei ruoli e segnalare i problemi (ad esempio contesto troppo corto per il ruolo di planner).
- Documenta la procedura "aggiungere un nuovo modello" e "aggiungere una nuova macchina".

Criteri di uscita: un utente esterno configura un profilo nuovo seguendo solo la documentazione; test automatici con nodi finti di prestazioni diverse.

### Fase 8: ottimizzazione della velocità (solo ora)

Ogni modifica va confrontata con la baseline di qualità della Fase 2 e accettata solo se la qualità non cala.

Azioni, in ordine:

1. Caching del prefisso dei prompt per i contesti ripetuti (ledger, istruzioni di ruolo).
2. Parallelismo reale dei worker dentro i limiti di concorrenza misurati.
3. Decodifica speculativa **locale a ciascuna macchina** (draft model sullo stesso nodo del modello target; non attraverso la rete).
4. Limiti di ragionamento adattivi per ruolo (meno token di ragionamento per worker semplici, più per il planner).
5. Compressione estrattiva dei contesti lunghi quando il guadagno è misurato.

Criteri di uscita: tabella prima/dopo con qualità e tempo; nessuna regressione di qualità.

### Fase 9: robustezza e sicurezza

Azioni:

- Sandbox obbligatoria per l'esecuzione di codice: filesystem isolato, niente rete di default, limiti di CPU, memoria e tempo.
- Budget per sessione (token, tempo, numero di round) e interruttore di emergenza.
- Tutto il testo proveniente da file, pagine web o strumenti è dato, non istruzione: i modelli non devono eseguire comandi impartiti da contenuti esterni.
- Replay deterministico delle sessioni a partire dai log.

Criteri di uscita: test di sicurezza di base superati; una sessione completa riproducibile dai log.

### Specifica 0: DAG e RAG, due cose diverse nel progetto

- **DAG** (grafo aciclico orientato): la struttura del piano. Ogni nodo è un sotto-task e ogni arco significa "B richiede il risultato di A". Serve allo **scheduler** per sapere cosa può partire subito e cosa può girare in parallelo. Non recupera informazioni.
- **RAG** (generazione aumentata dal recupero): prima di far rispondere un modello si cercano in una base di documenti, codice o note i pezzi pertinenti (embedding + reranker) e si inseriscono nel prompt. Serve alla **qualità del contesto**. Non pianifica nulla.
- Nel progetto convivono: il planner produce un DAG; il tier edge fa il retrieval (la parte R del RAG) e il riassunto estrattivo; i modelli grandi fanno la generazione.
- Retrieval e riassunto estrattivo hanno la stessa meccanica (scegliere unità originali per pertinenza): riusa lo stesso componente di segmentazione e di punteggio.

### Specifica A: scheduling con priorità e DAG

**Principio.** Nessuna ottimizzazione opzionale (compressione, riassunto, revisione extra) deve mai bloccare il percorso critico. Nella versione precedente la compressione girava su un nodo condiviso e i worker aspettavano la fine del task in corso: questo è l'errore da non ripetere.

**1. Il piano è un DAG.** Il planner scrive `plan.dag.json`. Ogni nodo contiene `id`, `descrizione`, `deps` (id dei nodi da cui dipende), `tipo` (codice, analisi, trasformazione), `difficolta` stimata, `contesto_stimato` in token, `criteri_di_accettazione` (test o controlli) e `priorita`.

- Lo scheduler verifica che il grafo sia aciclico (ordinamento topologico). Se trova un ciclo, rifiuta il piano e chiede al planner di rifarlo.
- Un nodo è *pronto* quando tutte le sue dipendenze sono completate **e verificate**.
- Il planner deve scomporre per **rami indipendenti** quando il problema lo permette. Se il piano è una catena lineare nessuna macchina aggiuntiva lo accelera: in quel caso la capacità libera va ai task P2.
- Lo scheduler calcola il **cammino critico** (la catena di dipendenze più lunga, con durate stimate dalla calibrazione) e dà priorità ai nodi che ci stanno sopra.
- Se un nodo fallisce, si ripianifica solo il sotto-grafo invalidato, non l'intero piano.

**2. Tre priorità.**

- **P0**: percorso critico (planner, worker del nodo sul cammino critico, verifica deterministica).
- **P1**: lavoro normale pronto ma fuori dal cammino critico.
- **P2, opportunistico**: tentativi alternativi con strategie diverse, test e stress test aggiuntivi, revisione incrociata, riassunti anticipati, esplorazione di piani alternativi.
- I P2 sono **interrompibili**: quando arriva un P0 la richiesta in corso viene annullata via API e il lavoro scartato o ripreso. Un P1 fermo da troppo tempo viene promosso a P0 (*aging*), con soglia in configurazione.
- Un risultato P2 viene **adottato solo se migliora il punteggio sull'oracolo** (test, controlli). Altrimenti viene archiviato in `p2/` e non entra nel ledger principale.

**3. Assegnazione pull-based.** Ogni nodo preleva dalla coda un task compatibile con le sue capacità (contesto massimo, ruoli ammessi, concorrenza libera). Con più candidati lo scheduler stima il tempo totale (attesa in coda + prefill + generazione) e sceglie il minimo. A parità preferisce il nodo che ha già in cache il prefisso del contesto (**affinità di cache**): spostare contesti lunghi costa rete e prefill.

**4. Il laptop è un nodo condiviso con l'utente.** Un monitor legge RAM e VRAM libere e l'attività dell'utente. Sotto le soglie in configurazione: prima sospende i P2, poi riduce la concorrenza, poi si dichiara non disponibile e restituisce in coda i task in corso. Un nodo che va in esaurimento di memoria costa più di un nodo spento.

**5. Contesto senza attese.** La funzione che prepara il contesto di un worker restituisce *subito* la miglior versione disponibile: vista riassunta se pronta, altrimenti riduzione deterministica (Specifica B), altrimenti l'originale. Il tempo massimo di attesa per le ottimizzazioni opzionali è zero per i task P0.

**6. Concorrenza misurata, non supposta.** Con Strata (esperti MoE spostati tra VRAM e RAM) più richieste concorrenti potrebbero non aumentare il throughput totale. Prima di fissare `concurrency` di un nodo, misura i tokens/s aggregati con 1, 2 e 4 richieste concorrenti e usa il valore migliore.

**6 bis. Budget di contesto per nodo.** Lo scheduler assegna ai task P0 prompt che rientrano nel `target_prompt_tokens` del nodo (calcolato dallo sweep di calibrazione, Fase 1). Se il contesto necessario lo supera, ci sono due strade, in quest'ordine: passare per il riassunto estrattivo (Specifica B), oppure dirottare il task verso un nodo con budget maggiore. Il contesto massimo configurato resta come margine di emergenza e non è un obiettivo di utilizzo.

**7. Metriche obbligatorie**, per task e per nodo: tempo di blocco dei worker in attesa di altri nodi (deve tendere a zero); utilizzo per priorità (P0, P1, P2); percentuale di risultati P2 adottati; lunghezza del cammino critico rispetto al tempo reale; tempi di coda.

**Criteri di uscita.**

- In simulazione con nodi finti, se il nodo che riassume è 10 volte più lento il tempo totale dei task non peggiora oltre la tolleranza concordata rispetto a una run senza riassunto.
- Un P0 in arrivo interrompe un P2 entro un tempo massimo misurato e documentato.
- Un piano con ciclo viene rifiutato, un piano lineare viene gestito correttamente, la caduta di un nodo a metà task viene recuperata.

### Specifica B: riassunto estrattivo in tempo reale con il modello piccolo

**Principio.** Il riassunto è **estrattivo**: il modello piccolo *sceglie* frasi o blocchi originali, non scrive parole nuove. Così non può inventare contenuto, perché ogni riga che arriva al modello grande è testo originale. Restano possibili due altri errori: scartare una frase decisiva e togliere una frase dal suo contesto. La specifica è costruita per ridurre proprio questi due rischi.

**1. Segmentazione deterministica in unità con ID stabili.** Ogni contenuto che entra nel ledger viene spezzato senza modelli: frasi per la prosa, funzioni o hunk per il codice, righe significative e blocchi per i log, righe per le tabelle. Ogni unità ha un `ref` (ad esempio `notes#12:4`), l'hash del contenuto e la posizione originale. Le unità sono salvate in `units/`.

**2. Unità sempre da tenere (*pinned*), decise da regole e non dal modello.** Sono quelle che contengono numeri e unità di misura, identificatori, percorsi di file, comandi, messaggi di errore, negazioni e condizioni ("non", "solo se", "tranne", "a meno che"), vincoli e requisiti, definizioni, citazioni. Le unità pinned non vengono mai scartate.

**3. Punteggio delle altre unità**, in ordine di preferenza:

1. encoder piccolo per gli embedding e reranker solo sulle prime K unità (versione aggiornata al punto 13), con query = descrizione del sotto-task corrente;
2. modello generativo piccolo **vincolato da grammatica** a restituire solo una lista di ID da tenere, mai testo libero;
3. fallback deterministico (BM25 o TextRank) se il nodo edge è lento o assente.

**4. Contesto locale.** Per evitare frasi decontestualizzate: se un'unità selezionata inizia con un riferimento ("questo", "esso", "come sopra", "quindi"), o contiene una negazione o condizione che dipende dalla frase vicina, si include anche l'unità precedente. Come opzione generale da misurare: finestra di ±1 unità attorno a ogni unità selezionata.

**5. Ricostruzione.** Le unità selezionate sono concatenate **nell'ordine originale**. Ogni taglio è segnalato con un marcatore, ad esempio `[… 3 frasi omesse: notes#12:5-7 …]`, così il modello sa che c'è stata un'omissione e dove.

**6. Espansione su richiesta.** Il modello grande dispone dello strumento `expand(ref)`, che restituisce l'originale. C'è un limite di chiamate per task, in configurazione, per evitare cicli. Un tasso alto di `expand` segnala che il recall del riassunto è basso.

**7. Tempo reale = lavoro anticipato e incrementale.**

- Segmentazione e punteggio generico partono quando l'unità entra nel ledger, in background, a priorità P2 sul nodo edge.
- Al cambio di sotto-task si rifà solo il re-ranking con la nuova query (veloce, solo embedding).
- Le viste sono in cache con chiave `hash del contenuto + query`.
- Se il job del nodo edge non finisce entro il timeout, il worker usa la riduzione deterministica o l'originale. Il riassunto non blocca mai (Specifica A, punto 5).

**8. Quando non riassumere.** Contesto già sotto la soglia di attivazione; testo del task; codice in modifica; messaggi di errore esatti; tabelle di numeri; vincoli e requisiti. La soglia di attivazione (frazione della finestra del nodo destinatario) si calibra con gli esperimenti.

**9. Riassunto astrattivo (riscrittura).** Disattivato di default. Se attivato, solo per la storia vecchia, eseguito da un modello grande in P2 e mai dal modello piccolo, con controllo automatico: ogni numero, percorso e identificatore del riassunto deve comparire nell'originale.

**10. Nodo edge lento.** Prima di assegnare questo ruolo a un Raspberry o a un telefono, misura i tokens/s in prefill del dispositivo ed elabora a lotti piccoli. Se il costo del job supera il tempo risparmiato al nodo destinatario, usa il fallback deterministico.

**11. Budget di contesto per nodo.** Il riassunto si attiva rispetto al `target_prompt_tokens` del nodo destinatario, non rispetto alla finestra massima. Esempio: per Flash-Next con Strata il confine atteso è intorno ai 32K token (vedi nota in Fase 1, da confermare con lo sweep). Il riassunto è utile su un nodo solo se almeno una di queste condizioni è dimostrata dalle misure: (a) la curva di velocità mostra un calo oltre il budget; (b) la qualità non cala al rapporto scelto; (c) il prompt altrimenti non entrerebbe nella finestra del nodo. Altrimenti, su quel nodo, il riassunto resta spento.

**12. Prefisso stabile.** Un riassunto rigenerato a ogni passo cambia il prompt e può invalidare il riuso della cache del prefisso, annullando il guadagno di prefill. Regole: in testa metti ciò che non cambia (istruzioni di ruolo, testo del task, piano); il materiale riassunto va in coda; durante un sotto-task il riassunto si **aggiorna solo in aggiunta** (nuove unità alla fine) e si rigenera da zero solo al cambio di sotto-task. L'agente deve verificare se e come Strata riusa il prefisso o la sessione tra una richiesta e l'altra (la documentazione e i benchmark parlano di sessioni residenti) e misurare l'effetto sul prefill.

**13. Design dello scorer (aggiornamento v2.2, prevale sul punto 3 dove differisce).** In ordine di costo crescente:

1. **BM25 + unità pinned**: baseline sempre disponibile, senza modelli.
2. **Encoder piccolo per gli embedding** (ordine di 20-120 milioni di parametri, da misurare): ogni unità viene embeddata **una sola volta**, quando entra nel ledger (il ledger è in sola aggiunta). Per un nuovo sotto-task si embedda solo la nuova query e la si confronta con gli embedding in cache.
3. **Reranker solo sulle prime K unità** (K in configurazione). Il reranker valuta una coppia query-unità per volta e costa molto più di un confronto tra embedding.
4. **Selezione di ID con un modello generativo vincolato da grammatica**: opzionale e spenta di default. Va attivata solo se un esperimento mostra un vantaggio di qualità che giustifichi il costo del prefill.

Un modello da 0.4-0.6B non è un requisito: è una delle opzioni da misurare.

**14. Il baseline è obbligatorio.** Prima di dedicare hardware al ruolo edge, misura la qualità a valle con BM25 + unità pinned. Se i modelli non migliorano il risultato in modo significativo, il riassunto usa solo il baseline e il nodo fisico non serve a questo scopo (può restare per titoli, tag e retrieval).

**15. Qualificazione del nodo edge.** Un dispositivo riceve il ruolo solo se:

- la velocità sostenuta (Fase 1, 10-15 minuti) supera di un fattore configurabile il flusso di contenuto prodotto dall'harness;
- heartbeat e riconnessione funzionano in un test di spegnimento e riattacco;
- il processo resta attivo senza interventi manuali per almeno 24 ore.

Hardware consigliato, dal più semplice: Raspberry Pi 5 con raffreddamento attivo ed Ethernet; mini-PC x86 con AVX2; telefono solo se supera i test. Un telefono con batteria, sotto carico e in carica continua, va tenuto sotto sorveglianza (rischio di rigonfiamento della batteria). Dalla versione 12 di Android esiste inoltre un limite ai processi figli, da verificare per la versione in uso. Se il nodo non si qualifica, il ruolo passa al baseline deterministico: è una configurazione valida, non un guasto.

**Metriche e test.**

- **Fedeltà**: ogni unità nell'output esiste nell'originale con hash identico (deve essere 100%).
- **Copertura pinned**: 100% delle unità pinned conservate.
- **Test *needle***: un fatto decisivo inserito in un contesto lungo deve sopravvivere al riassunto; ripeti con fatti in posizioni e forme diverse.
- **Qualità a valle**: pass rate e punteggio sul set di valutazione con contesto completo, riassunto e riduzione deterministica, a più rapporti; individua il rapporto oltre cui la qualità cala.
- **Tasso di `expand`** e **tempo risparmiato** sul nodo destinatario.

**Criteri di uscita.** Fedeltà e copertura pinned al 100% nei test; nessuna regressione di qualità oltre la tolleranza ai rapporti di default; il job del nodo edge non compare mai sul cammino critico.

## 4. Interfacce di riferimento

### Configurazione dei nodi

```yaml
nodes:
  heavy:
    endpoint: http://server:8080/v1
    model: <nome-modello>
    family: qwen          # seleziona template e parametri di campionamento
    ctx: 131072
    concurrency: 2
    availability: always
    roles_allowed: [planner, worker, verifier, reviewer]
  mid:
    endpoint: http://laptop:8080/v1
    model: <nome-modello>
    family: qwen
    ctx: 32768
    concurrency: 1
    availability: best_effort
    roles_allowed: [worker, reviewer]
  edge:
    endpoint: http://piccolo:8080/v1
    model: <nome-modello>
    family: qwen
    roles_allowed: [router, titler, embedder, compressor]
policy:
  quality_first: true
  max_rounds: 8
  fallback_role_to: heavy
  reassign_roles_on_calibration: true
```

Estensione v2 della configurazione (scheduler e riassunto). I valori numerici sono segnaposto da calibrare con gli esperimenti.

```yaml
scheduler:
  priorities: [P0, P1, P2]
  p2_preemptible: true
  p1_aging_seconds: 120        # promozione P1 -> P0 se fermo troppo a lungo
  cache_affinity: true
nodes:
  mid:
    resource_guard:
      min_free_ram_gb: 3
      min_free_vram_gb: 1
      pause_p2_when_user_active: true
summarizer:
  mode: extractive             # extractive | off
  node_role: edge
  scorers: [reranker, grammar_ids, bm25_fallback]
  pin_rules: [numbers, identifiers, paths, commands, errors, negations, conditions, constraints, definitions]
  neighbor_window: 1           # da misurare: 0 o 1
  trigger_ratio: 0.5           # frazione della finestra del nodo destinatario
  max_wait_ms: 0               # mai bloccare il percorso critico
  omission_markers: true
  expand_tool: true
  expand_max_calls_per_task: 10
  timeout_fallback: deterministic
  abstractive:
    enabled: false
```

Estensione v2.1 della configurazione: budget di contesto e parametri di memoria del nodo. Il valore di `target_prompt_tokens` è calcolato dalla calibrazione, quello indicato è solo un esempio. I parametri `engine_args` sono quelli dichiarati dall'utente per Flash-Next con Strata; l'agente deve verificarne il significato nella documentazione corrente.

```yaml
nodes:
  heavy:
    engine: strata
    engine_args:
      max_context: 131072
      kv: int8
      kv_resident: 32768       # da verificare nella documentazione di Strata
    calibration:
      prompt_sweep: [4096, 16384, 32768, 65536, 131072]
      target_prompt_tokens: auto   # ricavato dal ginocchio della curva
    context_policy:
      summarize_above_target: true  # solo se le misure lo giustificano
      stable_prefix: true
```

Estensione v2.2 della configurazione: qualificazione e scorer del nodo edge. I valori sono segnaposto da calibrare.

```yaml
nodes:
  edge:
    qualification:
      sustained_test_minutes: 15
      min_capacity_ratio: 2.0       # capacità sostenuta / flusso di contenuto prodotto
      heartbeat_seconds: 10
      uptime_check_hours: 24
    scorer:
      baseline: bm25_pinned         # sempre attivo come riferimento
      encoder: small                # ordine di 20-120M parametri, da misurare
      reranker_top_k: 20
      generative_ids: false         # opzionale, solo se un esperimento lo giustifica
    on_not_qualified: baseline_only # configurazione valida, non un guasto
```

### Ledger di un task

```
workspaces/<task_id>/
  task.md             # richiesta originale, immutabile
  plan.md             # piano; modificabile solo dal planner
  notes.md            # note dei worker, in append
  state.json          # sotto-task, stato, assegnatario, tentativi
  solution/           # soluzione corrente (repo git)
  verification.jsonl  # esiti di ogni verifica con livello e causa
  trace/              # log di ogni chiamata a modello
```

Aggiunte v2 al ledger:

```
workspaces/<task_id>/
  plan.dag.json         # DAG: nodi, deps, priorità, criteri di accettazione
  units/                # unità originali con id stabili e hash (*.jsonl)
  views/                # viste riassunte, cache per hash + query
  p2/                   # risultati opportunistici: adottati o scartati
  scheduler.log.jsonl   # decisioni, code, interruzioni, tempi di blocco
```

### Comandi CLI minimi

```
harness doctor
harness calibrate [--node NOME]
harness run "<task>" [--mode fast|deep|auto] [--profile FILE]
harness eval --suite <nome> --mode <single|ledger|mixed>
harness replay <session_id>
```

## 5. Matrice di esperimenti

Da eseguire a partire dalla Fase 3 e registrare in `experiments/`:

- single contro ledger, per ogni modello;
- modello A solo, modello B solo, A+B misti;
- autoverifica contro verifica incrociata;
- planner A contro planner B;
- numero di worker (1, 2, 4) contro qualità e tempo;
- profondità di ragionamento contro qualità e tempo;
- con e senza compressione estrattiva delle note.

Esperimenti aggiuntivi v2:

- Riassunto estrattivo contro contesto completo contro riduzione deterministica, a più rapporti e per tipo di contenuto.
- Scorer a confronto: reranker, ID con grammatica, BM25 e loro combinazioni; finestra di ±1 unità contro nessuna finestra.
- Test *needle* e tasso di `expand`.
- Riassunto sincrono contro anticipato e asincrono: tempo di blocco e qualità.
- Effetto dei task P2 su qualità, tempo totale e tasso di adozione, con e senza interruzione.
- Concorrenza del nodo Flash-Next con Strata: 1, 2 e 4 richieste.
- Piano a DAG con rami indipendenti contro piano lineare: guadagno di tempo reale.

Esperimenti aggiuntivi v2.1:

- Curva di velocità contro lunghezza del prompt per ogni nodo (tempo al primo token e tokens/s), a freddo e con prefisso riusato; verifica se c'è un salto oltre `kv_resident` su Flash-Next.
- Flash-Next con `kv_resident` 32K contro valori più bassi (ad esempio 16K) con prompt brevi: la VRAM liberata alla cache degli esperti accelera la decodifica? Ipotesi da confermare.
- Contesto completo contro riassunto estrattivo **su Flash-Next** e **sul 27B** separatamente: velocità e qualità. Si prevede che il beneficio sia maggiore sul 27B, ma va misurato.
- Prefisso stabile contro riassunto rigenerato a ogni passo: effetto sul prefill.
- Contesto massimo ridotto (ad esempio da 131072 a un valore più basso) a parità di prompt: cambia qualcosa oltre alla memoria liberata?

Esperimenti aggiuntivi v2.2:

- Qualità a valle con BM25 + unità pinned contro encoder piccolo contro encoder + reranker sulle prime K contro selezione di ID con modello generativo. Se il baseline non è battuto in modo significativo, il ruolo edge resta sul baseline.
- Flusso reale di token nuovi al minuto nel ledger durante task di esempio, contro la capacità sostenuta di ogni dispositivo candidato.
- Velocità sostenuta per 15 minuti su ogni hardware candidato (Raspberry Pi 5 con raffreddamento attivo, mini-PC x86, eventuale telefono): picco contro valore minimo.
- Flag CPU di ogni nodo (`asimddp`, `i8mm`, AVX2) e loro effetto sulla velocità di prefill, misurato e non dedotto dal nome del core.
- Costo in tempo e in qualità del reranker al variare di K.

Regola di decisione: adotta una variante solo se migliora la qualità in modo non spiegabile dalla varianza; a parità di qualità sceglie la più veloce e meno costosa in token.

## 6. Cose da non fare

- Non ottimizzare la velocità prima di avere la baseline della Fase 2.
- Non fidarsi dell'autovalutazione di un modello come unico criterio.
- Non far scrivere al modello piccolo informazioni che entrano nel ledger senza una verifica.
- Non assumere che i guadagni del metodo di riferimento si trasferiscano: sono misurati su problemi di programmazione competitiva con test; per altri tipi di task vanno verificati.
- Non assumere che la mescolanza di modelli diversi migliori la qualità: è un'ipotesi da misurare.
- Non legare il codice a un runtime, a una versione o a un nome di modello.

Divieti aggiunti dalla revisione v2:

- Non far attendere il percorso critico per un'ottimizzazione opzionale.
- Non lasciar produrre al modello piccolo testo nuovo che entra nel ledger come fatto: può soltanto selezionare.
- Non considerare il riassunto estrattivo privo di errori: può omettere una frase decisiva o toglierla dal suo contesto.
- Non avviare task P2 che non si possano interrompere.
- Non assumere che più richieste concorrenti su Flash-Next con Strata aumentino il throughput: va misurato.

Divieti aggiunti dalla revisione v2.1:

- Non ridurre il contesto di un nodo, né attivarvi il riassunto, senza aver misurato la curva di velocità e la qualità su quel nodo.
- Non pensare che abbassare il contesto massimo configurato acceleri il modello: libera memoria, non velocità, a parità di prompt.
- Non rigenerare da zero il riassunto a ogni passo: rompe il prefisso stabile.
- Non ricavare `target_prompt_tokens` da numeri letti in articoli o benchmark altrui: vale solo quello misurato sul proprio hardware.

Divieti aggiunti dalla revisione v2.2:

- Non assegnare il ruolo edge a un dispositivo senza qualificazione sostenuta di almeno 10-15 minuti e test di riconnessione.
- Non dedurre le funzioni della CPU dal nome del core: leggerle dal dispositivo.
- Non dare per scontato che serva un modello da 0.4-0.6B per il ruolo edge: prima va battuto il baseline BM25 + pinned.
- Non rielaborare ogni volta l'intero contesto sul nodo edge: ogni unità si embedda una sola volta.
- Non lasciare incustodito un telefono con batteria sotto carico e in carica continua.

## 7. Definizione di "finito"

1. Il sistema funziona con almeno tre configurazioni diverse di nodi senza modifiche al codice.
2. Esiste una tabella di valutazione riproducibile che confronta single-call, ledger e configurazioni miste.
3. Ogni default del profilo è giustificato da un esperimento registrato.
4. La caduta di un nodo non interrompe un task in corso.
5. La documentazione permette di aggiungere un modello o una macchina senza toccare il codice.

Criteri aggiuntivi v2:

- Con un nodo edge 10 volte più lento in simulazione, il tempo dei task non peggiora oltre la tolleranza concordata.
- Il riassunto estrattivo ha fedeltà e copertura pinned al 100% nei test e nessuna regressione di qualità ai rapporti di default.
- Un task P0 interrompe un P2 entro il tempo massimo documentato.
- Ogni risultato P2 adottato è tracciato con il miglioramento di punteggio che lo ha giustificato.

Criteri aggiuntivi v2.1:

- `harness calibrate` produce, per ogni nodo, una curva di velocità contro lunghezza del prompt e un `target_prompt_tokens`.
- Il riassunto è attivo su un nodo solo se curva e A/B di qualità ne dimostrano il vantaggio; altrimenti è spento e la decisione è documentata.

Criteri aggiuntivi v2.2:

- Il ruolo edge è assegnato solo a un nodo che ha superato la qualificazione (velocità sostenuta, riconnessione, 24 ore di attività continua).
- Il confronto con il baseline BM25 + pinned è documentato in `experiments/`; se il baseline non è battuto, la configurazione di default lo usa.
- La perdita del nodo edge non produce attese né errori: i worker proseguono con il baseline.

## 8. Primo prompt da dare all'agente

> Leggi interamente il documento "Three Racqwen in a Trenchcoat: piano d'azione". Esegui la Fase 0 e la Fase 1 seguendo le regole di lavoro della sezione 0. Prima di scrivere codice, restituiscimi un riepilogo di cosa hai capito, le assunzioni che stai facendo e l'unica domanda più importante per cui ti serve una risposta. Poi procedi e fermati alla fine della Fase 1 con il rapporto dei criteri di uscita.

> Aggiunta v2.1 al prompt: prima di iniziare leggi anche la Specifica 0, la Specifica A e la Specifica B. La Fase 1 include ora lo sweep di lunghezza del prompt per ogni nodo e il calcolo di `target_prompt_tokens`; consegnali insieme agli altri criteri di uscita della Fase 1.
