from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .path_utils import validate_path_component

LECTURE_REGISTRY_FILE = "lecture_registry.json"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class LectureEntry:
    lec_id: str
    paths: list[Path]
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "lec_id": self.lec_id,
            "paths": [str(path) for path in self.paths],
            "enabled": self.enabled,
        }


class LectureRegistryService:
    def registry_path(self, *, project_root: Path | str) -> Path:
        root = Path(project_root).expanduser().resolve()
        return root / "state" / LECTURE_REGISTRY_FILE

    def list_lectures(self, *, project_root: Path | str) -> list[LectureEntry]:
        payload = self._load_registry_payload(project_root=project_root)
        lectures_raw = payload.get("lectures")
        if not isinstance(lectures_raw, dict):
            return []

        results: list[LectureEntry] = []
        for raw_lec_id, raw_entry in sorted(lectures_raw.items(), key=lambda item: str(item[0])):
            lec_id = str(raw_lec_id)
            if not isinstance(raw_entry, dict):
                continue
            raw_paths = raw_entry.get("paths")
            if not isinstance(raw_paths, list):
                continue
            paths: list[Path] = []
            for raw_path in raw_paths:
                if not isinstance(raw_path, str) or not raw_path.strip():
                    continue
                path = Path(raw_path).expanduser().resolve()
                paths.append(path)
            if not paths:
                continue
            enabled = bool(raw_entry.get("enabled", True))
            results.append(LectureEntry(lec_id=lec_id, paths=paths, enabled=enabled))
        return results

    def upsert_lecture(
        self,
        *,
        project_root: Path | str,
        lec_id: str,
        paths: list[Path | str],
        enabled: bool = True,
    ) -> LectureEntry:
        lec_key = validate_path_component(lec_id, field_name="lec_id")
        normalized_paths = self._normalize_existing_paths(paths)
        payload = self._load_registry_payload(project_root=project_root)
        lectures = payload.setdefault("lectures", {})
        if not isinstance(lectures, dict):
            lectures = {}
            payload["lectures"] = lectures
        lectures[lec_key] = {
            "paths": [str(path) for path in normalized_paths],
            "enabled": bool(enabled),
        }
        payload["updated_at"] = _now_iso()
        self._write_registry_payload(project_root=project_root, payload=payload)
        return LectureEntry(lec_id=lec_key, paths=normalized_paths, enabled=bool(enabled))

    def remove_lecture(self, *, project_root: Path | str, lec_id: str) -> bool:
        lec_key = validate_path_component(lec_id, field_name="lec_id")
        payload = self._load_registry_payload(project_root=project_root)
        lectures = payload.get("lectures")
        if not isinstance(lectures, dict):
            return False
        if lec_key not in lectures:
            return False
        del lectures[lec_key]
        payload["updated_at"] = _now_iso()
        self._write_registry_payload(project_root=project_root, payload=payload)
        return True

    def resolve_paths(
        self,
        *,
        project_root: Path | str,
        target_lectures: list[str] | None = None,
    ) -> dict[str, list[Path]]:
        entries = self.list_lectures(project_root=project_root)
        enabled_entries = [entry for entry in entries if entry.enabled]
        if not enabled_entries:
            raise ValueError("未配置可用讲次，请先在讲次配置中添加 lec_id 与资料路径")

        by_id = {entry.lec_id: entry for entry in enabled_entries}
        if target_lectures:
            normalized_targets = [validate_path_component(item, field_name="target_lecture") for item in target_lectures]
            missing = [lec_id for lec_id in normalized_targets if lec_id not in by_id]
            if missing:
                raise ValueError(f"目标讲次未注册: {', '.join(missing)}")
            selected_ids = normalized_targets
        else:
            selected_ids = sorted(by_id.keys())

        return {lec_id: list(by_id[lec_id].paths) for lec_id in selected_ids}

    def _normalize_existing_paths(self, paths: list[Path | str]) -> list[Path]:
        if not paths:
            raise ValueError("paths cannot be empty")
        normalized: list[Path] = []
        seen: set[str] = set()
        for raw in paths:
            path = Path(raw).expanduser().resolve()
            if not path.exists():
                raise FileNotFoundError(f"path not found: {path}")
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(path)
        if not normalized:
            raise ValueError("paths cannot be empty")
        return normalized

    def _load_registry_payload(self, *, project_root: Path | str) -> dict[str, Any]:
        path = self.registry_path(project_root=project_root)
        payload = self._read_json(path)
        if payload:
            payload.setdefault("version", 1)
            payload.setdefault("updated_at", _now_iso())
            payload.setdefault("lectures", {})
            return payload
        return {
            "version": 1,
            "updated_at": _now_iso(),
            "lectures": {},
        }

    def _write_registry_payload(self, *, project_root: Path | str, payload: dict[str, Any]) -> None:
        path = self.registry_path(project_root=project_root)
        self._write_json(path, payload)

    def _read_json(self, path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as fp:
                payload = json.load(fp)
        except (OSError, json.JSONDecodeError):
            return {}
        if isinstance(payload, dict):
            return payload
        return {}

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
