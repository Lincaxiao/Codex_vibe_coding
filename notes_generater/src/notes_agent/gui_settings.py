from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SETTINGS_DIR_NAME = ".notes_agent_gui"
SETTINGS_FILE_NAME = "settings.json"


def _as_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    return default


@dataclass(frozen=True)
class GuiSettings:
    workspace_root: str = ""
    course_id: str = ""
    target_lecture: str = ""
    from_round: str = "round0"
    to_round: str = "round1"
    max_changed_lines: int = 500
    max_changed_files: int = 20
    pause_after_each_round: bool = False
    search_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "course_id": self.course_id,
            "target_lecture": self.target_lecture,
            "from_round": self.from_round,
            "to_round": self.to_round,
            "max_changed_lines": self.max_changed_lines,
            "max_changed_files": self.max_changed_files,
            "pause_after_each_round": self.pause_after_each_round,
            "search_enabled": self.search_enabled,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> GuiSettings:
        return cls(
            workspace_root=str(payload.get("workspace_root", "")),
            course_id=str(payload.get("course_id", "")),
            target_lecture=str(payload.get("target_lecture", "")),
            from_round=str(payload.get("from_round", "round0")),
            to_round=str(payload.get("to_round", "round1")),
            max_changed_lines=int(payload.get("max_changed_lines", 500)),
            max_changed_files=int(payload.get("max_changed_files", 20)),
            pause_after_each_round=_as_bool(payload.get("pause_after_each_round", False), False),
            search_enabled=_as_bool(payload.get("search_enabled", False), False),
        )


def default_settings_path(home: Path | None = None) -> Path:
    base = home if home is not None else Path.home()
    return base / SETTINGS_DIR_NAME / SETTINGS_FILE_NAME


def load_gui_settings(path: Path | None = None) -> GuiSettings:
    target = path or default_settings_path()
    if not target.exists():
        return GuiSettings()
    with target.open("r", encoding="utf-8") as fp:
        payload = json.load(fp)
    return GuiSettings.from_dict(payload)


def save_gui_settings(settings: GuiSettings, path: Path | None = None) -> Path:
    target = path or default_settings_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_suffix(target.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8") as fp:
        json.dump(settings.to_dict(), fp, indent=2, ensure_ascii=False, sort_keys=True)
        fp.write("\n")
    temp_path.replace(target)
    return target
