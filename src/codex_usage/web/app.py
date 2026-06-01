from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from codex_usage.web.settings import load_web_settings
from codex_usage.web.view_models import build_dashboard_context, build_filter_state


PACKAGE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))


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
        filters, filter_values, filter_error = build_filter_state(request.query_params)
        dashboard = build_dashboard_context(db_path, filters) if settings.db_exists and filters is not None else {
            "report": None,
            "report_error": filter_error or "SQLite database file was not found.",
        }
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "db_exists": settings.db_exists,
                "db_path": str(db_path),
                "db_path_source": settings.db_path_source,
                "filter_values": filter_values,
                **dashboard,
            },
        )

    return app


app = create_app()
