from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import CreateProjectRequest, ProjectConfig

PROJECT_CONFIG_FILE = "project.yaml"
STATE_DIR_NAME = "state"
RUNS_DIR_NAME = "runs"
ARTIFACTS_DIR_NAME = "artifacts"
PROJECT_REL_PATH = Path(".notes_agent") / "project"
NOTES_REL_PATH = Path("notes")


def slugify_course_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    normalized = re.sub(r"-{2,}", "-", normalized).strip("-")
    if not normalized:
        raise ValueError("course_id must contain at least one alphanumeric character")
    return normalized


class ProjectService:
    def create_project(
        self,
        request: CreateProjectRequest,
        *,
        allow_existing: bool = False,
    ) -> ProjectConfig:
        config = self._resolve_config(request)
        config_path = config.project_root / PROJECT_CONFIG_FILE
        project_exists = config_path.exists()

        if project_exists and not allow_existing:
            raise FileExistsError(f"project already exists: {config.project_root}")

        self._ensure_scaffold(config.project_root, config.notes_root)
        self._write_project_config(config)
        if project_exists:
            self._ensure_state_files(config.project_root, config.course_id)
        else:
            self._initialize_state(config.project_root, config.course_id)
        return config

    def load_project_config(self, project_root: Path | str) -> ProjectConfig:
        root = Path(project_root).expanduser().resolve()
        data = self._read_json(root / PROJECT_CONFIG_FILE)
        try:
            config = ProjectConfig.from_dict(data)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid project config: {root / PROJECT_CONFIG_FILE}") from exc

        return replace(
            config,
            course_root=config.course_root.expanduser().resolve(),
            project_root=config.project_root.expanduser().resolve(),
            notes_root=config.notes_root.expanduser().resolve(),
        )

    def load_project_by_course_root(self, course_root: Path | str) -> ProjectConfig:
        course = Path(course_root).expanduser().resolve()
        return self.load_project_config(course / PROJECT_REL_PATH)

    def update_project_config(
        self,
        project_root: Path | str,
        **updates: Any,
    ) -> ProjectConfig:
        existing = self.load_project_config(project_root)
        merged = existing.to_dict()
        merged.update(updates)
        updated = ProjectConfig.from_dict(merged)

        # Keep roots normalized to absolute paths.
        updated = replace(
            updated,
            course_root=updated.course_root.resolve(),
            project_root=updated.project_root.resolve(),
            notes_root=updated.notes_root.resolve(),
        )
        self._write_project_config(updated)
        return updated

    def _resolve_config(self, request: CreateProjectRequest) -> ProjectConfig:
        course_root = request.course_root.expanduser().resolve()
        course_id_raw = request.course_id if request.course_id else course_root.name
        course_id = slugify_course_id(course_id_raw)
        project_root = (course_root / PROJECT_REL_PATH).resolve()
        notes_root = (course_root / NOTES_REL_PATH).resolve()

        return ProjectConfig(
            course_root=course_root,
            course_id=course_id,
            project_root=project_root,
            notes_root=notes_root,
            language=request.language,
            review_granularity=request.review_granularity,
            human_review_timing=request.human_review_timing,
            pause_after_each_round=request.pause_after_each_round,
            max_changed_lines=request.max_changed_lines,
            max_changed_files=request.max_changed_files,
            network_mode=request.network_mode,
        )

    def _ensure_scaffold(self, project_root: Path, notes_root: Path) -> None:
        for path in (
            project_root,
            project_root / STATE_DIR_NAME,
            project_root / RUNS_DIR_NAME,
            project_root / ARTIFACTS_DIR_NAME,
            notes_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _initialize_state(self, project_root: Path, course_id: str) -> None:
        now = datetime.now(tz=timezone.utc).isoformat()
        session_payload = self._default_session_payload(course_id=course_id, now=now)
        round_status_payload = self._default_round_status_payload()

        state_dir = project_root / STATE_DIR_NAME
        self._write_json(state_dir / "session.json", session_payload)
        self._write_json(state_dir / "round_status.json", round_status_payload)

    def _ensure_state_files(self, project_root: Path, course_id: str) -> None:
        state_dir = project_root / STATE_DIR_NAME
        now = datetime.now(tz=timezone.utc).isoformat()
        session_path = state_dir / "session.json"
        round_status_path = state_dir / "round_status.json"

        if not session_path.exists():
            self._write_json(
                session_path,
                self._default_session_payload(course_id=course_id, now=now),
            )
        if not round_status_path.exists():
            self._write_json(round_status_path, self._default_round_status_payload())

    def _default_session_payload(self, *, course_id: str, now: str) -> dict[str, Any]:
        return {
            "course_id": course_id,
            "status": "idle",
            "current_run_id": None,
            "created_at": now,
            "updated_at": now,
        }

    def _default_round_status_payload(self) -> dict[str, str]:
        return {
            "round0": "pending",
            "round1": "pending",
            "round2": "pending",
            "round3": "pending",
            "final": "pending",
        }

    def _write_project_config(self, config: ProjectConfig) -> None:
        self._write_json(config.project_root / PROJECT_CONFIG_FILE, config.to_dict())

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
