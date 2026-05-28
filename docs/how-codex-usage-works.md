# How `codex-usage` Works

Questa guida descrive il funzionamento attuale del tool e include comandi pronti da copiare.

## 1) Sorgente dati

Il tool legge file `*.jsonl` dalle sessioni Codex.

- Directory base: `sessions_dir` (da `config.toml` o `--sessions-dir`)
- Opzionale: include anche `archived_sessions` (da `config.toml` o `--include-archived-sessions`)

Se usi `config.toml`, non serve passare i path ogni volta.

Convenzione consigliata nel repository:

- `docs/`: solo documentazione;
- `data/`: database SQLite locale;
- `reports/`: report testuali e CSV generati.

Per lavorare in sicurezza puoi impostare `sessions_dir` verso una copia locale delle sessioni, ad esempio `C:/Users/marco/.codex - Copia/sessions`.

## 2) Eventi considerati per i token

Per le metriche token vengono usati solo gli eventi `payload.type == "token_count"`.

Per ogni evento token:

1. `payload.info.last_token_usage` (prioritario)
2. `payload.info.total_token_usage` (fallback)
3. campi token direttamente in `payload` (fallback)

Campi principali:

- `input_tokens`
- `cached_input_tokens`
- `output_tokens`
- `reasoning_output_tokens`
- `total_tokens`

Timestamp (ordine):

1. `timestamp`
2. `created_at`
3. `payload.timestamp`

## 3) Metadati aggiuntivi

Il tool arricchisce gli eventi token con metadati trovati nei `turn_context` dello stesso file:

- `model`
- `reasoning_effort`
- `cwd` (usato per report per repository)

## 4) Costi stimati

I costi mostrati dal tool sono stime API-equivalenti. Non sono il billing ufficiale OpenAI e non rappresentano il costo reale dell'infrastruttura. Servono solo per confrontare ordini di grandezza, trend e distribuzione dell'uso.

I costi sono calcolati per modello:

- `gpt-5.5`: input `5.00`, cached `0.50`, output `30.00`
- `gpt-5.4`: input `2.50`, cached `0.25`, output `15.00`
- `gpt-5.4-mini`: input `0.75`, cached `0.075`, output `4.50`
- `gpt-5.3-codex`: input `1.75`, cached `0.175`, output `14.00`

Unità: USD per 1M token.

Se un modello non e' presente nella tabella, il tool usa il pricing predefinito configurato nel codice.

Il fallback non e' silenzioso:

- nel report viene mostrata la sezione `Models using default pricing`;
- nell'import SQLite viene valorizzato `pricing_used_default`;
- il comando `import-sqlite` stampa il totale degli eventi token che hanno usato il pricing predefinito.

## 5) Output disponibili

### Report console / file

Sezioni principali:

- Data quality
- Token totals
- Costi (totale e per area)
- Breakdown per giorno
- Breakdown per modello
- Breakdown per effort
- Breakdown per modello+effort
- Breakdown per repository

Nel report console la deduplica degli eventi token usa questa chiave:

- `timestamp`
- `total_tokens`
- `input_tokens`
- `output_tokens`

Questa regola evita doppi conteggi evidenti nel report aggregato, anche quando due righe token equivalenti compaiono nei file letti.

### CSV export

- `--export-events-csv`: dettaglio per evento
- `--export-daily-csv`: aggregato giornaliero
- `--export-model-costs-csv`: costi per modello
- `--export-repo-csv`: aggregato per repository

## 6) Import SQLite

Comando `import-sqlite`:

- salva `import_runs` (una riga per ogni esecuzione import, anche se idempotente)
- salva `raw_events` (tutte le righe JSONL)
- salva `token_events` (eventi token normalizzati)
- salva `pricing_profiles` e `pricing_profile_rates` per tracciare lo snapshot prezzi usato dall'import
- salva `workspace_cwd` e `repository` sugli eventi token quando ricavati da `turn_context`
- salva `pricing_used_default` per rendere espliciti i modelli non presenti nella tabella prezzi
- salva `cumulative_total_tokens` quando disponibile da `total_token_usage`
- salva i componenti separati del costo stimato: input non-cache, input cached e output
- espone la vista `repositories`, derivata da `token_events`, con token e costi aggregati per repository
- espone viste aggregate ricorrenti: `daily_usage`, `weekly_usage`, `monthly_usage`, `model_usage`, `model_effort_usage` e `repository_usage`
- idempotente via `raw_event_hash` (no duplicati su re-import)

L'import SQLite deduplica a livello di riga raw normalizzata (`raw_event_hash`). Questo conserva una relazione verificabile tra evento grezzo e token normalizzato.

Ogni import produce un `import_run_id` e salva:

- timestamp inizio/fine import;
- `sessions_dir` e flag `include_archived_sessions`;
- `source_device` e `source_account`;
- `pricing_profile_id`;
- contatori file, righe, inserimenti, duplicati e qualita' dati.

Il profilo prezzi e' uno snapshot del listino usato al momento dell'import. Se in futuro i prezzi configurati cambiano, i vecchi eventi mantengono il `pricing_profile_id` con cui sono stati calcolati; un re-import idempotente non ricalcola i costi degli eventi gia' presenti.

Se un database e' stato creato con una versione precedente dello schema, `import-sqlite` completa gli eventi token gia' presenti con `pricing_profile_id` e componenti separati del costo quando mancano.

L'import espone anche contatori di qualita' dati:

- righe JSON malformate;
- payload o tipo evento mancanti;
- eventi token con campi obbligatori mancanti;
- eventi non-token.

## 7) Esempi copy/paste

Prima di usare i comandi, puoi copiare `config.example.toml` in `config.toml` e adattare i path alla tua macchina.

### A) Summary usando `config.toml` (consigliato)

```powershell
$env:PYTHONPATH='src'
python -m codex_usage.cli --config config.toml summary `
  --save-report reports\summary.txt `
  --export-events-csv reports\events.csv `
  --export-daily-csv reports\daily_summary.csv `
  --export-model-costs-csv reports\model_costs.csv `
  --export-repo-csv reports\repo_summary.csv
```

### B) Summary senza config (PowerShell)

```powershell
$env:PYTHONPATH='src'
python -m codex_usage.cli summary `
  --sessions-dir "C:\Users\marco\.codex - Copia\sessions" `
  --include-archived-sessions `
  --save-report reports\summary.txt `
  --export-events-csv reports\events.csv `
  --export-daily-csv reports\daily_summary.csv `
  --export-model-costs-csv reports\model_costs.csv `
  --export-repo-csv reports\repo_summary.csv
```

### C) Summary senza config (Linux/macOS)

```bash
PYTHONPATH=src python -m codex_usage.cli summary \
  --sessions-dir "$HOME/.codex/sessions" \
  --include-archived-sessions \
  --save-report reports/summary.txt \
  --export-events-csv reports/events.csv \
  --export-daily-csv reports/daily_summary.csv \
  --export-model-costs-csv reports/model_costs.csv \
  --export-repo-csv reports/repo_summary.csv
```

### D) Import SQLite usando `config.toml`

```powershell
$env:PYTHONPATH='src'
python -m codex_usage.cli --config config.toml import-sqlite
```

### E) Import SQLite senza config (PowerShell)

```powershell
$env:PYTHONPATH='src'
python -m codex_usage.cli import-sqlite `
  --sessions-dir "C:\Users\marco\.codex - Copia\sessions" `
  --include-archived-sessions `
  --db-path data\codex_usage.db `
  --source-device windows-main `
  --source-account marco
```

### F) Report da SQLite usando `config.toml`

```bash
PYTHONPATH=src python -m codex_usage.cli --config config.toml report
```

Il comando `report` legge il database SQLite gia' importato e mostra totali, costi stimati, cache ratio, top repository, top modelli, riepilogo mensile e giornaliero recente.

Per salvare lo stesso output:

```bash
PYTHONPATH=src python -m codex_usage.cli --config config.toml report --save-report reports/sqlite-report.txt
```
