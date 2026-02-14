from __future__ import annotations

from pathlib import Path


def validate_path_component(value: str, *, field_name: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{field_name} cannot be empty")
    if "\\" in trimmed:
        raise ValueError(f"{field_name} cannot contain path separators")
    path = Path(trimmed)
    if len(path.parts) != 1:
        raise ValueError(f"{field_name} must be a single path component")
    component = path.parts[0]
    if component in {".", ".."}:
        raise ValueError(f"{field_name} cannot be '.' or '..'")
    return component


def resolve_within_root(*, root: Path, relative_path: str) -> Path | None:
    if "\\" in relative_path:
        return None
    rel = Path(relative_path)
    if rel.is_absolute():
        return None
    if any(part in {"", ".", ".."} for part in rel.parts):
        return None
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate
