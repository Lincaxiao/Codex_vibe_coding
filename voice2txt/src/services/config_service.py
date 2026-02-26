"""配置服务：加载/保存应用配置到 JSON 文件。"""

import json
import tempfile
from pathlib import Path

from src.constants import DEFAULT_CHANNELS, DEFAULT_MODEL_NAME, DEFAULT_SAMPLE_RATE
from src.models import AppConfig


class ConfigService:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.config_path = project_root / "state" / "app_config.json"
        self.state_dir = self.config_path.parent

    def load(self) -> AppConfig | None:
        if not self.config_path.exists():
            return None

        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        workspace_raw = str(raw.get("workspace_dir", "")).strip()
        if not workspace_raw:
            return None

        workspace = Path(workspace_raw).expanduser()
        if not self.is_workspace_valid(workspace):
            return None

        return AppConfig(
            workspace_dir=str(workspace.resolve()),
            model_name=str(raw.get("model_name", DEFAULT_MODEL_NAME)),
            sample_rate=self._parse_positive_int(raw.get("sample_rate"), DEFAULT_SAMPLE_RATE),
            channels=self._parse_positive_int(raw.get("channels"), DEFAULT_CHANNELS),
            input_device_index=self._parse_optional_int(raw.get("input_device_index")),
        )

    def save(self, config: AppConfig) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "workspace_dir": str(Path(config.workspace_dir).expanduser().resolve()),
            "model_name": config.model_name,
            "sample_rate": int(config.sample_rate),
            "channels": int(config.channels),
            "input_device_index": config.input_device_index,
        }
        self.config_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def is_workspace_valid(self, workspace_dir: Path) -> bool:
        if not workspace_dir:
            return False
        try:
            workspace_dir = workspace_dir.expanduser().resolve()
        except OSError:
            return False

        if not workspace_dir.exists() or not workspace_dir.is_dir():
            return False

        if not workspace_dir.is_absolute():
            return False

        try:
            with tempfile.NamedTemporaryFile(dir=workspace_dir, prefix=".writable_", delete=True):
                pass
        except OSError:
            return False

        return True

    @staticmethod
    def make_default(workspace_dir: Path) -> AppConfig:
        return AppConfig(
            workspace_dir=str(workspace_dir.expanduser().resolve()),
            model_name=DEFAULT_MODEL_NAME,
            sample_rate=DEFAULT_SAMPLE_RATE,
            channels=DEFAULT_CHANNELS,
            input_device_index=None,
        )

    @staticmethod
    def _parse_optional_int(value) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _parse_positive_int(value, fallback: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return fallback
        if parsed <= 0:
            return fallback
        return parsed
