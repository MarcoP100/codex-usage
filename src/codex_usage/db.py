from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codex_usage.ingestion import DataQuality, ParsedSessionLine, iter_session_lines
from codex_usage.models import TokenUsageEvent
from codex_usage.pricing import CostBreakdown, cost_breakdown_usd
from codex_usage.repository import repository_key_from_cwd


def _normalized_hash(line: str) -> str:
    return hashlib.sha256(line.strip().encode("utf-8")).hexdigest()


def _relative_session_file(base_dir: Path, file_path: Path) -> str:
    try:
        return str(file_path.resolve().relative_to(base_dir.resolve()))
    except ValueError:
        return str(file_path)


def _parse_json_dict(line: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _extract_raw_event_timestamp(payload: dict[str, Any]) -> str | None:
    for key in ("timestamp", "created_at"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    event_payload = payload.get("payload")
    if isinstance(event_payload, dict):
        value = event_payload.get("timestamp")
        if isinstance(value, str) and value:
            return value
    return None


def _extract_raw_event_type(payload: dict[str, Any]) -> str | None:
    event_type = payload.get("type")
    if isinstance(event_type, str) and event_type:
        return event_type
    return None


def _create_schema(conn: sqlite3.Connection) -> None:
    _create_import_runs_schema(conn)
    _create_pricing_profile_schema(conn)
    _create_raw_events_schema(conn)
    _create_token_events_schema(conn)
    _create_indexes_and_migrations(conn)
    _create_repository_views(conn)
    _create_usage_views(conn)


def _create_import_runs_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS import_runs (
            import_run_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT NOT NULL,
            sessions_dir TEXT NOT NULL,
            include_archived_sessions INTEGER NOT NULL,
            source_device TEXT,
            source_account TEXT,
            files_scanned INTEGER NOT NULL,
            lines_scanned INTEGER NOT NULL,
            raw_inserted INTEGER NOT NULL,
            raw_skipped_duplicate INTEGER NOT NULL,
            token_inserted INTEGER NOT NULL,
            token_skipped_duplicate INTEGER NOT NULL,
            malformed_json_lines INTEGER NOT NULL,
            missing_payload_type INTEGER NOT NULL,
            missing_token_fields INTEGER NOT NULL,
            non_token_events INTEGER NOT NULL,
            default_pricing_token_events INTEGER NOT NULL,
            pricing_profile_id TEXT,
            FOREIGN KEY(pricing_profile_id) REFERENCES pricing_profiles(pricing_profile_id)
        )
        """
    )


def _create_pricing_profile_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pricing_profiles (
            pricing_profile_id TEXT PRIMARY KEY,
            profile_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            pricing_json TEXT NOT NULL,
            default_non_cached_input_usd_per_million REAL NOT NULL,
            default_cached_input_usd_per_million REAL NOT NULL,
            default_output_usd_per_million REAL NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pricing_profile_rates (
            pricing_profile_id TEXT NOT NULL,
            model TEXT NOT NULL,
            non_cached_input_usd_per_million REAL NOT NULL,
            cached_input_usd_per_million REAL NOT NULL,
            output_usd_per_million REAL NOT NULL,
            PRIMARY KEY (pricing_profile_id, model),
            FOREIGN KEY(pricing_profile_id) REFERENCES pricing_profiles(pricing_profile_id)
        )
        """
    )


def _create_raw_events_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS raw_events (
            raw_event_hash TEXT PRIMARY KEY,
            source_device TEXT,
            source_account TEXT,
            session_file TEXT NOT NULL,
            line_number INTEGER NOT NULL,
            event_type TEXT,
            timestamp TEXT,
            raw_json TEXT NOT NULL,
            imported_at TEXT NOT NULL
        )
        """
    )


def _create_token_events_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS token_events (
            event_id TEXT PRIMARY KEY,
            source_device TEXT,
            source_account TEXT,
            session_file TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            model TEXT,
            reasoning_effort TEXT,
            workspace_cwd TEXT,
            repository TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            cached_input_tokens INTEGER NOT NULL,
            non_cached_input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            reasoning_output_tokens INTEGER NOT NULL,
            total_tokens INTEGER NOT NULL,
            cumulative_total_tokens INTEGER,
            estimated_non_cached_input_cost_usd REAL NOT NULL DEFAULT 0,
            estimated_cached_input_cost_usd REAL NOT NULL DEFAULT 0,
            estimated_output_cost_usd REAL NOT NULL DEFAULT 0,
            estimated_cost_usd REAL NOT NULL,
            pricing_used_default INTEGER NOT NULL DEFAULT 0,
            pricing_profile_id TEXT,
            raw_event_hash TEXT NOT NULL UNIQUE,
            imported_at TEXT NOT NULL,
            FOREIGN KEY(pricing_profile_id) REFERENCES pricing_profiles(pricing_profile_id),
            FOREIGN KEY(raw_event_hash) REFERENCES raw_events(raw_event_hash)
        )
        """
    )


def _create_indexes_and_migrations(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_raw_events_timestamp ON raw_events(timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_raw_events_event_type ON raw_events(event_type)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_events_timestamp ON token_events(timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_events_model ON token_events(model)"
    )
    _ensure_column(conn, "token_events", "workspace_cwd", "TEXT")
    _ensure_column(conn, "token_events", "repository", "TEXT NOT NULL DEFAULT 'unknown'")
    _ensure_column(conn, "token_events", "pricing_used_default", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(conn, "token_events", "pricing_profile_id", "TEXT")
    _ensure_column(conn, "import_runs", "pricing_profile_id", "TEXT")
    _ensure_column(conn, "token_events", "cumulative_total_tokens", "INTEGER")
    _ensure_column(
        conn,
        "token_events",
        "estimated_non_cached_input_cost_usd",
        "REAL NOT NULL DEFAULT 0",
    )
    _ensure_column(
        conn,
        "token_events",
        "estimated_cached_input_cost_usd",
        "REAL NOT NULL DEFAULT 0",
    )
    _ensure_column(
        conn,
        "token_events",
        "estimated_output_cost_usd",
        "REAL NOT NULL DEFAULT 0",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_events_repository ON token_events(repository)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_import_runs_completed_at ON import_runs(completed_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_events_pricing_profile ON token_events(pricing_profile_id)"
    )


def _create_repository_views(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE VIEW IF NOT EXISTS repositories AS
        SELECT
            repository,
            MIN(timestamp) AS first_seen_at,
            MAX(timestamp) AS last_seen_at,
            COUNT(*) AS events,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(non_cached_input_tokens) AS non_cached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens,
            SUM(estimated_non_cached_input_cost_usd) AS estimated_non_cached_input_cost_usd,
            SUM(estimated_cached_input_cost_usd) AS estimated_cached_input_cost_usd,
            SUM(estimated_output_cost_usd) AS estimated_output_cost_usd,
            SUM(estimated_cost_usd) AS estimated_cost_usd,
            SUM(pricing_used_default) AS default_pricing_events
        FROM token_events
        GROUP BY repository
        """
    )


def _create_usage_views(conn: sqlite3.Connection) -> None:
    _create_aggregate_view(
        conn,
        view_name="daily_usage",
        dimensions=[("substr(timestamp, 1, 10)", "usage_date")],
    )
    _create_aggregate_view(
        conn,
        view_name="weekly_usage",
        dimensions=[
            (
                "strftime('%Y-W%W', replace(substr(timestamp, 1, 19), 'T', ' '))",
                "usage_week",
            )
        ],
    )
    _create_aggregate_view(
        conn,
        view_name="monthly_usage",
        dimensions=[("substr(timestamp, 1, 7)", "usage_month")],
    )
    _create_aggregate_view(
        conn,
        view_name="model_usage",
        dimensions=[("COALESCE(model, 'unknown')", "model")],
    )
    _create_aggregate_view(
        conn,
        view_name="model_effort_usage",
        dimensions=[
            ("COALESCE(model, 'unknown')", "model"),
            ("COALESCE(reasoning_effort, 'unknown')", "reasoning_effort"),
        ],
    )
    _create_aggregate_view(
        conn,
        view_name="repository_usage",
        dimensions=[("repository", "repository")],
    )


def _create_aggregate_view(
    conn: sqlite3.Connection,
    *,
    view_name: str,
    dimensions: list[tuple[str, str]],
) -> None:
    select_dimensions = ",\n            ".join(
        f"{expression} AS {alias}" for expression, alias in dimensions
    )
    group_dimensions = ", ".join(alias for _, alias in dimensions)
    conn.execute(
        f"""
        CREATE VIEW IF NOT EXISTS {view_name} AS
        SELECT
            {select_dimensions},
            MIN(timestamp) AS first_seen_at,
            MAX(timestamp) AS last_seen_at,
            COUNT(*) AS events,
            SUM(input_tokens) AS input_tokens,
            SUM(cached_input_tokens) AS cached_input_tokens,
            SUM(non_cached_input_tokens) AS non_cached_input_tokens,
            SUM(output_tokens) AS output_tokens,
            SUM(reasoning_output_tokens) AS reasoning_output_tokens,
            SUM(total_tokens) AS total_tokens,
            SUM(estimated_non_cached_input_cost_usd) AS estimated_non_cached_input_cost_usd,
            SUM(estimated_cached_input_cost_usd) AS estimated_cached_input_cost_usd,
            SUM(estimated_output_cost_usd) AS estimated_output_cost_usd,
            SUM(estimated_cost_usd) AS estimated_cost_usd,
            SUM(pricing_used_default) AS default_pricing_events
        FROM token_events
        GROUP BY {group_dimensions}
        """
    )


def _ensure_column(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    existing_columns = {
        row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in existing_columns:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def _pricing_profile_payload(
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
) -> dict[str, Any]:
    return {
        "default_pricing": list(default_pricing),
        "models": {model: list(rates) for model, rates in sorted(pricing.items())},
    }


def _pricing_profile_id(
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
) -> str:
    payload = _pricing_profile_payload(pricing, default_pricing)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _ensure_pricing_profile(
    conn: sqlite3.Connection,
    *,
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
    created_at: str,
) -> str:
    profile_id = _pricing_profile_id(pricing, default_pricing)
    pricing_json = json.dumps(
        _pricing_profile_payload(pricing, default_pricing),
        sort_keys=True,
        separators=(",", ":"),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO pricing_profiles (
            pricing_profile_id, profile_name, created_at, pricing_json,
            default_non_cached_input_usd_per_million,
            default_cached_input_usd_per_million,
            default_output_usd_per_million
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            profile_id,
            "builtin",
            created_at,
            pricing_json,
            default_pricing[0],
            default_pricing[1],
            default_pricing[2],
        ),
    )
    for model, rates in pricing.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO pricing_profile_rates (
                pricing_profile_id, model, non_cached_input_usd_per_million,
                cached_input_usd_per_million, output_usd_per_million
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (profile_id, model, rates[0], rates[1], rates[2]),
        )
    return profile_id


def import_token_events_to_sqlite(
    *,
    db_path: Path,
    sessions_dir: Path,
    include_archived_sessions: bool,
    source_device: str | None,
    source_account: str | None,
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
) -> dict[str, int | str]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC).isoformat()
    imported_at = started_at

    conn = sqlite3.connect(db_path)
    try:
        _create_schema(conn)
        pricing_profile_id = _ensure_pricing_profile(
            conn,
            pricing=pricing,
            default_pricing=default_pricing,
            created_at=started_at,
        )
        pricing_backfilled_token_events = _backfill_token_event_pricing(
            conn,
            pricing=pricing,
            default_pricing=default_pricing,
            pricing_profile_id=pricing_profile_id,
        )
        completed_at = datetime.now(UTC).isoformat()
        result = _import_session_lines(
            conn,
            sessions_dir=sessions_dir,
            include_archived_sessions=include_archived_sessions,
            source_device=source_device,
            source_account=source_account,
            imported_at=imported_at,
            pricing=pricing,
            default_pricing=default_pricing,
            pricing_profile_id=pricing_profile_id,
        )
        result["pricing_backfilled_token_events"] = pricing_backfilled_token_events
        import_run_id = _insert_import_run(
            conn,
            started_at=started_at,
            completed_at=completed_at,
            sessions_dir=sessions_dir,
            include_archived_sessions=include_archived_sessions,
            source_device=source_device,
            source_account=source_account,
            pricing_profile_id=pricing_profile_id,
            result=result,
        )
        result["import_run_id"] = import_run_id
        result["pricing_profile_id"] = pricing_profile_id
        conn.commit()
        return result
    finally:
        conn.close()


def _backfill_token_event_pricing(
    conn: sqlite3.Connection,
    *,
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
    pricing_profile_id: str,
) -> int:
    rows = conn.execute(
        """
        SELECT event_id, model, input_tokens, cached_input_tokens, output_tokens
        FROM token_events
        WHERE pricing_profile_id IS NULL
           OR (
                estimated_non_cached_input_cost_usd = 0
                AND estimated_cached_input_cost_usd = 0
                AND estimated_output_cost_usd = 0
                AND estimated_cost_usd > 0
           )
        """
    ).fetchall()
    for event_id, model, input_tokens, cached_input_tokens, output_tokens in rows:
        cost = cost_breakdown_usd(
            model=model,
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            pricing=pricing,
            default_pricing=default_pricing,
        )
        conn.execute(
            """
            UPDATE token_events
            SET estimated_non_cached_input_cost_usd = ?,
                estimated_cached_input_cost_usd = ?,
                estimated_output_cost_usd = ?,
                pricing_used_default = ?,
                pricing_profile_id = ?
            WHERE event_id = ?
            """,
            (
                cost.non_cached_input_usd,
                cost.cached_input_usd,
                cost.output_usd,
                int(cost.used_default_pricing),
                pricing_profile_id,
                event_id,
            ),
        )
    return len(rows)


def _import_session_lines(
    conn: sqlite3.Connection,
    *,
    sessions_dir: Path,
    include_archived_sessions: bool,
    source_device: str | None,
    source_account: str | None,
    imported_at: str,
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
    pricing_profile_id: str,
) -> dict[str, int | str]:
    data_quality = DataQuality()
    raw_inserted = 0
    raw_skipped_duplicate = 0
    token_inserted = 0
    token_skipped_duplicate = 0
    default_pricing_token_events = 0

    for parsed_line in iter_session_lines(
        sessions_dir,
        include_archived_sessions=include_archived_sessions,
        data_quality=data_quality,
    ):
        raw_was_inserted, token_was_inserted, used_default_pricing = _import_parsed_line(
            conn,
            parsed_line=parsed_line,
            sessions_dir=sessions_dir,
            source_device=source_device,
            source_account=source_account,
            imported_at=imported_at,
            pricing=pricing,
            default_pricing=default_pricing,
            pricing_profile_id=pricing_profile_id,
        )
        if raw_was_inserted:
            raw_inserted += 1
        else:
            raw_skipped_duplicate += 1
        if used_default_pricing:
            default_pricing_token_events += 1
        if token_was_inserted is True:
            token_inserted += 1
        elif token_was_inserted is False:
            token_skipped_duplicate += 1

    return _build_import_result(
        data_quality=data_quality,
        raw_inserted=raw_inserted,
        raw_skipped_duplicate=raw_skipped_duplicate,
        token_inserted=token_inserted,
        token_skipped_duplicate=token_skipped_duplicate,
        default_pricing_token_events=default_pricing_token_events,
    )


def _import_parsed_line(
    conn: sqlite3.Connection,
    *,
    parsed_line: ParsedSessionLine,
    sessions_dir: Path,
    source_device: str | None,
    source_account: str | None,
    imported_at: str,
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
    pricing_profile_id: str,
) -> tuple[bool, bool | None, bool]:
    raw_event_hash = _normalized_hash(parsed_line.line)
    relative_session_file = _relative_session_file(sessions_dir, parsed_line.session_file)
    payload = _parse_json_dict(parsed_line.line)
    raw_was_inserted = _insert_raw_event(
        conn,
        raw_event_hash=raw_event_hash,
        source_device=source_device,
        source_account=source_account,
        session_file=relative_session_file,
        line_number=parsed_line.line_number,
        payload=payload,
        raw_json=parsed_line.line.rstrip("\n"),
        imported_at=imported_at,
    )
    if parsed_line.status != "valid" or parsed_line.event is None:
        return (raw_was_inserted, None, False)

    event = parsed_line.event
    cost = cost_breakdown_usd(
        model=event.model,
        input_tokens=event.input_tokens,
        cached_input_tokens=event.cached_input_tokens,
        output_tokens=event.output_tokens,
        pricing=pricing,
        default_pricing=default_pricing,
    )
    token_was_inserted = _insert_token_event(
        conn,
        event=event,
        cost=cost,
        source_device=source_device,
        source_account=source_account,
        session_file=relative_session_file,
        raw_event_hash=raw_event_hash,
        imported_at=imported_at,
        pricing_profile_id=pricing_profile_id,
    )
    return (raw_was_inserted, token_was_inserted, cost.used_default_pricing)


def _build_import_result(
    *,
    data_quality: DataQuality,
    raw_inserted: int,
    raw_skipped_duplicate: int,
    token_inserted: int,
    token_skipped_duplicate: int,
    default_pricing_token_events: int,
) -> dict[str, int | str]:
    return {
        "files_scanned": data_quality.files_scanned,
        "lines_scanned": data_quality.lines_scanned,
        "raw_inserted": raw_inserted,
        "raw_skipped_duplicate": raw_skipped_duplicate,
        "token_inserted": token_inserted,
        "token_skipped_duplicate": token_skipped_duplicate,
        "malformed_json_lines": data_quality.malformed_json_lines,
        "missing_payload_type": data_quality.missing_payload_type,
        "missing_token_fields": data_quality.missing_token_fields,
        "non_token_events": data_quality.non_token_events,
        "default_pricing_token_events": default_pricing_token_events,
        # backward-compat keys
        "inserted": token_inserted,
        "skipped_duplicate": token_skipped_duplicate,
    }


def _insert_import_run(
    conn: sqlite3.Connection,
    *,
    started_at: str,
    completed_at: str,
    sessions_dir: Path,
    include_archived_sessions: bool,
    source_device: str | None,
    source_account: str | None,
    pricing_profile_id: str,
    result: dict[str, int | str],
) -> str:
    import_run_id = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO import_runs (
            import_run_id, started_at, completed_at, sessions_dir,
            include_archived_sessions, source_device, source_account,
            files_scanned, lines_scanned, raw_inserted, raw_skipped_duplicate,
            token_inserted, token_skipped_duplicate, malformed_json_lines,
            missing_payload_type, missing_token_fields, non_token_events,
            default_pricing_token_events, pricing_profile_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            import_run_id,
            started_at,
            completed_at,
            str(sessions_dir),
            int(include_archived_sessions),
            source_device,
            source_account,
            result["files_scanned"],
            result["lines_scanned"],
            result["raw_inserted"],
            result["raw_skipped_duplicate"],
            result["token_inserted"],
            result["token_skipped_duplicate"],
            result["malformed_json_lines"],
            result["missing_payload_type"],
            result["missing_token_fields"],
            result["non_token_events"],
            result["default_pricing_token_events"],
            pricing_profile_id,
        ),
    )
    return import_run_id


def _insert_raw_event(
    conn: sqlite3.Connection,
    *,
    raw_event_hash: str,
    source_device: str | None,
    source_account: str | None,
    session_file: str,
    line_number: int,
    payload: dict[str, Any] | None,
    raw_json: str,
    imported_at: str,
) -> bool:
    raw_cursor = conn.execute(
        """
        INSERT OR IGNORE INTO raw_events (
            raw_event_hash, source_device, source_account, session_file,
            line_number, event_type, timestamp, raw_json, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            raw_event_hash,
            source_device,
            source_account,
            session_file,
            line_number,
            _extract_raw_event_type(payload) if payload else None,
            _extract_raw_event_timestamp(payload) if payload else None,
            raw_json,
            imported_at,
        ),
    )
    return raw_cursor.rowcount == 1


def _insert_token_event(
    conn: sqlite3.Connection,
    *,
    event: TokenUsageEvent,
    cost: CostBreakdown,
    source_device: str | None,
    source_account: str | None,
    session_file: str,
    raw_event_hash: str,
    imported_at: str,
    pricing_profile_id: str,
) -> bool:
    non_cached = event.input_tokens - event.cached_input_tokens
    repository = repository_key_from_cwd(event.workspace_cwd)
    token_cursor = conn.execute(
        """
        INSERT OR IGNORE INTO token_events (
            event_id, source_device, source_account, session_file, timestamp,
            model, reasoning_effort, workspace_cwd, repository,
            input_tokens, cached_input_tokens,
            non_cached_input_tokens, output_tokens, reasoning_output_tokens,
            total_tokens, cumulative_total_tokens,
            estimated_non_cached_input_cost_usd,
            estimated_cached_input_cost_usd,
            estimated_output_cost_usd,
            estimated_cost_usd, pricing_used_default, pricing_profile_id,
            raw_event_hash, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            source_device,
            source_account,
            session_file,
            event.timestamp.isoformat(),
            event.model,
            event.reasoning_effort,
            event.workspace_cwd,
            repository,
            event.input_tokens,
            event.cached_input_tokens,
            non_cached,
            event.output_tokens,
            event.reasoning_output_tokens,
            event.total_tokens,
            event.cumulative_total_tokens,
            cost.non_cached_input_usd,
            cost.cached_input_usd,
            cost.output_usd,
            cost.total_usd,
            int(cost.used_default_pricing),
            pricing_profile_id,
            raw_event_hash,
            imported_at,
        ),
    )
    return token_cursor.rowcount == 1
