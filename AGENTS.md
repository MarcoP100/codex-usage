# AGENTS.md

## Obiettivo

Mantenere `codex-usage` semplice, locale e manutenibile. Anche se e' un progetto personale, il codice deve restare presentabile, testabile e facile da condividere.

## Regole architetturali

- `cli.py` deve orchestrare comandi, parsing argomenti, chiamate ai servizi e output finale. Non deve contenere logica di parsing, aggregazione o persistenza.
- `db.py` deve occuparsi di schema SQLite e persistenza. Non deve contenere logica di scansione sessioni o aggregazione report.
- `ingestion.py` e' il punto unico per leggere sessioni, gestire `turn_context`, arricchire eventi token e raccogliere data quality.
- `pricing.py` e' il punto unico per prezzi, fallback e calcolo costi.
- `usage_summary.py` e' il punto unico per deduplica e aggregazioni del report.
- `text_report.py` genera solo testo leggibile. Non deve modificare dati o calcolare metriche nuove.
- `markdown_report.py` genera solo Markdown leggibile. Non deve modificare dati o calcolare metriche nuove.
- Le app, le dashboard e i report avanzati devono leggere da SQLite. I JSONL sono sorgente di import/ricostruzione, non una sorgente dati diretta per la UI.
- `parser.py` deve restare tollerante e focalizzato sul parsing di una singola riga JSONL.
- `models.py` contiene dataclass condivise e tipi di dominio.

## Soglie pratiche

- Evitare funzioni oltre 100 righe.
- Se una funzione supera 80 righe, valutare se sta facendo piu' di una cosa.
- Evitare duplicazioni tra CLI e SQLite.
- Ogni nuova metrica deve avere una sola fonte di calcolo.
- Ogni modifica a parsing, deduplica, pricing o import deve avere test.

## Dati e output

- `docs/` contiene solo documentazione.
- `data/` contiene database e dati locali generati.
- `reports/` contiene report e CSV generati.
- Non scrivere ne' modificare le sessioni Codex originali.
- Per sviluppo locale preferire una copia delle sessioni.
- La cartella `.codex` o la sua copia di backup e' la sorgente ricostruibile primaria.
- Il database SQLite in `data/` e' importante per l'uso quotidiano, ma deve restare ricostruibile dai JSONL salvati.
- Prima di cambiare schema o import, preservare la possibilita' di rigenerare il DB da una copia delle sessioni.

## Test

Prima di considerare conclusa una modifica:

```bash
PYTHONPATH=src python -m pytest
```

## Roadmap

Seguire `docs/project-roadmap.md`. Se una scelta tecnica cambia la roadmap, aggiornare il documento nello stesso giro.
