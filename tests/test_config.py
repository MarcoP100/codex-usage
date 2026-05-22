from __future__ import annotations

from pathlib import Path

from codex_usage.config import load_app_config


def test_load_app_config_defaults_when_missing(tmp_path: Path) -> None:
    cfg = load_app_config(tmp_path / "missing.toml")
    assert cfg.sqlite_db_path == Path("codex_usage.db")
    assert cfg.include_archived_sessions is False


def test_load_app_config_reads_values(tmp_path: Path) -> None:
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        "\n".join(
            [
                "[app]",
                'sessions_dir = "C:/Users/test/.codex-copy/sessions"',
                'sqlite_db_path = "data/usage.db"',
                "include_archived_sessions = true",
                'source_device = "pc-1"',
                'source_account = "acc-1"',
            ]
        ),
        encoding="utf-8",
    )

    cfg = load_app_config(cfg_path)

    assert cfg.sessions_dir == Path("C:/Users/test/.codex-copy/sessions")
    assert cfg.sqlite_db_path == Path("data/usage.db")
    assert cfg.include_archived_sessions is True
    assert cfg.source_device == "pc-1"
    assert cfg.source_account == "acc-1"
