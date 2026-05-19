from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Iterator


def _resolve_default_sessions_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "sessions"

    home = Path.home()
    system_name = platform.system().lower()
    if system_name == "windows":
        return home / ".codex" / "sessions"
    if system_name in {"linux", "darwin"}:
        return home / ".codex" / "sessions"
    return Path("~/.codex/sessions").expanduser()


DEFAULT_SESSIONS_DIR = _resolve_default_sessions_dir()


def iter_session_files(base_dir: Path = DEFAULT_SESSIONS_DIR) -> Iterator[Path]:
    if not base_dir.exists():
        return
    for path in sorted(base_dir.rglob("*.jsonl")):
        if path.is_file():
            yield path
