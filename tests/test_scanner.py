from __future__ import annotations

from pathlib import Path

from codex_usage.scanner import iter_session_files


def test_iter_session_files_include_archived(tmp_path: Path) -> None:
    sessions = tmp_path / "sessions"
    archived = tmp_path / "archived_sessions"
    sessions.mkdir()
    archived.mkdir()

    active_file = sessions / "active.jsonl"
    archived_file = archived / "archived.jsonl"
    active_file.write_text("{}\n", encoding="utf-8")
    archived_file.write_text("{}\n", encoding="utf-8")

    active_only = list(iter_session_files(sessions, include_archived_sessions=False))
    with_archived = list(iter_session_files(sessions, include_archived_sessions=True))

    assert active_file in active_only
    assert archived_file not in active_only
    assert active_file in with_archived
    assert archived_file in with_archived
