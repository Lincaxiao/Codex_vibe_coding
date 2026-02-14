from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_snapshot_id() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _safe_name(name: str) -> str:
    filtered = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in name.strip())
    filtered = filtered.strip("-")
    return filtered or "source"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_id: str
    snapshot_root: Path
    source_index_path: Path
    source_hashes_path: Path
    source_count: int
    file_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "snapshot_root": str(self.snapshot_root),
            "source_index_path": str(self.source_index_path),
            "source_hashes_path": str(self.source_hashes_path),
            "source_count": self.source_count,
            "file_count": self.file_count,
        }


@dataclass(frozen=True)
class SnapshotVerificationResult:
    snapshot_id: str
    valid: bool
    checked_files: int
    mismatches: list[dict[str, str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "valid": self.valid,
            "checked_files": self.checked_files,
            "mismatches": self.mismatches,
        }


class SnapshotService:
    def create_snapshot(
        self,
        *,
        project_root: Path | str,
        sources: list[Path | str],
        lecture_mapping: dict[str, str] | None = None,
        snapshot_id: str | None = None,
    ) -> SnapshotResult:
        if not sources:
            raise ValueError("sources cannot be empty")

        root = Path(project_root).expanduser().resolve()
        artifacts_root = root / "artifacts"
        artifacts_root.mkdir(parents=True, exist_ok=True)

        resolved_sources = [Path(source).expanduser().resolve() for source in sources]
        for source in resolved_sources:
            if not source.exists():
                raise FileNotFoundError(f"source not found: {source}")

        snapshot_key = snapshot_id or _utc_snapshot_id()
        snapshot_root = artifacts_root / "snapshots" / snapshot_key
        if snapshot_root.exists():
            raise FileExistsError(f"snapshot already exists: {snapshot_root}")
        snapshot_root.mkdir(parents=True, exist_ok=False)

        mapping: dict[str, str] = {}
        if lecture_mapping:
            mapping = {
                str(Path(source_path).expanduser().resolve()): lecture
                for source_path, lecture in lecture_mapping.items()
            }
        generated_at = datetime.now(tz=timezone.utc).isoformat()
        source_index: dict[str, Any] = {
            "snapshot_id": snapshot_key,
            "generated_at": generated_at,
            "project_root": str(root),
            "sources": [],
        }
        source_hashes: dict[str, Any] = {
            "snapshot_id": snapshot_key,
            "generated_at": generated_at,
            "project_root": str(root),
            "files": {},
        }

        file_count = 0
        for idx, source in enumerate(resolved_sources, start=1):
            safe_name = _safe_name(source.name)
            dest_name = f"{idx:03d}_{safe_name}"
            dest_path = snapshot_root / dest_name
            source_type = "dir" if source.is_dir() else "file"
            if source.is_dir():
                shutil.copytree(source, dest_path, dirs_exist_ok=False)
            else:
                shutil.copy2(source, dest_path)

            file_hash_entries = self._collect_hashes(
                project_root=root,
                copied_path=dest_path,
            )
            source_hashes["files"].update(file_hash_entries)
            file_count += len(file_hash_entries)

            source_index["sources"].append(
                {
                    "source_id": f"src_{idx:04d}",
                    "source_path": str(source),
                    "source_type": source_type,
                    "snapshot_path": str(dest_path),
                    "snapshot_rel_path": str(dest_path.relative_to(root)),
                    "lecture": mapping.get(str(source)),
                    "file_count": len(file_hash_entries),
                }
            )

        self._set_read_only(snapshot_root)

        source_index_path = artifacts_root / "source_index.json"
        source_hashes_path = artifacts_root / "source_hashes.json"
        self._write_json(source_index_path, source_index)
        self._write_json(source_hashes_path, source_hashes)

        return SnapshotResult(
            snapshot_id=snapshot_key,
            snapshot_root=snapshot_root,
            source_index_path=source_index_path,
            source_hashes_path=source_hashes_path,
            source_count=len(resolved_sources),
            file_count=file_count,
        )

    def verify_snapshot_hashes(self, *, project_root: Path | str) -> SnapshotVerificationResult:
        root = Path(project_root).expanduser().resolve()
        source_hashes_path = root / "artifacts" / "source_hashes.json"
        payload = self._read_json(source_hashes_path)
        expected_files: dict[str, str] = payload.get("files", {})
        snapshot_id = str(payload.get("snapshot_id", "unknown"))

        mismatches: list[dict[str, str]] = []
        for relative_path, expected_hash in expected_files.items():
            file_path = root / relative_path
            if not file_path.exists():
                mismatches.append(
                    {
                        "path": str(file_path),
                        "reason": "missing",
                        "expected": expected_hash,
                        "actual": "",
                    }
                )
                continue

            actual_hash = _file_sha256(file_path)
            if actual_hash != expected_hash:
                mismatches.append(
                    {
                        "path": str(file_path),
                        "reason": "hash_mismatch",
                        "expected": expected_hash,
                        "actual": actual_hash,
                    }
                )

        return SnapshotVerificationResult(
            snapshot_id=snapshot_id,
            valid=len(mismatches) == 0,
            checked_files=len(expected_files),
            mismatches=mismatches,
        )

    def _collect_hashes(
        self,
        *,
        project_root: Path,
        copied_path: Path,
    ) -> dict[str, str]:
        if copied_path.is_file():
            relative_path = str(copied_path.relative_to(project_root))
            return {relative_path: _file_sha256(copied_path)}

        results: dict[str, str] = {}
        for file_path in sorted(copied_path.rglob("*")):
            if file_path.is_file():
                relative_path = str(file_path.relative_to(project_root))
                results[relative_path] = _file_sha256(file_path)
        return results

    def _set_read_only(self, snapshot_root: Path) -> None:
        # Ensure parent directories are traversable and files are immutable by default.
        for dir_path in sorted([snapshot_root, *snapshot_root.rglob("*")], key=lambda p: len(p.parts)):
            if dir_path.is_dir():
                os.chmod(dir_path, 0o555)
            else:
                os.chmod(dir_path, 0o444)

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
