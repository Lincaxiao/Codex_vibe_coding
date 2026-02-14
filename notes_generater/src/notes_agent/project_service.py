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

        if config_path.exists() and not allow_existing:
            raise FileExistsError(f"project already exists: {config.project_root}")

        self._ensure_scaffold(config.project_root, config.notes_root)
        self._write_project_config(config)
        self._initialize_state(config.project_root, config.course_id)
        return config

    def load_project_config(self, project_root: Path | str) -> ProjectConfig:
        root = Path(project_root).expanduser().resolve()
        data = self._read_json(root / PROJECT_CONFIG_FILE)
        return ProjectConfig.from_dict(data)

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
            workspace_root=updated.workspace_root.resolve() if updated.workspace_root else None,
            project_root=updated.project_root.resolve(),
            notes_root=updated.notes_root.resolve(),
        )
        self._write_project_config(updated)
        return updated

    def discover_workspace_projects(self, workspace_root: Path | str) -> list[ProjectConfig]:
        workspace = Path(workspace_root).expanduser().resolve()
        projects_dir = workspace / "projects"
        if not projects_dir.exists():
            return []

        results: list[ProjectConfig] = []
        for config_path in sorted(projects_dir.glob(f"*/{PROJECT_CONFIG_FILE}")):
            results.append(ProjectConfig.from_dict(self._read_json(config_path)))
        return results

    def _resolve_config(self, request: CreateProjectRequest) -> ProjectConfig:
        course_id = slugify_course_id(request.course_id)

        workspace_root: Path | None = None
        if request.workspace_root:
            workspace_root = request.workspace_root.expanduser().resolve()

        project_root = self._resolve_root(
            explicit_root=request.project_root,
            workspace_root=workspace_root,
            default_child=f"projects/{course_id}",
            root_name="project_root",
        )
        notes_root = self._resolve_root(
            explicit_root=request.notes_root,
            workspace_root=workspace_root,
            default_child=f"notes/{course_id}",
            root_name="notes_root",
        )

        return ProjectConfig(
            workspace_root=workspace_root,
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

    def _resolve_root(
        self,
        *,
        explicit_root: Path | None,
        workspace_root: Path | None,
        default_child: str,
        root_name: str,
    ) -> Path:
        if explicit_root:
            return explicit_root.expanduser().resolve()
        if workspace_root:
            return (workspace_root / default_child).resolve()
        raise ValueError(f"{root_name} is required when workspace_root is not provided")

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

        session_payload = {
            "course_id": course_id,
            "status": "idle",
            "current_run_id": None,
            "created_at": now,
            "updated_at": now,
        }
        round_status_payload = {
            "round0": "pending",
            "round1": "pending",
            "round2": "pending",
            "round3": "pending",
            "final": "pending",
        }

        state_dir = project_root / STATE_DIR_NAME
        self._write_json(state_dir / "session.json", session_payload)
        self._write_json(state_dir / "round_status.json", round_status_payload)

    def _write_project_config(self, config: ProjectConfig) -> None:
        self._write_json(config.project_root / PROJECT_CONFIG_FILE, config.to_dict())

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
