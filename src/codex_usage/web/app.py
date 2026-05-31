from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from codex_usage.sqlite_report import build_sqlite_usage_report
from codex_usage.text_report import fmt_pct, fmt_usd, human_tokens
from codex_usage.web.settings import load_web_settings


PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


def _format_period(first_seen_at: str | None, last_seen_at: str | None) -> str:
    if first_seen_at is None or last_seen_at is None:
        return "No token events"
    return f"{first_seen_at} -> {last_seen_at}"


def _format_breakdown_rows(rows: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "key": str(row.key),
            "events": f"{row.events:,}",
            "tokens": human_tokens(row.total_tokens),
            "cost": fmt_usd(row.estimated_cost_usd),
        }
        for row in rows
    ]


def _format_top_events(rows: list[Any]) -> list[dict[str, str]]:
    return [
        {
            "timestamp": row.timestamp,
            "repository": row.repository,
            "model": row.model,
            "tokens": human_tokens(row.total_tokens),
            "cost": fmt_usd(row.estimated_cost_usd),
            "session_file": row.session_file,
        }
        for row in rows
    ]


def _dashboard_context(db_path: Path) -> dict[str, Any]:
    try:
        report = build_sqlite_usage_report(db_path)
    except sqlite3.Error as exc:
        return {
            "report": None,
            "report_error": f"SQLite database is not ready: {exc}",
        }

    totals = report.totals
    return {
        "report": {
            "period": _format_period(totals.first_seen_at, totals.last_seen_at),
            "import_runs": f"{report.import_runs_count:,}",
            "latest_import": (
                report.latest_import_run.completed_at
                if report.latest_import_run is not None
                else "n/a"
            ),
            "totals": [
                ("Events", f"{totals.events:,}"),
                ("Total tokens", human_tokens(totals.total_tokens)),
                ("Input tokens", human_tokens(totals.input_tokens)),
                ("Cached input", human_tokens(totals.cached_input_tokens)),
                ("Output tokens", human_tokens(totals.output_tokens)),
                ("Cache ratio", fmt_pct(totals.cached_input_tokens, totals.input_tokens)),
                ("Estimated cost", fmt_usd(totals.estimated_cost_usd)),
                ("Default pricing events", f"{totals.default_pricing_events:,}"),
            ],
            "top_repositories": _format_breakdown_rows(report.top_repositories[:5]),
            "top_models": _format_breakdown_rows(report.top_models[:5]),
            "top_days": _format_breakdown_rows(report.top_days[:5]),
            "top_sessions": _format_breakdown_rows(report.top_sessions[:5]),
            "top_events": _format_top_events(report.top_events[:5]),
        },
        "report_error": None,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="codex-usage dashboard")
    app.mount(
        "/static",
        StaticFiles(directory=str(PACKAGE_DIR / "static")),
        name="static",
    )

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request) -> HTMLResponse:
        settings = load_web_settings()
        db_path = settings.db_path.expanduser()
        dashboard = _dashboard_context(db_path) if settings.db_exists else {
            "report": None,
            "report_error": "SQLite database file was not found.",
        }
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "db_exists": settings.db_exists,
                "db_path": str(db_path),
                "db_path_source": settings.db_path_source,
                **dashboard,
            },
        )

    return app


app = create_app()
