from __future__ import annotations

from pathlib import Path

from codex_usage.cli import cmd_report_sqlite
from codex_usage.db import import_token_events_to_sqlite


MODEL_PRICING_USD_PER_MILLION = {
    "gpt-5.5": (5.0, 0.5, 30.0),
    "gpt-5.4": (2.5, 0.25, 15.0),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
    "gpt-5.3-codex": (1.75, 0.175, 14.0),
}


def test_report_sqlite_reads_imported_usage(tmp_path: Path, capsys) -> None:
    sessions_dir = tmp_path / "sessions"
    day_dir = sessions_dir / "2026" / "05" / "20"
    day_dir.mkdir(parents=True)
    session_file = day_dir / "rollout-report.jsonl"
    session_file.write_text(
        "\n".join(
            [
                '{"timestamp":"2026-05-20T10:00:00Z","type":"turn_context","payload":{"model":"gpt-5.4","effort":"medium","cwd":"C:/Progetti/personal/codex-usage"}}',
                '{"timestamp":"2026-05-20T10:00:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":100,"cached_input_tokens":20,"output_tokens":10,"reasoning_output_tokens":5,"total_tokens":115}}}}',
                '{"timestamp":"2026-05-20T10:05:00Z","type":"turn_context","payload":{"model":"gpt-5.4-mini","effort":"low","cwd":"C:/Progetti/personal/other-tool"}}',
                '{"timestamp":"2026-05-20T10:05:01Z","type":"event_msg","payload":{"type":"token_count","info":{"last_token_usage":{"input_tokens":50,"cached_input_tokens":10,"output_tokens":8,"reasoning_output_tokens":2,"total_tokens":60}}}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    db_path = tmp_path / "usage.db"
    report_path = tmp_path / "report.txt"

    import_token_events_to_sqlite(
        db_path=db_path,
        sessions_dir=sessions_dir,
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
        pricing=MODEL_PRICING_USD_PER_MILLION,
        default_pricing=MODEL_PRICING_USD_PER_MILLION["gpt-5.5"],
    )

    exit_code = cmd_report_sqlite(db_path=db_path, save_report=report_path)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SQLite DB:" in output
    assert "Events:                  2" in output
    assert "Usage tokens estimate:   175" in output
    assert "Cache ratio:             20.0%" in output
    assert "codex-usage: events=1" in output
    assert "other-tool: events=1" in output
    assert "gpt-5.4: events=1" in output
    assert "gpt-5.4-mini: events=1" in output
    assert "2026-05: events=2" in output
    assert "2026-05-20: events=2" in output
    assert report_path.read_text(encoding="utf-8") == output
