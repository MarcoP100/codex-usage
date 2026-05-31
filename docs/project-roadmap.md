# codex-usage: documento di progetto e roadmap

## 1. Visione

`codex-usage` nasce come strumento personale per capire come viene usato Codex nel tempo: quanti token vengono consumati, su quali progetti, con quali modelli, con quale effort e con quale stima di costo.

L'obiettivo non e' costruire subito un prodotto complesso, ma creare un osservatorio locale, affidabile e incrementale. Deve aiutare a rispondere a domande pratiche:

- quanto sto usando Codex?
- quali repository generano piu' consumo?
- quanto incide la cache?
- quali modelli o livelli di reasoning pesano di piu'?
- quali sessioni o giornate hanno avuto anomalie?
- posso confrontare periodi, macchine o account diversi?

Il progetto ha valore anche se resta personale: deve essere semplice da eseguire, trasparente nei calcoli e facile da estendere quando emergono nuove necessita'.

## 2. Principi guida

- **Locale prima di tutto**: i dati vengono letti dai file di sessione Codex e salvati localmente.
- **SQLite dopo l'import**: report avanzati, app e dashboard leggono da SQLite. I JSONL sono usati per import, backfill e ricostruzione.
- **Incrementale**: ogni fase deve lasciare il progetto in uno stato utilizzabile.
- **Verificabile**: ogni metrica importante deve essere tracciabile fino agli eventi grezzi.
- **Conservativo sui costi**: le stime sono utili per orientarsi, ma non devono essere presentate come costi reali di infrastruttura.
- **Portabile**: deve funzionare su Windows, con attenzione a non chiudere la porta a Linux/macOS.
- **Estensibile**: CLI, database, report e futura dashboard devono condividere lo stesso modello dati.

## 3. Stato attuale

Il progetto dispone gia' di una base funzionante:

- scansione dei file `*.jsonl` delle sessioni Codex;
- parsing degli eventi `token_count`;
- fallback tra `last_token_usage`, `total_token_usage` e campi diretti nel payload;
- arricchimento con metadati da `turn_context` (`model`, `reasoning_effort`, `cwd`);
- report testuale con totali, qualita' dati, breakdown per giorno, modello, effort e repository;
- export CSV per eventi, riepilogo giornaliero, costi per modello e repository;
- import SQLite idempotente con `raw_events` e `token_events`;
- test automatici su parser, scanner, config, report e import SQLite.

La documentazione operativa esistente e' in `docs/how-codex-usage-works.md`.

## 4. Perimetro funzionale

### In scope

- analisi storica delle sessioni Codex locali;
- stima token e costi API-equivalenti;
- aggregazioni per giorno, modello, effort, repository, dispositivo e account;
- archiviazione SQLite consultabile;
- esportazioni CSV;
- report periodici;
- futura dashboard locale;
- controlli di qualita' sui dati importati.

### Fuori scope, almeno per ora

- billing ufficiale OpenAI;
- sincronizzazione cloud;
- multiutente vero;
- scraping di dashboard esterne;
- automazioni invasive sulle directory Codex;
- modifica o riscrittura dei file di sessione originali.

## 5. Architettura desiderata

Il progetto puo' evolvere mantenendo quattro livelli separati.

### 5.1 Ingestion

Responsabile della lettura dei file di sessione:

- trova file `*.jsonl`;
- supporta `sessions` e `archived_sessions`;
- riconosce sorgente, dispositivo, account e path relativo;
- calcola hash stabili per evitare duplicati;
- mantiene gli eventi grezzi per audit.

### 5.2 Normalizzazione

Responsabile della trasformazione degli eventi Codex in record coerenti:

- normalizza timestamp;
- estrae token;
- associa modello, effort e repository;
- gestisce eventi incompleti o malformati;
- espone contatori di qualita' dati.

### 5.3 Storage e metriche

Responsabile della persistenza e delle query:

- SQLite come storage locale principale;
- tabelle raw e normalizzate;
- viste o query per aggregati frequenti;
- possibilita' di ricalcolare costi se cambia il pricing;
- storico import idempotente.

### 5.4 Backup e ricostruibilita'

Responsabile della continuita' dei dati:

- la cartella `.codex`, o una sua copia completa, e' la sorgente primaria da preservare;
- il DB SQLite in `data/` e' derivato e deve poter essere ricostruito dai JSONL;
- prima di migrazioni o cambiamenti di schema, deve essere possibile fare una copia rapida del DB;
- l'app non deve dipendere dai JSONL in runtime: dopo l'import tutto passa da SQLite.

### 5.5 Presentazione

Responsabile dell'uso quotidiano:

- CLI per report veloci;
- CSV per analisi esterna;
- documentazione copy/paste;
- in futuro dashboard locale con filtri e grafici.

## 6. Roadmap

La roadmap e' organizzata per fasi. Ogni fase produce qualcosa di usabile, senza obbligare a completare tutto il progetto in blocco.

### Fase 0 - Allineamento e pulizia documentale

Obiettivo: rendere chiaro cosa fa il progetto e come usarlo.

- [x] Documentare il funzionamento attuale.
- [x] Documentare visione, perimetro e roadmap.
- [x] Completare `README.md` con setup, comandi principali e link ai documenti.
- [x] Aggiungere un esempio di `config.toml` commentato.
- [x] Separare chiaramente "costo stimato" da "costo reale".

Criterio di uscita: una persona che apre il repository capisce in 5 minuti cosa fa il progetto e come lanciare un report.

### Fase 1 - Stabilizzare il core

Obiettivo: rendere affidabili parser, import e report sui dati reali.

- [x] Aggiungere test su file JSONL realistici con piu' turni nella stessa sessione.
- [x] Verificare deduplica tra report CLI e import SQLite, rendendo esplicite le regole.
- [x] Persistire `workspace_cwd` anche in `token_events`.
- [x] Salvare il nome repository normalizzato nel database.
- [x] Aggiungere contatori di qualita' dati anche all'import SQLite.
- [x] Gestire in modo esplicito modelli non riconosciuti nel pricing.
- [x] Aggiungere test sui timestamp numerici, ISO con timezone e valori mancanti.

Criterio di uscita: gli stessi dati producono risultati coerenti tra CLI, CSV e SQLite.

### Fase 2 - Migliorare il modello dati

Obiettivo: preparare il database per analisi piu' ricche.

- [x] Aggiungere tabella `import_runs` con data import, sorgente, numero file e contatori.
- [x] Aggiungere tabella o vista `repositories`.
- [x] Aggiungere viste SQLite per aggregati giornalieri, settimanali, mensili, per modello e per repository.
- [x] Separare costo input non-cache, costo cache e costo output nel DB.
- [x] Salvare `cumulative_total_tokens` dove disponibile.
- [x] Aggiungere `pricing_profiles` e `pricing_profile_rates` per versionare i prezzi usati.

Criterio di uscita: il DB diventa la fonte principale per report avanzati e dashboard.

### Fase 3 - Report utili per uso personale

Obiettivo: passare da metriche grezze a insight pratici.

- [x] Aggiungere comando `report` che legge da SQLite.
- [x] Aggiungere filtri CLI per periodo (`--from`, `--to`).
- [x] Aggiungere filtro per repository.
- [x] Aggiungere filtro per modello.
- [x] Aggiungere riepiloghi giornalieri, settimanali e mensili (`--group-by`).
- [x] Evidenziare top sessioni, giornate ed eventi piu' pesanti.
- [x] Aggiungere export Markdown oltre al report testuale.

Criterio di uscita: il report risponde alle domande piu' frequenti senza dover aprire CSV o SQLite.

### Fase 4 - Dashboard locale

Obiettivo: rendere l'analisi piu' esplorabile.

- [ ] Scegliere approccio leggero: Streamlit, FastAPI + frontend minimale, oppure notebook.
- [ ] Implementare la dashboard leggendo solo da SQLite.
- [ ] Mostrare KPI principali: token, costo stimato, cache ratio, eventi, repository principali.
- [ ] Aggiungere grafici per giorno/mese.
- [ ] Aggiungere breakdown per modello, effort e repository.
- [ ] Aggiungere filtri interattivi per periodo, repo, modello e dispositivo.
- [ ] Aggiungere vista "data quality".

Criterio di uscita: una dashboard locale consente di esplorare i dati senza rigenerare manualmente report.

### Fase 5 - Automazioni leggere

Obiettivo: ridurre il lavoro manuale senza complicare il progetto.

- [ ] Comando `refresh` che importa e produce report standard.
- [ ] Script PowerShell per aggiornamento locale.
- [ ] Possibile task schedulato giornaliero o settimanale.
- [x] Cartella output standard (`reports` per report, `data` per SQLite).
- [ ] Naming stabile dei report per data.

Criterio di uscita: aggiornare lo storico diventa un comando unico.

### Fase 6 - Qualita' e distribuzione

Obiettivo: rendere il progetto piu' solido nel tempo.

- [ ] Aggiungere linting e formatting.
- [ ] Aggiungere CI GitHub Actions.
- [ ] Aumentare copertura test sulle regressioni principali.
- [ ] Preparare installazione locale via `pipx` o `pip install -e .`.
- [ ] Valutare versionamento semantico.
- [ ] Aggiungere changelog.

Criterio di uscita: il progetto e' mantenibile senza dipendere dalla memoria di chi lo ha scritto.

## 7. Backlog prioritario

Questi sono i prossimi interventi consigliati, in ordine pratico:

1. Verificare manualmente report e Markdown su dati reali.
2. Preparare una dashboard locale minima leggendo solo da SQLite.
3. Aggiungere confronto tra due periodi.
4. Aggiungere comandi o checklist di backup/restore.
5. Valutare import incrementale da offset JSONL.

## 8. Rischi e attenzioni

- **Formato sessioni Codex instabile**: i JSONL potrebbero cambiare. Il parser deve restare tollerante e ben testato.
- **Costi stimati non ufficiali**: i prezzi configurati servono a confrontare ordini di grandezza, non a validare billing reale.
- **Deduplica delicata**: bisogna evitare sia doppi conteggi sia perdita di eventi legittimi simili.
- **Privacy**: i file raw possono contenere contenuti sensibili. Il progetto deve evitare export non necessari dei payload completi.
- **Repository detection fragile**: usare solo l'ultimo segmento di `cwd` e' utile, ma puo' creare collisioni tra progetti con lo stesso nome.
- **Backup incompleto**: perdere `.codex` o la copia delle sessioni impedisce di ricostruire lo storico. Il DB da solo non deve essere l'unico backup.

## 9. Decisioni aperte

- La dashboard deve essere un'app Python semplice o un frontend web separato?
- I prezzi devono stare in codice, config TOML o tabella SQLite?
- Ha senso distinguere workspace, repository e progetto personale come tre concetti separati?
- Vuoi mantenere il progetto strettamente personale o prepararlo per essere usabile anche da altri?

## 10. Definizione di successo

Una prima versione completa del progetto puo' considerarsi riuscita quando:

- importi le sessioni con un comando;
- ottieni un report affidabile per periodo;
- puoi vedere quali repository consumano di piu';
- puoi stimare l'effetto della cache;
- puoi consultare lo storico in SQLite;
- puoi spiegare da dove arriva ogni numero importante;
- puoi aggiungere nuove metriche senza riscrivere il core.
