from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DiffSummary:
    changed_files: int
    added_lines: int
    removed_lines: int
    changed_rel_paths: list[str]
    patch_path: Path
    notes_snapshot_path: Path

    @property
    def changed_lines(self) -> int:
        return self.added_lines + self.removed_lines

    def to_dict(self) -> dict[str, Any]:
        return {
            "changed_files": self.changed_files,
            "added_lines": self.added_lines,
            "removed_lines": self.removed_lines,
            "changed_lines": self.changed_lines,
            "changed_rel_paths": self.changed_rel_paths,
            "patch_path": str(self.patch_path),
            "notes_snapshot_path": str(self.notes_snapshot_path),
        }


class DiffService:
    def capture_state(self, *, notes_root: Path | str) -> dict[str, str]:
        root = Path(notes_root).expanduser().resolve()
        if not root.exists():
            return {}

        state: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root))
            state[rel] = path.read_text(encoding="utf-8", errors="replace")
        return state

    def write_diff_artifacts(
        self,
        *,
        notes_root: Path | str,
        before_state: dict[str, str],
        after_state: dict[str, str],
        run_dir: Path | str,
    ) -> DiffSummary:
        notes = Path(notes_root).expanduser().resolve()
        run_path = Path(run_dir).expanduser().resolve()
        run_path.mkdir(parents=True, exist_ok=True)

        changed_paths = sorted(
            path for path in set(before_state) | set(after_state) if before_state.get(path) != after_state.get(path)
        )

        patch_lines: list[str] = []
        added_lines = 0
        removed_lines = 0
        for rel in changed_paths:
            old_text = before_state.get(rel, "")
            new_text = after_state.get(rel, "")
            old_lines = old_text.splitlines(keepends=True)
            new_lines = new_text.splitlines(keepends=True)
            diff_lines = list(
                unified_diff(
                    old_lines,
                    new_lines,
                    fromfile=f"a/{rel}",
                    tofile=f"b/{rel}",
                    lineterm="",
                )
            )
            for line in diff_lines:
                patch_lines.append(line + "\n")
                if line.startswith("+++") or line.startswith("---"):
                    continue
                if line.startswith("+"):
                    added_lines += 1
                elif line.startswith("-"):
                    removed_lines += 1

        patch_path = run_path / "changes.patch"
        patch_path.write_text("".join(patch_lines), encoding="utf-8")

        notes_snapshot_path = run_path / "notes_snapshot"
        notes_snapshot_path.mkdir(parents=True, exist_ok=True)
        deleted_files: list[str] = []
        for rel in changed_paths:
            src = notes / rel
            if src.exists() and src.is_file():
                dst = notes_snapshot_path / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            else:
                deleted_files.append(rel)

        if deleted_files:
            (notes_snapshot_path / "deleted_files.json").write_text(
                json.dumps({"deleted_files": deleted_files}, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        summary = DiffSummary(
            changed_files=len(changed_paths),
            added_lines=added_lines,
            removed_lines=removed_lines,
            changed_rel_paths=changed_paths,
            patch_path=patch_path,
            notes_snapshot_path=notes_snapshot_path,
        )
        (run_path / "diff_summary.json").write_text(
            json.dumps(summary.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return summary
