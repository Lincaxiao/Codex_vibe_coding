from pathlib import Path

from src.models import AppConfig
from src.services.config_service import ConfigService


def test_load_missing_config_returns_none(tmp_path: Path) -> None:
    service = ConfigService(project_root=tmp_path)
    assert service.load() is None


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    service = ConfigService(project_root=tmp_path)
    config = AppConfig(
        workspace_dir=str(workspace),
        model_name="large-v3-fp16",
        sample_rate=16000,
        channels=1,
        input_device_index=3,
    )
    service.save(config)

    loaded = service.load()
    assert loaded is not None
    assert Path(loaded.workspace_dir) == workspace.resolve()
    assert loaded.model_name == "large-v3-fp16"
    assert loaded.sample_rate == 16000
    assert loaded.channels == 1
    assert loaded.input_device_index == 3


def test_invalid_workspace_returns_none(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    service = ConfigService(project_root=tmp_path)
    config = AppConfig(workspace_dir=str(workspace))
    service.save(config)

    workspace.rmdir()
    assert service.load() is None
