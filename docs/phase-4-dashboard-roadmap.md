# Fase 4: roadmap dashboard server

## Obiettivo

Portare `codex-usage` da report CLI a dashboard web locale/server, mantenendo il progetto semplice, ricostruibile e centrato su SQLite.

La dashboard deve aiutare a esplorare lo storico senza aprire DBeaver, CSV o file JSONL.

## Decisione tecnica

Approccio scelto:

- **FastAPI** come server Python;
- **Jinja** per generare pagine HTML lato server;
- **SQLite** come database operativo;
- **Docker Compose** per avviare web app e volumi in modo ripetibile.

Jinja e' un motore di template: permette di scrivere file HTML con placeholder e cicli, per esempio una tabella di repository generata dai dati Python. In pratica evita un frontend JavaScript complesso nella prima versione.

## Principi

- La UI legge solo da SQLite.
- I JSONL non sono letti dalla UI.
- SQLite vive in un volume o path persistente.
- I backup veri restano le sessioni `.codex` o la loro copia.
- La dashboard deve essere utile anche se resta minimale.
- La prima versione deve evitare login, multiutente, upload e automazioni live.

## Architettura target iniziale

```text
Browser
  -> FastAPI container
      -> Jinja templates
      -> SQLite read-only o read-mostly in /data/codex_usage.db

Import CLI/manuale
  -> legge copia sessioni JSONL
  -> aggiorna /data/codex_usage.db
```

Per ora il container web non deve modificare i JSONL. L'import resta un comando separato.

## Step 1 - Skeleton web

Obiettivo: avere una web app minima avviabile.

Attivita':

- aggiungere dipendenze web (`fastapi`, `uvicorn`, `jinja2`);
- creare modulo `codex_usage.web`;
- creare endpoint `/`;
- creare template HTML base;
- leggere path DB da variabile ambiente o config;
- mostrare stato app e path DB.

Criterio di uscita:

- `uvicorn` avvia la web app;
- la pagina `/` risponde;
- nessun accesso ai JSONL.

## Step 2 - Lettura dashboard da SQLite

Obiettivo: mostrare i KPI principali usando il layer dati gia' esistente.

Attivita':

- riusare `sqlite_report.py` o estrarre query condivise se necessario;
- mostrare:
  - periodo coperto;
  - eventi token;
  - token totali;
  - cache ratio;
  - costo stimato;
  - top repository;
  - top modelli;
  - top giornate/sessioni/eventi;
- gestire DB mancante o vuoto con messaggio chiaro.

Criterio di uscita:

- la homepage mostra dati coerenti con `codex-usage report`;
- test su almeno un DB temporaneo.

## Step 3 - Filtri interattivi

Obiettivo: usare la dashboard per esplorare periodi e sottoinsiemi.

Attivita':

- form GET con filtri:
  - `from`;
  - `to`;
  - `repository`;
  - `model`;
- validazione date;
- preservare i filtri nei link e nel form;
- usare gli stessi filtri del report SQLite.

Criterio di uscita:

- i filtri web producono gli stessi numeri del comando CLI equivalente.

## Step 4 - Grafici leggeri

Obiettivo: rendere visibili trend e distribuzioni senza introdurre un frontend pesante.

Attivita':

- aggiungere grafico giornaliero o mensile;
- aggiungere grafico per repository o modello;
- preferire HTML/CSS semplice o una libreria leggera caricata localmente/selezionata esplicitamente;
- mantenere sempre tabelle leggibili come fallback.

Criterio di uscita:

- i trend principali sono leggibili a colpo d'occhio;
- la dashboard resta usabile anche senza interazioni complesse.

## Step 5 - Vista data quality

Obiettivo: esporre i segnali di qualita' import senza aprire SQLite.

Attivita':

- mostrare ultimi import;
- mostrare righe scansionate, raw inseriti, duplicati, token inseriti;
- mostrare malformed JSON, missing payload/type, missing token fields;
- mostrare eventi con pricing default.

Criterio di uscita:

- si capisce se l'ultimo import e' sano.

## Step 6 - Docker

Obiettivo: rendere l'avvio ripetibile e preparare l'esecuzione server.

Attivita':

- aggiungere `Dockerfile`;
- aggiungere `docker-compose.yml`;
- montare `data/` come volume persistente;
- esporre la web app su `localhost:8000`;
- documentare comando di avvio;
- tenere il DB fuori dall'immagine.

Esempio target:

```bash
docker compose up web
```

Criterio di uscita:

- la dashboard parte via Docker Compose;
- il DB resta persistente tra restart;
- la UI non richiede accesso ai JSONL.

## Step 7 - Import server-side, ma separato

Obiettivo: preparare il futuro senza anticipare troppo.

Attivita':

- valutare servizio o comando Docker separato per `import-sqlite`;
- montare la copia sessioni in sola lettura;
- montare `data/` in scrittura;
- non implementare ancora watcher live.

Criterio di uscita:

- si puo' aggiornare il DB da container con un comando manuale.

## Non obiettivi della Fase 4

- Postgres.
- Login e utenti.
- Upload di sessioni dalla UI.
- Watcher live dei JSONL.
- Import automatico continuo.
- Deploy pubblico su internet.

## Backup

La dashboard non cambia la gerarchia dei backup:

1. salvare `.codex` o copia completa delle sessioni;
2. salvare `data/codex_usage.db` per ripartenze rapide;
3. considerare SQLite ricostruibile dai JSONL.

Prima di test Docker o migrazioni:

```bash
cp data/codex_usage.db "data/codex_usage.backup-$(date +%Y%m%d-%H%M%S).db"
```

## Criterio di uscita della Fase 4

La fase e' chiusa quando:

- la dashboard parte localmente e via Docker;
- legge solo da SQLite;
- mostra KPI, trend, breakdown e data quality;
- i filtri principali funzionano;
- i numeri sono coerenti con il report CLI;
- la documentazione spiega avvio, backup e ricostruzione.
