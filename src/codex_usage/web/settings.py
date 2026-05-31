from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from codex_usage.config import load_app_config


DB_PATH_ENV = "CODEX_USAGE_DB_PATH"
CONFIG_PATH_ENV = "CODEX_USAGE_CONFIG"
DEFAULT_CONFIG_PATH = Path("config.toml")


@dataclass(frozen=True, slots=True)
class WebSettings:
    db_path: Path
    db_path_source: str
    config_path: Path | None

    @property
    def db_exists(self) -> bool:
        return self.db_path.exists()


def _path_from_env(environ: Mapping[str, str], key: str) -> Path | None:
    raw = environ.get(key)
    if raw is None or not raw.strip():
        return None
    return Path(raw).expanduser()


def load_web_settings(environ: Mapping[str, str] | None = None) -> WebSettings:
    env = os.environ if environ is None else environ

    env_db_path = _path_from_env(env, DB_PATH_ENV)
    env_config_path = _path_from_env(env, CONFIG_PATH_ENV)
    config_path = env_config_path or DEFAULT_CONFIG_PATH

    if env_db_path is not None:
        return WebSettings(
            db_path=env_db_path,
            db_path_source=DB_PATH_ENV,
            config_path=config_path,
        )

    app_config = load_app_config(config_path if config_path.exists() else None)
    source = str(config_path) if config_path.exists() else "default"
    return WebSettings(
        db_path=app_config.sqlite_db_path,
        db_path_source=source,
        config_path=config_path if config_path.exists() or env_config_path is not None else None,
    )
