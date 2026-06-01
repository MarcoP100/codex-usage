from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from codex_usage.sqlite_report import SqliteUsageReportFilters, build_sqlite_usage_report
from codex_usage.text_report import fmt_pct, fmt_usd, human_tokens


def build_filter_state(
    query_params: Mapping[str, str],
) -> tuple[SqliteUsageReportFilters | None, dict[str, str], str | None]:
    form_values = {
        "from": query_params.get("from", ""),
        "to": query_params.get("to", ""),
        "repository": query_params.get("repository", ""),
        "model": query_params.get("model", ""),
    }
    try:
        return (
            SqliteUsageReportFilters(
                from_date=_clean_query_value(form_values["from"]),
                to_date=_clean_query_value(form_values["to"]),
                repository=_clean_query_value(form_values["repository"]),
                model=_clean_query_value(form_values["model"]),
            ),
            form_values,
            None,
        )
    except ValueError as exc:
        return (None, form_values, str(exc))


def build_dashboard_context(
    db_path: Path,
    filters: SqliteUsageReportFilters,
) -> dict[str, Any]:
    try:
        report = build_sqlite_usage_report(db_path, filters=filters)
    except sqlite3.Error as exc:
        return {
            "report": None,
            "report_error": f"SQLite database is not ready: {exc}",
        }

    totals = report.totals
    return {
        "report": {
            "period": _format_period(totals.first_seen_at, totals.last_seen_at),
            "filters_active": not filters.is_empty,
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
            "charts": {
                "daily": _format_chart_rows(list(reversed(report.recent_daily_usage))[-14:]),
                "repositories": _format_chart_rows(report.top_repositories[:8]),
                "models": _format_chart_rows(report.top_models[:8]),
            },
            "data_quality": _format_data_quality(report.recent_import_runs),
        },
        "report_error": None,
    }


def _clean_query_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


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


def _format_chart_rows(rows: list[Any]) -> list[dict[str, str]]:
    max_tokens = max((row.total_tokens for row in rows), default=0)
    chart_rows: list[dict[str, str]] = []
    for row in rows:
        width = 0 if max_tokens == 0 else max(3, round((row.total_tokens / max_tokens) * 100))
        chart_rows.append(
            {
                "label": str(row.key),
                "events": f"{row.events:,}",
                "tokens": human_tokens(row.total_tokens),
                "cost": fmt_usd(row.estimated_cost_usd),
                "width": str(width),
            }
        )
    return chart_rows


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


def _format_data_quality(rows: list[Any]) -> dict[str, Any]:
    latest = rows[0] if rows else None
    return {
        "latest": _format_import_run(latest) if latest is not None else None,
        "recent_imports": [_format_import_run(row) for row in rows],
    }


def _format_import_run(row: Any) -> dict[str, str]:
    source_parts = [part for part in (row.source_device, row.source_account) if part]
    return {
        "completed_at": row.completed_at,
        "source": " / ".join(source_parts) if source_parts else "n/a",
        "sessions_dir": row.sessions_dir,
        "files_scanned": f"{row.files_scanned:,}",
        "lines_scanned": f"{row.lines_scanned:,}",
        "raw_inserted": f"{row.raw_inserted:,}",
        "raw_skipped_duplicate": f"{row.raw_skipped_duplicate:,}",
        "token_inserted": f"{row.token_inserted:,}",
        "token_skipped_duplicate": f"{row.token_skipped_duplicate:,}",
        "malformed_json_lines": f"{row.malformed_json_lines:,}",
        "missing_payload_type": f"{row.missing_payload_type:,}",
        "missing_token_fields": f"{row.missing_token_fields:,}",
        "non_token_events": f"{row.non_token_events:,}",
        "default_pricing_token_events": f"{row.default_pricing_token_events:,}",
    }
