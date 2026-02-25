from dataclasses import dataclass
from enum import Enum

from src.constants import (
    DEFAULT_CHANNELS,
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL_NAME,
    DEFAULT_SAMPLE_RATE,
)


class AppState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    TRANSCRIBING = "transcribing"
    ERROR = "error"


@dataclass
class AppConfig:
    workspace_dir: str
    model_name: str = DEFAULT_MODEL_NAME
    sample_rate: int = DEFAULT_SAMPLE_RATE
    channels: int = DEFAULT_CHANNELS
    input_device_index: int | None = None


@dataclass
class TranscribeRequest:
    source_audio_path: str
    workspace_dir: str
    model_name: str = DEFAULT_MODEL_NAME
    language: str = DEFAULT_LANGUAGE


@dataclass
class TranscribeResult:
    text: str
    duration_sec: float
    source_audio_path: str
    model_name: str


@dataclass
class TranscriptBuffer:
    text: str
    source_audio_path: str
    suggested_filename: str
    is_saved: bool = False
