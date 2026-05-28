from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class SqliteUsageTotals:
    first_seen_at: str | None
    last_seen_at: str | None
    events: int
    input_tokens: int
    cached_input_tokens: int
    non_cached_input_tokens: int
    output_tokens: int
    reasoning_output_tokens: int
    total_tokens: int
    estimated_non_cached_input_cost_usd: float
    estimated_cached_input_cost_usd: float
    estimated_output_cost_usd: float
    estimated_cost_usd: float
    default_pricing_events: int


@dataclass(frozen=True, slots=True)
class SqliteUsageBreakdownRow:
    key: str
    events: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


@dataclass(frozen=True, slots=True)
class SqliteImportRun:
    import_run_id: str
    completed_at: str
    files_scanned: int
    lines_scanned: int
    token_inserted: int
    token_skipped_duplicate: int


@dataclass(frozen=True, slots=True)
class SqliteUsageReportData:
    db_path: Path
    totals: SqliteUsageTotals
    import_runs_count: int
    latest_import_run: SqliteImportRun | None
    top_repositories: list[SqliteUsageBreakdownRow]
    top_models: list[SqliteUsageBreakdownRow]
    recent_daily_usage: list[SqliteUsageBreakdownRow]
    monthly_usage: list[SqliteUsageBreakdownRow]


def build_sqlite_usage_report(db_path: Path) -> SqliteUsageReportData:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return SqliteUsageReportData(
            db_path=db_path,
            totals=_fetch_totals(conn),
            import_runs_count=_fetch_import_runs_count(conn),
            latest_import_run=_fetch_latest_import_run(conn),
            top_repositories=_fetch_breakdown(
                conn,
                view_name="repository_usage",
                key_column="repository",
            ),
            top_models=_fetch_breakdown(
                conn,
                view_name="model_usage",
                key_column="model",
            ),
            recent_daily_usage=_fetch_breakdown(
                conn,
                view_name="daily_usage",
                key_column="usage_date",
                limit=14,
                order_by="usage_date DESC",
            ),
            monthly_usage=_fetch_breakdown(
                conn,
                view_name="monthly_usage",
                key_column="usage_month",
                limit=None,
                order_by="usage_month",
            ),
        )
    finally:
        conn.close()


def _fetch_totals(conn: sqlite3.Connection) -> SqliteUsageTotals:
    row = conn.execute(
        """
        SELECT
            MIN(timestamp) AS first_seen_at,
            MAX(timestamp) AS last_seen_at,
            COUNT(*) AS events,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
            COALESCE(SUM(non_cached_input_tokens), 0) AS non_cached_input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COALESCE(SUM(reasoning_output_tokens), 0) AS reasoning_output_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(estimated_non_cached_input_cost_usd), 0) AS non_cached_cost,
            COALESCE(SUM(estimated_cached_input_cost_usd), 0) AS cached_cost,
            COALESCE(SUM(estimated_output_cost_usd), 0) AS output_cost,
            COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost,
            COALESCE(SUM(pricing_used_default), 0) AS default_pricing_events
        FROM token_events
        """
    ).fetchone()
    return SqliteUsageTotals(
        first_seen_at=row["first_seen_at"],
        last_seen_at=row["last_seen_at"],
        events=row["events"],
        input_tokens=row["input_tokens"],
        cached_input_tokens=row["cached_input_tokens"],
        non_cached_input_tokens=row["non_cached_input_tokens"],
        output_tokens=row["output_tokens"],
        reasoning_output_tokens=row["reasoning_output_tokens"],
        total_tokens=row["total_tokens"],
        estimated_non_cached_input_cost_usd=row["non_cached_cost"],
        estimated_cached_input_cost_usd=row["cached_cost"],
        estimated_output_cost_usd=row["output_cost"],
        estimated_cost_usd=row["estimated_cost"],
        default_pricing_events=row["default_pricing_events"],
    )


def _fetch_import_runs_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS count FROM import_runs").fetchone()
    return row["count"]


def _fetch_latest_import_run(conn: sqlite3.Connection) -> SqliteImportRun | None:
    row = conn.execute(
        """
        SELECT import_run_id, completed_at, files_scanned, lines_scanned,
               token_inserted, token_skipped_duplicate
        FROM import_runs
        ORDER BY completed_at DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return SqliteImportRun(
        import_run_id=row["import_run_id"],
        completed_at=row["completed_at"],
        files_scanned=row["files_scanned"],
        lines_scanned=row["lines_scanned"],
        token_inserted=row["token_inserted"],
        token_skipped_duplicate=row["token_skipped_duplicate"],
    )


def _fetch_breakdown(
    conn: sqlite3.Connection,
    *,
    view_name: str,
    key_column: str,
    limit: int | None = 10,
    order_by: str = "estimated_cost_usd DESC",
) -> list[SqliteUsageBreakdownRow]:
    limit_clause = "" if limit is None else "LIMIT ?"
    params = () if limit is None else (limit,)
    rows = conn.execute(
        f"""
        SELECT {key_column} AS key, events, input_tokens, cached_input_tokens,
               output_tokens, total_tokens, estimated_cost_usd
        FROM {view_name}
        ORDER BY {order_by}
        {limit_clause}
        """,
        params,
    ).fetchall()
    return [
        SqliteUsageBreakdownRow(
            key=row["key"],
            events=row["events"],
            input_tokens=row["input_tokens"],
            cached_input_tokens=row["cached_input_tokens"],
            output_tokens=row["output_tokens"],
            total_tokens=row["total_tokens"],
            estimated_cost_usd=row["estimated_cost_usd"],
        )
        for row in rows
    ]
