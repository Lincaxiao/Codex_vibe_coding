from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    run_type: str
    status: str
    created_at: str | None
    path: Path
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_type": self.run_type,
            "status": self.status,
            "created_at": self.created_at,
            "path": str(self.path),
            "summary": self.summary,
        }


class RunHistoryService:
    def list_runs(self, *, project_root: Path | str) -> list[RunRecord]:
        root = Path(project_root).expanduser().resolve()
        runs_dir = root / "runs"
        if not runs_dir.exists():
            return []

        records: list[RunRecord] = []
        for run_path in sorted([p for p in runs_dir.iterdir() if p.is_dir()]):
            run_id = run_path.name
            workflow_path = run_path / "workflow_result.json"
            manifest_path = run_path / "run_manifest.json"

            if workflow_path.exists():
                payload = self._read_json(workflow_path)
                records.append(
                    RunRecord(
                        run_id=run_id,
                        run_type="workflow",
                        status=str(payload.get("status", "unknown")),
                        created_at=self._first_timestamp(payload),
                        path=run_path,
                        summary={
                            "round_count": len(payload.get("rounds", [])),
                            "workflow_result_path": str(workflow_path),
                        },
                    )
                )
                continue

            if manifest_path.exists():
                payload = self._read_json(manifest_path)
                records.append(
                    RunRecord(
                        run_id=run_id,
                        run_type="codex",
                        status="succeeded" if payload.get("success") else "failed",
                        created_at=self._first_timestamp(payload),
                        path=run_path,
                        summary={
                            "final_exit_code": payload.get("final_exit_code"),
                            "attempts": len(payload.get("attempts", [])),
                            "run_manifest_path": str(manifest_path),
                        },
                    )
                )
                continue

            records.append(
                RunRecord(
                    run_id=run_id,
                    run_type="unknown",
                    status="unknown",
                    created_at=None,
                    path=run_path,
                    summary={},
                )
            )

        # Newest first by run_id name; run_id includes timestamp in this project.
        records.sort(key=lambda item: item.run_id, reverse=True)
        return records

    def latest_workflow_result(self, *, project_root: Path | str) -> dict[str, Any] | None:
        for record in self.list_runs(project_root=project_root):
            if record.run_type == "workflow":
                workflow_path = record.path / "workflow_result.json"
                if workflow_path.exists():
                    return self._read_json(workflow_path)
        return None

    def load_round_status(self, *, project_root: Path | str) -> dict[str, Any]:
        root = Path(project_root).expanduser().resolve()
        path = root / "state" / "round_status.json"
        if not path.exists():
            return {}
        return self._read_json(path)

    def resolve_patch_path(
        self,
        *,
        project_root: Path | str,
        run_id: str,
        round_name: str | None = None,
    ) -> Path | None:
        root = Path(project_root).expanduser().resolve()
        run_dir = root / "runs" / run_id
        if not run_dir.exists():
            return None

        if round_name:
            candidate = run_dir / round_name / "changes.patch"
            return candidate if candidate.exists() else None

        direct_patch = run_dir / "changes.patch"
        if direct_patch.exists():
            return direct_patch

        workflow_path = run_dir / "workflow_result.json"
        if workflow_path.exists():
            payload = self._read_json(workflow_path)
            rounds = payload.get("rounds", [])
            if isinstance(rounds, list):
                for item in reversed(rounds):
                    if isinstance(item, dict):
                        name = item.get("round_name")
                        if isinstance(name, str):
                            candidate = run_dir / name / "changes.patch"
                            if candidate.exists():
                                return candidate
        return None

    def read_patch(
        self,
        *,
        project_root: Path | str,
        run_id: str,
        round_name: str | None = None,
    ) -> str | None:
        patch_path = self.resolve_patch_path(
            project_root=project_root,
            run_id=run_id,
            round_name=round_name,
        )
        if patch_path is None:
            return None
        return patch_path.read_text(encoding="utf-8", errors="replace")

    def _first_timestamp(self, payload: dict[str, Any]) -> str | None:
        for key in ("started_at", "created_at", "finished_at"):
            value = payload.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _read_json(self, path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fp:
            return json.load(fp)
