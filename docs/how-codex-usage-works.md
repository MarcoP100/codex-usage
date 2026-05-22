# How `codex-usage` Works

Questo documento descrive cosa legge il programma, come interpreta i dati, quali metriche calcola e come gestisce duplicati o righe non valide.

## 1) Sorgente dati

La CLI legge tutti i file `*.jsonl` sotto:

- default: `~/.codex/sessions`
- opzionale: percorso passato con `--sessions-dir`

Ogni riga è trattata come un record JSON indipendente.

## 2) Quali eventi vengono considerati

Il parser tiene solo le righe dove:

- il JSON è valido
- esiste `payload` come oggetto
- `payload.type == "token_count"`

Tutto il resto viene ignorato ai fini dei token.

## 3) Dove prende i token

Per ogni evento `token_count`, i campi token vengono letti con questa priorità:

1. `payload.info.last_token_usage` (preferito: uso incrementale dell'evento)
2. `payload.info.total_token_usage` (fallback: cumulato)
3. direttamente in `payload` (compatibilità con formati più vecchi/diversi)

Campi letti:

- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_output_tokens`
- `total_tokens`

Il timestamp viene letto da:

1. `timestamp`
2. `created_at`
3. `payload.timestamp`

## 4) Classificazione righe non valide

Durante la scansione, ogni riga può finire in una categoria:

- `malformed_json`: la riga non è JSON parseabile
- `missing_payload_type`: manca `payload`, `payload` non è oggetto, manca timestamp valido, o struttura base non sufficiente
- `missing_token_fields`: è `token_count` ma i campi token richiesti non ci sono nel blocco scelto
- `not_token_event`: evento valido ma non di tipo `token_count` (non contato come errore)
- `valid`: evento usabile

Nel report qualità vengono mostrati i conteggi principali.

## 5) Deduplica eventi

Prima di aggiungere un evento valido alle statistiche, viene applicata deduplica con chiave:

- `(timestamp.isoformat(), total_tokens, input_tokens, output_tokens)`

Se la stessa chiave è già stata vista:

- evento scartato
- `Duplicate events skipped` incrementato

Perché questa scelta:

- semplice e veloce
- intercetta bene retry/append duplicati
- evita complessità non necessaria nel v0.1

Limite noto:

- due eventi realmente diversi ma con stessa quadrupla potrebbero collidere (raro, ma possibile).

## 6) Cosa calcola il report

## Data quality

- `Files scanned`: numero file `.jsonl` letti
- `Lines scanned`: numero righe totali processate
- `Valid token events`: eventi `token_count` validi dopo deduplica
- `Malformed JSON lines`: righe non parseabili
- `Missing payload/type`: righe con struttura base insufficiente
- `Missing token fields`: eventi `token_count` incompleti
- `Duplicate events skipped`: eventi validi scartati perché duplicati

## Token totals

- `Input tokens`
- `Cached input tokens`
- `Non-cached input = input - cached_input`
- `Output tokens`
- `Reasoning tokens`
- `Cache ratio = cached_input / input`
- `Effective new tokens estimate = (input - cached_input) + output + reasoning`

In più:

- `Usage tokens estimate (sum last_token_usage)`: somma `total_tokens` degli eventi validi (stima consumo)
- `Session final cumulative total (sum per-session total_token_usage)`: per ogni file/sessione prende l'ultimo cumulato e li somma

Nota importante:

- la metrica più utile per "quanto ho usato" è in genere `Usage tokens estimate`
- il cumulato finale per sessione è utile per confronto, ma misura qualcosa di diverso

## Breakdown by day

Per giorno (`YYYY-MM-DD`) somma i `total_tokens` degli eventi validi deduplicati.

## Breakdown by model

Prova a estrarre il modello da:

1. `payload.model`
2. root `model`
3. `payload.info.model`
4. root `model_slug`

Se non trova nulla usa `unknown`.

## Cache efficiency by day

Per ciascun giorno:

- `cached_input_tokens / input_tokens`

Mostra anche numeratore/denominatore raw.

## Event distribution

- `Average tokens/event`: media di `total_tokens` sugli eventi validi deduplicati
- `Median tokens/event`: mediana di `total_tokens`
- `Top 10 heaviest events`: eventi con `total_tokens` più alto, con timestamp/modello e dettaglio campi token

## 7) Export

## Event CSV (`--export-events-csv`)

Una riga per evento valido deduplicato:

- `timestamp,model,input_tokens,cached_input_tokens,output_tokens,reasoning_tokens,total_tokens`

## Daily CSV (`--export-daily-csv`)

Una riga per giorno:

- `date,events,input_tokens,non_cached_tokens,output_tokens,cache_ratio`

## Text report (`--save-report`)

Salva su file lo stesso report stampato a console.

## 8) Limiti e interpretazione

- Il tool legge solo i log presenti localmente nella cartella sessioni.
- Se una sessione non è salvata nei file, non può essere conteggiata.
- Token usati non equivalgono automaticamente al costo in valuta: per il costo servono modello, pricing e regole cache del periodo.


codex-usage summary \
  --save-report docs/summary.txt \
  --export-events-csv docs/events.csv \
  --export-daily-csv docs/daily_summary.csv \
  --export-model-costs-csv docs\model_costs.csv


codex-usage summary `
  --sessions-dir C:\Users\marco\.codex\sessions `
  --export-events-csv docs\events.csv `
  --export-daily-csv docs\daily_summary.csv `
  --export-model-costs-csv docs\model_costs.csv
