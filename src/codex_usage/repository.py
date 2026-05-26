from __future__ import annotations


def repository_key_from_cwd(cwd: str | None) -> str:
    if cwd is None:
        return "unknown"
    trimmed = cwd.strip().rstrip("\\/")
    if not trimmed:
        return "unknown"
    normalized = trimmed.replace("\\", "/")
    return normalized.split("/")[-1] or "unknown"
