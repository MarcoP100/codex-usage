from __future__ import annotations

from codex_usage.sqlite_report import (
    SqliteUsageBreakdownRow,
    SqliteUsageEventHighlight,
    SqliteUsageReportData,
)
from codex_usage.text_report import fmt_pct, fmt_tokens, fmt_usd


def render_sqlite_usage_markdown(data: SqliteUsageReportData) -> str:
    totals = data.totals
    lines: list[str] = []
    lines.append("# Codex Usage Report")
    lines.append("")
    lines.append(f"- **SQLite DB:** `{data.db_path}`")
    lines.append(f"- **Filters:** {_format_filters(data)}")
    lines.append(f"- **Period:** {_format_period(totals.first_seen_at, totals.last_seen_at)}")
    lines.append(f"- **Import runs:** {data.import_runs_count:,}")
    if data.latest_import_run is not None:
        lines.append(f"- **Latest import:** {data.latest_import_run.completed_at}")
    lines.append("")
    lines.append("## Token Totals")
    lines.extend(
        _markdown_table(
            ["Metric", "Value"],
            [
                ["Events", f"{totals.events:,}"],
                ["Input tokens", fmt_tokens(totals.input_tokens)],
                ["Cached input tokens", fmt_tokens(totals.cached_input_tokens)],
                ["Non-cached input", fmt_tokens(totals.non_cached_input_tokens)],
                ["Output tokens", fmt_tokens(totals.output_tokens)],
                ["Reasoning tokens", fmt_tokens(totals.reasoning_output_tokens)],
                ["Usage tokens estimate", fmt_tokens(totals.total_tokens)],
                ["Cache ratio", fmt_pct(totals.cached_input_tokens, totals.input_tokens)],
            ],
        )
    )
    lines.append("")
    lines.append("## API-Equivalent Estimate")
    lines.extend(
        _markdown_table(
            ["Component", "Estimated Cost"],
            [
                ["Non-cached input", fmt_usd(totals.estimated_non_cached_input_cost_usd)],
                ["Cached input", fmt_usd(totals.estimated_cached_input_cost_usd)],
                ["Output", fmt_usd(totals.estimated_output_cost_usd)],
                ["Total", fmt_usd(totals.estimated_cost_usd)],
                ["Default pricing events", f"{totals.default_pricing_events:,}"],
            ],
        )
    )
    lines.append("")
    _append_breakdown_table(lines, "Top Repositories", data.top_repositories)
    _append_breakdown_table(lines, "Top Models", data.top_models)
    _append_breakdown_table(lines, "Top Days", data.top_days)
    _append_breakdown_table(lines, "Top Sessions", data.top_sessions)
    _append_events_table(lines, data.top_events)
    _append_breakdown_table(lines, "Monthly Usage", data.monthly_usage)
    _append_breakdown_table(
        lines,
        "Recent Daily Usage",
        list(reversed(data.recent_daily_usage)),
    )
    if data.group_by is not None:
        _append_breakdown_table(lines, f"Usage By {data.group_by.title()}", data.grouped_usage)
    return "\n".join(lines).rstrip() + "\n"


def _format_period(first_seen_at: str | None, last_seen_at: str | None) -> str:
    if first_seen_at is None or last_seen_at is None:
        return "empty"
    return f"{first_seen_at} -> {last_seen_at}"


def _format_filters(data: SqliteUsageReportData) -> str:
    filters = data.filters
    if filters.is_empty:
        return "none"
    parts: list[str] = []
    if filters.from_date:
        parts.append(f"`from={filters.from_date}`")
    if filters.to_date:
        parts.append(f"`to={filters.to_date}`")
    if filters.repository:
        parts.append(f"`repository={filters.repository}`")
    if filters.model:
        parts.append(f"`model={filters.model}`")
    return ", ".join(parts)


def _append_breakdown_table(
    lines: list[str],
    title: str,
    rows: list[SqliteUsageBreakdownRow],
) -> None:
    lines.append(f"## {title}")
    if not rows:
        lines.append("")
        lines.append("No data.")
        lines.append("")
        return
    lines.extend(
        _markdown_table(
            ["Key", "Events", "Tokens", "Estimated Cost"],
            [
                [
                    row.key,
                    f"{row.events:,}",
                    fmt_tokens(row.total_tokens),
                    fmt_usd(row.estimated_cost_usd),
                ]
                for row in rows
            ],
        )
    )
    lines.append("")


def _append_events_table(
    lines: list[str],
    rows: list[SqliteUsageEventHighlight],
) -> None:
    lines.append("## Top Events")
    if not rows:
        lines.append("")
        lines.append("No data.")
        lines.append("")
        return
    lines.extend(
        _markdown_table(
            ["Timestamp", "Repository", "Model", "Tokens", "Cost", "Session"],
            [
                [
                    row.timestamp,
                    row.repository,
                    row.model,
                    fmt_tokens(row.total_tokens),
                    fmt_usd(row.estimated_cost_usd),
                    row.session_file,
                ]
                for row in rows
            ],
        )
    )
    lines.append("")


def _markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    table = [
        "| " + " | ".join(_escape_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        table.append("| " + " | ".join(_escape_cell(value) for value in row) + " |")
    return table


def _escape_cell(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")
