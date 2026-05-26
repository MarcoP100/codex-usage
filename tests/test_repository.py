from __future__ import annotations

from codex_usage.repository import repository_key_from_cwd


def test_repository_key_from_cwd_handles_missing_values() -> None:
    assert repository_key_from_cwd(None) == "unknown"
    assert repository_key_from_cwd("") == "unknown"
    assert repository_key_from_cwd("   ") == "unknown"


def test_repository_key_from_cwd_normalizes_windows_and_unix_paths() -> None:
    assert repository_key_from_cwd("C:\\Progetti\\personal\\codex-usage\\") == "codex-usage"
    assert repository_key_from_cwd("/home/marco/projects/codex-usage/") == "codex-usage"
