from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

from codex_usage.scanner import DEFAULT_SESSIONS_DIR


@dataclass(frozen=True)
class AppConfig:
    sessions_dir: Path
    sqlite_db_path: Path
    include_archived_sessions: bool = False
    source_device: str | None = None
    source_account: str | None = None


def _read_toml(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    data = tomllib.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        return {}
    return data


def load_app_config(path: Path | None) -> AppConfig:
    default = AppConfig(
        sessions_dir=DEFAULT_SESSIONS_DIR,
        sqlite_db_path=Path("codex_usage.db"),
        include_archived_sessions=False,
        source_device=None,
        source_account=None,
    )
    if path is None:
        return default
    if not path.exists():
        return default

    data = _read_toml(path)
    app = data.get("app")
    if not isinstance(app, dict):
        return default

    sessions_dir_raw = app.get("sessions_dir")
    sqlite_db_path_raw = app.get("sqlite_db_path")
    include_archived_raw = app.get("include_archived_sessions")
    source_device_raw = app.get("source_device")
    source_account_raw = app.get("source_account")

    sessions_dir = (
        Path(sessions_dir_raw).expanduser()
        if isinstance(sessions_dir_raw, str) and sessions_dir_raw.strip()
        else default.sessions_dir
    )
    sqlite_db_path = (
        Path(sqlite_db_path_raw).expanduser()
        if isinstance(sqlite_db_path_raw, str) and sqlite_db_path_raw.strip()
        else default.sqlite_db_path
    )
    source_device = source_device_raw if isinstance(source_device_raw, str) and source_device_raw else None
    source_account = source_account_raw if isinstance(source_account_raw, str) and source_account_raw else None
    include_archived_sessions = bool(include_archived_raw) if isinstance(include_archived_raw, bool) else default.include_archived_sessions

    return AppConfig(
        sessions_dir=sessions_dir,
        sqlite_db_path=sqlite_db_path,
        include_archived_sessions=include_archived_sessions,
        source_device=source_device,
        source_account=source_account,
    )
