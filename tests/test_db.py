from __future__ import annotations

import sqlite3
from pathlib import Path

from codex_usage.db import import_token_events_to_sqlite


MODEL_PRICING_USD_PER_MILLION = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
    "gpt-5.3-codex": (1.75, 0.175, 14.0),
}


def test_import_sqlite_is_idempotent(tmp_path: Path) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-test.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":110}}}}',
                '{"timestamp":"2026-05-20T10:00:02Z","type":"event_msg","payload":{"type":"task_started"}}',
                "{bad json",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    db_path = tmp_path / "usage.db"
    first = import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device="laptop-1",
        source_account="me@example.com",
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )
    second = import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device="laptop-1",
        source_account="me@example.com",
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )

    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped_duplicate"] == 1
    assert first["raw_inserted"] == 4
    assert second["raw_inserted"] == 0

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT source_device, source_account, model, reasoning_effort, non_cached_input_tokens FROM token_events"
        ).fetchone()
        raw_count = conn.execute("SELECT COUNT(*) FROM raw_events").fetchone()
        malformed_count = conn.execute(
            "SELECT COUNT(*) FROM raw_events WHERE event_type IS NULL"
        ).fetchone()
    finally:
        conn.close()

    assert row == ("laptop-1", "me@example.com", "gpt-5.4", "medium", 80)
    assert raw_count == (4,)
    assert malformed_count == (1,)
