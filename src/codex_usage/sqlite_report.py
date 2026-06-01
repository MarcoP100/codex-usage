from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
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
class SqliteUsageEventHighlight:
    timestamp: str
    session_file: str
    repository: str
    model: str
    total_tokens: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


@dataclass(frozen=True, slots=True)
class SqliteUsageReportFilters:
    from_date: str | None = None
    to_date: str | None = None
    repository: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        _validate_iso_date(self.from_date, "--from")
        _validate_iso_date(self.to_date, "--to")
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("--from must be earlier than or equal to --to")

    @property
    def is_empty(self) -> bool:
        return not any((self.from_date, self.to_date, self.repository, self.model))


@dataclass(frozen=True, slots=True)
class SqliteImportRun:
    import_run_id: str
    started_at: str
    completed_at: str
    sessions_dir: str
    source_device: str | None
    source_account: str | None
    files_scanned: int
    lines_scanned: int
    raw_inserted: int
    raw_skipped_duplicate: int
    token_inserted: int
    token_skipped_duplicate: int
    malformed_json_lines: int
    missing_payload_type: int
    missing_token_fields: int
    non_token_events: int
    default_pricing_token_events: int


@dataclass(frozen=True, slots=True)
class SqliteUsageReportData:
    db_path: Path
    filters: SqliteUsageReportFilters
    group_by: str | None
    totals: SqliteUsageTotals
    import_runs_count: int
    latest_import_run: SqliteImportRun | None
    recent_import_runs: list[SqliteImportRun]
    top_repositories: list[SqliteUsageBreakdownRow]
    top_models: list[SqliteUsageBreakdownRow]
    recent_daily_usage: list[SqliteUsageBreakdownRow]
    monthly_usage: list[SqliteUsageBreakdownRow]
    grouped_usage: list[SqliteUsageBreakdownRow]
    top_days: list[SqliteUsageBreakdownRow]
    top_sessions: list[SqliteUsageBreakdownRow]
    top_events: list[SqliteUsageEventHighlight]


def build_sqlite_usage_report(
    db_path: Path,
    filters: SqliteUsageReportFilters | None = None,
    group_by: str | None = None,
) -> SqliteUsageReportData:
    filters = filters or SqliteUsageReportFilters()
    if group_by is not None and group_by not in _GROUP_EXPRESSIONS:
        raise ValueError("--group-by must be one of: day, week, month")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return SqliteUsageReportData(
            db_path=db_path,
            filters=filters,
            group_by=group_by,
            totals=_fetch_totals(conn, filters),
            import_runs_count=_fetch_import_runs_count(conn),
            latest_import_run=_fetch_latest_import_run(conn),
            recent_import_runs=_fetch_recent_import_runs(conn),
            top_repositories=_fetch_breakdown(
                conn,
                filters=filters,
                key_expression="repository",
            ),
            top_models=_fetch_breakdown(
                conn,
                filters=filters,
                key_expression="COALESCE(model, 'unknown')",
            ),
            recent_daily_usage=_fetch_breakdown(
                conn,
                filters=filters,
                key_expression="substr(timestamp, 1, 10)",
                limit=14,
                order_by="key DESC",
            ),
            monthly_usage=_fetch_breakdown(
                conn,
                filters=filters,
                key_expression="substr(timestamp, 1, 7)",
                limit=None,
                order_by="key",
            ),
            grouped_usage=_fetch_grouped_usage(conn, filters=filters, group_by=group_by),
            top_days=_fetch_breakdown(
                conn,
                filters=filters,
                key_expression="substr(timestamp, 1, 10)",
            ),
            top_sessions=_fetch_breakdown(
                conn,
                filters=filters,
                key_expression="session_file",
            ),
            top_events=_fetch_top_events(conn, filters=filters),
        )
    finally:
        conn.close()


_GROUP_EXPRESSIONS = {
    "day": "substr(timestamp, 1, 10)",
    "week": "strftime('%Y-W%W', replace(substr(timestamp, 1, 19), 'T', ' '))",
    "month": "substr(timestamp, 1, 7)",
}


def _validate_iso_date(value: str | None, option_name: str) -> None:
    if value is None:
        return
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{option_name} must use YYYY-MM-DD format") from exc


def _where_clause(filters: SqliteUsageReportFilters) -> tuple[str, list[str]]:
    clauses: list[str] = []
    params: list[str] = []
    if filters.from_date:
        clauses.append("substr(timestamp, 1, 10) >= ?")
        params.append(filters.from_date)
    if filters.to_date:
        clauses.append("substr(timestamp, 1, 10) <= ?")
        params.append(filters.to_date)
    if filters.repository:
        clauses.append("repository = ?")
        params.append(filters.repository)
    if filters.model:
        clauses.append("model = ?")
        params.append(filters.model)
    if not clauses:
        return ("", params)
    return ("WHERE " + " AND ".join(clauses), params)


def _fetch_totals(
    conn: sqlite3.Connection,
    filters: SqliteUsageReportFilters,
) -> SqliteUsageTotals:
    where_sql, params = _where_clause(filters)
    row = conn.execute(
        f"""
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
        {where_sql}
        """,
        params,
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
    rows = _fetch_recent_import_runs(conn, limit=1)
    if not rows:
        return None
    return rows[0]


def _fetch_recent_import_runs(
    conn: sqlite3.Connection,
    *,
    limit: int = 5,
) -> list[SqliteImportRun]:
    rows = conn.execute(
        """
        SELECT import_run_id, started_at, completed_at, sessions_dir,
               source_device, source_account, files_scanned, lines_scanned,
               raw_inserted, raw_skipped_duplicate, token_inserted,
               token_skipped_duplicate, malformed_json_lines,
               missing_payload_type, missing_token_fields, non_token_events,
               default_pricing_token_events
        FROM import_runs
        ORDER BY completed_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [_import_run_from_row(row) for row in rows]


def _import_run_from_row(row: sqlite3.Row) -> SqliteImportRun:
    return SqliteImportRun(
        import_run_id=row["import_run_id"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        sessions_dir=row["sessions_dir"],
        source_device=row["source_device"],
        source_account=row["source_account"],
        files_scanned=row["files_scanned"],
        lines_scanned=row["lines_scanned"],
        raw_inserted=row["raw_inserted"],
        raw_skipped_duplicate=row["raw_skipped_duplicate"],
        token_inserted=row["token_inserted"],
        token_skipped_duplicate=row["token_skipped_duplicate"],
        malformed_json_lines=row["malformed_json_lines"],
        missing_payload_type=row["missing_payload_type"],
        missing_token_fields=row["missing_token_fields"],
        non_token_events=row["non_token_events"],
        default_pricing_token_events=row["default_pricing_token_events"],
    )


def _fetch_breakdown(
    conn: sqlite3.Connection,
    *,
    filters: SqliteUsageReportFilters,
    key_expression: str,
    limit: int | None = 10,
    order_by: str = "estimated_cost_usd DESC",
) -> list[SqliteUsageBreakdownRow]:
    where_sql, params = _where_clause(filters)
    limit_clause = "" if limit is None else "LIMIT ?"
    query_params: list[str | int] = [*params]
    if limit is not None:
        query_params.append(limit)
    rows = conn.execute(
        f"""
        SELECT
            {key_expression} AS key,
            COUNT(*) AS events,
            COALESCE(SUM(input_tokens), 0) AS input_tokens,
            COALESCE(SUM(cached_input_tokens), 0) AS cached_input_tokens,
            COALESCE(SUM(output_tokens), 0) AS output_tokens,
            COALESCE(SUM(total_tokens), 0) AS total_tokens,
            COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
        FROM token_events
        {where_sql}
        GROUP BY key
        ORDER BY {order_by}
        {limit_clause}
        """,
        query_params,
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


def _fetch_grouped_usage(
    conn: sqlite3.Connection,
    *,
    filters: SqliteUsageReportFilters,
    group_by: str | None,
) -> list[SqliteUsageBreakdownRow]:
    if group_by is None:
        return []
    return _fetch_breakdown(
        conn,
        filters=filters,
        key_expression=_GROUP_EXPRESSIONS[group_by],
        limit=None,
        order_by="key",
    )


def _fetch_top_events(
    conn: sqlite3.Connection,
    *,
    filters: SqliteUsageReportFilters,
    limit: int = 10,
) -> list[SqliteUsageEventHighlight]:
    where_sql, params = _where_clause(filters)
    rows = conn.execute(
        f"""
        SELECT timestamp, session_file, repository, COALESCE(model, 'unknown') AS model,
               total_tokens, input_tokens, cached_input_tokens, output_tokens,
               estimated_cost_usd
        FROM token_events
        {where_sql}
        ORDER BY total_tokens DESC, estimated_cost_usd DESC
        LIMIT ?
        """,
        [*params, limit],
    ).fetchall()
    return [
        SqliteUsageEventHighlight(
            timestamp=row["timestamp"],
            session_file=row["session_file"],
            repository=row["repository"],
            model=row["model"],
            total_tokens=row["total_tokens"],
            input_tokens=row["input_tokens"],
            cached_input_tokens=row["cached_input_tokens"],
            output_tokens=row["output_tokens"],
            estimated_cost_usd=row["estimated_cost_usd"],
        )
        for row in rows
    ]
