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


def _iter_jsonl_files(base_dir: Path) -> Iterator[Path]:
    if not base_dir.exists():
        return
    for path in sorted(base_dir.rglob("*.jsonl")):
        if path.is_file():
            yield path


def iter_session_files(
    base_dir: Path = DEFAULT_SESSIONS_DIR,
    include_archived_sessions: bool = False,
) -> Iterator[Path]:
    seen: set[Path] = set()
    for path in _iter_jsonl_files(base_dir):
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            yield path

    if not include_archived_sessions:
        return

    archived_dir = base_dir.parent / "archived_sessions"
    for path in _iter_jsonl_files(archived_dir):
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            yield path
