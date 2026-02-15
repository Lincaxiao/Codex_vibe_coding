from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class CacheClearResult:
    project_root: Path
    removed_paths: list[str]
    kept_paths: list[str]
    session_reset: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root),
            "removed_paths": self.removed_paths,
            "removed_count": len(self.removed_paths),
            "kept_paths": self.kept_paths,
            "session_reset": self.session_reset,
        }


class CacheService:
    def clear_intermediate_files(
        self,
        *,
        project_root: Path | str,
        preserve_prompt_templates: bool = True,
        progress_callback: Callable[[str], None] | None = None,
    ) -> CacheClearResult:
        root = Path(project_root).expanduser().resolve()
        runs_dir = root / "runs"
        artifacts_dir = root / "artifacts"
        prompt_templates_file = artifacts_dir / "prompt_templates.json"

        removed_paths: list[str] = []
        kept_paths: list[str] = []

        self._emit(progress_callback, "[cache] 开始清理中间文件")

        if runs_dir.exists() and runs_dir.is_dir():
            for child in sorted(runs_dir.iterdir()):
                self._remove_path(child)
                removed_paths.append(str(child))
                self._emit(progress_callback, f"[cache] 已清理: {child}")

        if artifacts_dir.exists() and artifacts_dir.is_dir():
            for child in sorted(artifacts_dir.iterdir()):
                if preserve_prompt_templates and child == prompt_templates_file:
                    kept_paths.append(str(child))
                    self._emit(progress_callback, f"[cache] 保留: {child}")
                    continue
                self._remove_path(child)
                removed_paths.append(str(child))
                self._emit(progress_callback, f"[cache] 已清理: {child}")

        session_reset = self._reset_session_state(root)
        if session_reset:
            self._emit(progress_callback, "[cache] 会话状态已重置为 idle")

        self._emit(progress_callback, f"[cache] 清理完成，删除 {len(removed_paths)} 项")
        return CacheClearResult(
            project_root=root,
            removed_paths=removed_paths,
            kept_paths=kept_paths,
            session_reset=session_reset,
        )

    def _remove_path(self, path: Path) -> None:
        if path.is_symlink() or path.is_file():
            path.unlink(missing_ok=True)
            return
        if path.is_dir():
            shutil.rmtree(path)
            return
        path.unlink(missing_ok=True)

    def _reset_session_state(self, root: Path) -> bool:
        session_path = root / "state" / "session.json"
        payload = self._read_json(session_path)
        if not payload:
            return False
        payload["status"] = "idle"
        payload["current_run_id"] = None
        payload["updated_at"] = _now_iso()
        self._write_json(session_path, payload)
        return True

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

    def _emit(
        self,
        progress_callback: Callable[[str], None] | None,
        message: str,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(message)
        except Exception:
            return

