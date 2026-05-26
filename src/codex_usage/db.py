from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codex_usage.ingestion import DataQuality, iter_session_lines
from codex_usage.models import TokenUsageEvent
from codex_usage.pricing import cost_breakdown_usd
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
            estimated_cost_usd REAL NOT NULL,
            raw_event_hash TEXT NOT NULL UNIQUE,
            imported_at TEXT NOT NULL,
            FOREIGN KEY(raw_event_hash) REFERENCES raw_events(raw_event_hash)
        )
        """
    )
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
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_token_events_repository ON token_events(repository)"
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


def import_token_events_to_sqlite(
    *,
    db_path: Path,
    sessions_dir: Path,
    include_archived_sessions: bool,
    source_device: str | None,
    source_account: str | None,
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    imported_at = datetime.now(UTC).isoformat()

    conn = sqlite3.connect(db_path)
    try:
        _create_schema(conn)
        data_quality = DataQuality()
        raw_inserted = 0
        raw_skipped_duplicate = 0
        token_inserted = 0
        token_skipped_duplicate = 0

        for parsed_line in iter_session_lines(
            sessions_dir,
            include_archived_sessions=include_archived_sessions,
            data_quality=data_quality,
        ):
            raw_event_hash = _normalized_hash(parsed_line.line)
            relative_session_file = _relative_session_file(
                sessions_dir,
                parsed_line.session_file,
            )
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
            if raw_was_inserted:
                raw_inserted += 1
            else:
                raw_skipped_duplicate += 1

            if parsed_line.status != "valid" or parsed_line.event is None:
                continue

            event = parsed_line.event
            token_was_inserted = _insert_token_event(
                conn,
                event=event,
                source_device=source_device,
                source_account=source_account,
                session_file=relative_session_file,
                raw_event_hash=raw_event_hash,
                imported_at=imported_at,
                pricing=pricing,
                default_pricing=default_pricing,
            )
            if token_was_inserted:
                token_inserted += 1
            else:
                token_skipped_duplicate += 1

        conn.commit()
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
            # backward-compat keys
            "inserted": token_inserted,
            "skipped_duplicate": token_skipped_duplicate,
        }
    finally:
        conn.close()


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
    source_device: str | None,
    source_account: str | None,
    session_file: str,
    raw_event_hash: str,
    imported_at: str,
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
) -> bool:
    non_cached = event.input_tokens - event.cached_input_tokens
    repository = repository_key_from_cwd(event.workspace_cwd)
    cost = cost_breakdown_usd(
        model=event.model,
        input_tokens=event.input_tokens,
        cached_input_tokens=event.cached_input_tokens,
        output_tokens=event.output_tokens,
        pricing=pricing,
        default_pricing=default_pricing,
    )
    token_cursor = conn.execute(
        """
        INSERT OR IGNORE INTO token_events (
            event_id, source_device, source_account, session_file, timestamp,
            model, reasoning_effort, workspace_cwd, repository,
            input_tokens, cached_input_tokens,
            non_cached_input_tokens, output_tokens, reasoning_output_tokens,
            total_tokens, estimated_cost_usd, raw_event_hash, imported_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            cost.total_usd,
            raw_event_hash,
            imported_at,
        ),
    )
    return token_cursor.rowcount == 1
