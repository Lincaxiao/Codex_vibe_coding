from pathlib import Path

import pytest

from src.services.cleanup_service import CleanupService, CleanupServiceError


def test_cleanup_removes_orphan_wavs(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    orphan_wav = workspace / "record_1.wav"
    orphan_wav.write_bytes(b"1234")
    kept_wav = workspace / "record_2.wav"
    kept_wav.write_bytes(b"12")
    (workspace / "record_2.txt").write_text("ok", encoding="utf-8")

    service = CleanupService()
    result = service.cleanup_orphan_wavs(workspace)

    assert result.orphan_count == 1
    assert result.deleted_count == 1
    assert result.reclaimed_bytes == 4
    assert not result.failed_paths
    assert not orphan_wav.exists()
    assert kept_wav.exists()


def test_find_orphan_wavs_accepts_workspace_root_txt_for_tmp_wav(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    tmp_dir = workspace / ".tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    wav_path = tmp_dir / "meeting.wav"
    wav_path.write_bytes(b"123")
    (workspace / "meeting.txt").write_text("exists", encoding="utf-8")

    service = CleanupService()
    orphan_wavs = service.find_orphan_wavs(workspace)

    assert not orphan_wavs


def test_cleanup_invalid_workspace_raises(tmp_path: Path) -> None:
    service = CleanupService()
    with pytest.raises(CleanupServiceError):
        service.cleanup_orphan_wavs(tmp_path / "missing_workspace")
