"""清理服务：扫描和删除孤立的 WAV 缓存文件。"""

from dataclasses import dataclass, field
from pathlib import Path


class CleanupServiceError(Exception):
    pass


@dataclass
class CleanupResult:
    orphan_count: int
    deleted_count: int
    reclaimed_bytes: int
    failed_paths: list[Path] = field(default_factory=list)


class CleanupService:
    def find_orphan_wavs(self, workspace_dir: Path) -> list[Path]:
        workspace = self._validate_workspace(workspace_dir)
        orphan_wavs: list[Path] = []

        for wav_path in sorted(workspace.rglob("*.wav")):
            if not wav_path.is_file():
                continue
            if self._has_matching_txt(wav_path, workspace):
                continue
            orphan_wavs.append(wav_path)

        return orphan_wavs

    def delete_wavs(self, wav_paths: list[Path]) -> CleanupResult:
        """直接删除给定的 WAV 列表，避免重复扫描（TOCTOU 安全）。"""
        reclaimed_bytes = 0
        deleted_count = 0
        failed_paths: list[Path] = []

        for wav_path in wav_paths:
            try:
                file_size = wav_path.stat().st_size
            except OSError:
                file_size = 0
            try:
                wav_path.unlink()
            except OSError:
                failed_paths.append(wav_path)
                continue
            deleted_count += 1
            reclaimed_bytes += file_size

        return CleanupResult(
            orphan_count=len(wav_paths),
            deleted_count=deleted_count,
            reclaimed_bytes=reclaimed_bytes,
            failed_paths=failed_paths,
        )

    def cleanup_orphan_wavs(self, workspace_dir: Path) -> CleanupResult:
        """扫描并删除孤立 WAV（保留向后兼容）。"""
        orphan_wavs = self.find_orphan_wavs(workspace_dir)
        return self.delete_wavs(orphan_wavs)

    @staticmethod
    def _validate_workspace(workspace_dir: Path) -> Path:
        try:
            workspace = workspace_dir.expanduser().resolve()
        except OSError as exc:
            raise CleanupServiceError(f"无法访问工作区：{workspace_dir}") from exc
        if not workspace.exists() or not workspace.is_dir():
            raise CleanupServiceError(f"工作区不存在或不可用：{workspace}")
        return workspace

    @staticmethod
    def _has_matching_txt(wav_path: Path, workspace_root: Path) -> bool:
        sibling_txt = wav_path.with_suffix(".txt")
        if sibling_txt.exists():
            return True

        workspace_txt = workspace_root / f"{wav_path.stem}.txt"
        return workspace_txt.exists()
