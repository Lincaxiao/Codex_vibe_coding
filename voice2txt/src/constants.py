from pathlib import Path

APP_TITLE = "语音转写助手"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = PROJECT_ROOT / "state"
CONFIG_PATH = STATE_DIR / "app_config.json"

DEFAULT_MODEL_NAME = "large-v3-fp16"
DEFAULT_MODEL_REPO = "mlx-community/whisper-large-v3-fp16"
DEFAULT_LANGUAGE = "en"
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_CHANNELS = 1

SUPPORTED_IMPORT_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac"}

MODEL_CACHE_DIRNAME = ".model_cache"
TMP_DIRNAME = ".tmp"
