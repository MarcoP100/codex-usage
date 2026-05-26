# codex-usage

Strumento locale per analizzare l'uso di Codex a partire dai file di sessione `*.jsonl`.

Il progetto oggi include una CLI per produrre report su token, cache, modelli, reasoning effort, repository e costi stimati API-equivalenti. Include anche export CSV e import idempotente in SQLite.

Il punto non e' ricostruire il billing ufficiale, ma avere un osservatorio personale e locale sull'uso di Codex.

## Documenti

- [Documento di progetto e roadmap](docs/project-roadmap.md)
- [Funzionamento attuale e comandi](docs/how-codex-usage-works.md)
- [Esempio configurazione](config.example.toml)

## Requisiti

- Python 3.11 o superiore.
- Accesso locale alla directory sessioni di Codex.

Il progetto non richiede dipendenze runtime esterne. Per i test usa `pytest`.

## Setup locale

Clona o apri il repository, poi crea una virtualenv se vuoi lavorare in isolamento:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python -m pip install pytest
```

Prepara la configurazione copiando l'esempio:

```powershell
Copy-Item config.example.toml config.toml
```

Poi modifica `config.toml` impostando `sessions_dir` se vuoi usare una directory diversa da quella predefinita di Codex.

## Uso rapido

Report sintetico:

```powershell
$env:PYTHONPATH='src'
python -m codex_usage.cli --config config.toml summary
```

Per importare i dati in SQLite:

```powershell
$env:PYTHONPATH='src'
python -m codex_usage.cli --config config.toml import-sqlite
```

Report con export principali:

```powershell
$env:PYTHONPATH='src'
python -m codex_usage.cli --config config.toml summary `
  --save-report reports\summary.txt `
  --export-events-csv reports\events.csv `
  --export-daily-csv reports\daily_summary.csv `
  --export-model-costs-csv reports\model_costs.csv `
  --export-repo-csv reports\repo_summary.csv
```

## Organizzazione file

- `docs/`: documentazione del progetto.
- `data/`: database SQLite locale e altri dati generati.
- `reports/`: report testuali e CSV generati dalla CLI.
- `src/`: codice applicativo.
- `tests/`: test automatici.

Per lavorare in sicurezza puoi puntare `sessions_dir` a una copia locale delle sessioni Codex, come nel `config.toml` usato in questo progetto.

## Output

- Report testuale con qualita' dati, totali token, costo stimato e breakdown.
- CSV eventi.
- CSV riepilogo giornaliero.
- CSV costi stimati per modello.
- CSV riepilogo per repository.
- Database SQLite locale con eventi grezzi e token normalizzati.

## Nota sui costi

I costi mostrati sono stime API-equivalenti calcolate con i prezzi configurati nel codice. Non sono il billing ufficiale OpenAI e non rappresentano il costo reale dell'infrastruttura.

Servono per confrontare ordini di grandezza, individuare trend e capire quali repository, modelli o giornate pesano di piu'.

## Test

```powershell
python -m pytest
```

## Stato

Progetto personale, non urgente, sviluppato in modo incrementale. La priorita' e' avere metriche locali affidabili prima di aggiungere dashboard o automazioni.
