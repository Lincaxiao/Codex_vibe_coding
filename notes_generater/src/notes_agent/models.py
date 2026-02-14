from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ReviewGranularity = Literal["section", "lecture"]


@dataclass(frozen=True)
class CreateProjectRequest:
    course_id: str
    workspace_root: Path | None = None
    project_root: Path | None = None
    notes_root: Path | None = None
    review_granularity: ReviewGranularity = "lecture"
    language: str = "zh-CN"
    human_review_timing: str = "final_only"
    pause_after_each_round: bool = False
    max_changed_lines: int = 500
    max_changed_files: int = 20
    network_mode: str = "disabled_by_default"


@dataclass(frozen=True)
class ProjectConfig:
    workspace_root: Path | None
    course_id: str
    project_root: Path
    notes_root: Path
    language: str
    review_granularity: ReviewGranularity
    human_review_timing: str
    pause_after_each_round: bool
    max_changed_lines: int
    max_changed_files: int
    network_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": str(self.workspace_root) if self.workspace_root else None,
            "course_id": self.course_id,
            "project_root": str(self.project_root),
            "notes_root": str(self.notes_root),
            "language": self.language,
            "review_granularity": self.review_granularity,
            "human_review_timing": self.human_review_timing,
            "pause_after_each_round": self.pause_after_each_round,
            "max_changed_lines": self.max_changed_lines,
            "max_changed_files": self.max_changed_files,
            "network_mode": self.network_mode,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProjectConfig:
        workspace_root_raw = data.get("workspace_root")
        workspace_root = Path(workspace_root_raw) if workspace_root_raw else None
        return cls(
            workspace_root=workspace_root,
            course_id=str(data["course_id"]),
            project_root=Path(data["project_root"]),
            notes_root=Path(data["notes_root"]),
            language=str(data.get("language", "zh-CN")),
            review_granularity=str(data.get("review_granularity", "lecture")),  # type: ignore[arg-type]
            human_review_timing=str(data.get("human_review_timing", "final_only")),
            pause_after_each_round=bool(data.get("pause_after_each_round", False)),
            max_changed_lines=int(data.get("max_changed_lines", 500)),
            max_changed_files=int(data.get("max_changed_files", 20)),
            network_mode=str(data.get("network_mode", "disabled_by_default")),
        )
