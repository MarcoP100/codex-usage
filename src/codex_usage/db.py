from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codex_usage.models import TokenUsageEvent
from codex_usage.parser import parse_token_usage_event_with_status, parse_turn_context_metadata
from codex_usage.scanner import iter_session_files


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


def _cost_components_usd(
    model: str | None,
    input_tokens: int,
    cached_input_tokens: int,
    output_tokens: int,
    pricing: dict[str, tuple[float, float, float]],
    default_pricing: tuple[float, float, float],
) -> tuple[float, float, float]:
    model_key = (model or "").strip().lower()
    non_cached_rate, cached_rate, output_rate = pricing.get(model_key, default_pricing)
    non_cached_input = input_tokens - cached_input_tokens
    non_cached_input_cost = (non_cached_input / 1_000_000) * non_cached_rate
    cached_input_cost = (cached_input_tokens / 1_000_000) * cached_rate
    output_cost = (output_tokens / 1_000_000) * output_rate
    return (non_cached_input_cost, cached_input_cost, output_cost)


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
        raw_inserted = 0
        raw_skipped_duplicate = 0
        token_inserted = 0
        token_skipped_duplicate = 0
        files_scanned = 0
        lines_scanned = 0

        for session_file in iter_session_files(
            sessions_dir,
            include_archived_sessions=include_archived_sessions,
        ):
            files_scanned += 1
            current_model: str | None = None
            current_effort: str | None = None
            relative_session_file = _relative_session_file(sessions_dir, session_file)

            with session_file.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    lines_scanned += 1
                    raw_event_hash = _normalized_hash(line)

                    payload = _parse_json_dict(line)
                    raw_timestamp = _extract_raw_event_timestamp(payload) if payload else None
                    raw_event_type = _extract_raw_event_type(payload) if payload else None

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
                            relative_session_file,
                            line_number,
                            raw_event_type,
                            raw_timestamp,
                            line.rstrip("\n"),
                            imported_at,
                        ),
                    )
                    if raw_cursor.rowcount == 1:
                        raw_inserted += 1
                    else:
                        raw_skipped_duplicate += 1

                    turn_model, turn_effort = parse_turn_context_metadata(line)
                    if turn_model:
                        current_model = turn_model
                    if turn_effort:
                        current_effort = turn_effort

                    status, event = parse_token_usage_event_with_status(line)
                    if status != "valid" or event is None:
                        continue

                    if event.model is None and current_model is not None:
                        event = TokenUsageEvent(
                            timestamp=event.timestamp,
                            input_tokens=event.input_tokens,
                            cached_input_tokens=event.cached_input_tokens,
                            output_tokens=event.output_tokens,
                            reasoning_output_tokens=event.reasoning_output_tokens,
                            total_tokens=event.total_tokens,
                            cumulative_total_tokens=event.cumulative_total_tokens,
                            model=current_model,
                            reasoning_effort=event.reasoning_effort or current_effort,
                        )
                    elif event.reasoning_effort is None and current_effort is not None:
                        event = TokenUsageEvent(
                            timestamp=event.timestamp,
                            input_tokens=event.input_tokens,
                            cached_input_tokens=event.cached_input_tokens,
                            output_tokens=event.output_tokens,
                            reasoning_output_tokens=event.reasoning_output_tokens,
                            total_tokens=event.total_tokens,
                            cumulative_total_tokens=event.cumulative_total_tokens,
                            model=event.model,
                            reasoning_effort=current_effort,
                        )

                    non_cached = event.input_tokens - event.cached_input_tokens
                    non_cached_cost, cached_cost, output_cost = _cost_components_usd(
                        event.model,
                        event.input_tokens,
                        event.cached_input_tokens,
                        event.output_tokens,
                        pricing,
                        default_pricing,
                    )
                    estimated_total_cost = non_cached_cost + cached_cost + output_cost

                    token_cursor = conn.execute(
                        """
                        INSERT OR IGNORE INTO token_events (
                            event_id, source_device, source_account, session_file, timestamp,
                            model, reasoning_effort, input_tokens, cached_input_tokens,
                            non_cached_input_tokens, output_tokens, reasoning_output_tokens,
                            total_tokens, estimated_cost_usd, raw_event_hash, imported_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            source_device,
                            source_account,
                            relative_session_file,
                            event.timestamp.isoformat(),
                            event.model,
                            event.reasoning_effort,
                            event.input_tokens,
                            event.cached_input_tokens,
                            non_cached,
                            event.output_tokens,
                            event.reasoning_output_tokens,
                            event.total_tokens,
                            estimated_total_cost,
                            raw_event_hash,
                            imported_at,
                        ),
                    )
                    if token_cursor.rowcount == 1:
                        token_inserted += 1
                    else:
                        token_skipped_duplicate += 1

        conn.commit()
        return {
            "files_scanned": files_scanned,
            "lines_scanned": lines_scanned,
            "raw_inserted": raw_inserted,
            "raw_skipped_duplicate": raw_skipped_duplicate,
            "token_inserted": token_inserted,
            "token_skipped_duplicate": token_skipped_duplicate,
            # backward-compat keys
            "inserted": token_inserted,
            "skipped_duplicate": token_skipped_duplicate,
        }
    finally:
        conn.close()
