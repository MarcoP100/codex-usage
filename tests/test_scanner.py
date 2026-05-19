from __future__ import annotations

from pathlib import Path

from codex_usage import scanner


def test_default_sessions_dir_uses_codex_home_env(monkeypatch) -> None:
    monkeypatch.setenv("CODEX_HOME", "/tmp/custom-codex")
    path = scanner._resolve_default_sessions_dir()
    assert path == Path("/tmp/custom-codex") / "sessions"


def test_default_sessions_dir_windows(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(scanner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(scanner.Path, "home", lambda: Path("C:/Users/tester"))

    path = scanner._resolve_default_sessions_dir()

    assert path == Path("C:/Users/tester/.codex/sessions")


def test_default_sessions_dir_linux(monkeypatch) -> None:
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(scanner.platform, "system", lambda: "Linux")
    monkeypatch.setattr(scanner.Path, "home", lambda: Path("/home/tester"))

    path = scanner._resolve_default_sessions_dir()

    assert path == Path("/home/tester/.codex/sessions")
