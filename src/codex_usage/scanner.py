from __future__ import annotations

from pathlib import Path
from typing import Iterator

DEFAULT_SESSIONS_DIR = Path("~/.codex/sessions").expanduser()


def iter_session_files(base_dir: Path = DEFAULT_SESSIONS_DIR) -> Iterator[Path]:
    if not base_dir.exists():
        return
    for path in sorted(base_dir.rglob("*.jsonl")):
        if path.is_file():
            yield path
