import subprocess
from datetime import datetime
from pathlib import Path

from src.constants import DEFAULT_CHANNELS, DEFAULT_SAMPLE_RATE, SUPPORTED_IMPORT_SUFFIXES, TMP_DIRNAME


class ConversionError(Exception):
    pass


class UnsupportedFormatError(ConversionError):
    pass


class ConvertService:
    def __init__(self, sample_rate: int = DEFAULT_SAMPLE_RATE, channels: int = DEFAULT_CHANNELS) -> None:
        self.sample_rate = sample_rate
        self.channels = channels

    def prepare_for_transcribe(self, input_path: Path, workspace_dir: Path) -> Path:
        if not input_path.exists() or not input_path.is_file():
            raise ConversionError(f"Input file does not exist: {input_path}")

        suffix = input_path.suffix.lower()
        if suffix not in SUPPORTED_IMPORT_SUFFIXES:
            raise UnsupportedFormatError(
                f"Unsupported audio format: {suffix}. Supported: {sorted(SUPPORTED_IMPORT_SUFFIXES)}"
            )

        if suffix == ".wav" and self._is_target_wav(input_path):
            return input_path

        tmp_dir = workspace_dir / TMP_DIRNAME
        tmp_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = tmp_dir / f"{input_path.stem}_{ts}.wav"
        target = self._ensure_unique_path(target)
        self.to_wav_16k_mono(input_path, target)
        return target

    def to_wav_16k_mono(self, input_path: Path, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-ac",
            str(self.channels),
            "-ar",
            str(self.sample_rate),
            "-vn",
            str(output_path),
        ]
        self._run_command(cmd)

    def _run_command(self, cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or "").strip()
            raise ConversionError(f"ffmpeg conversion failed: {detail}") from exc
        except FileNotFoundError as exc:
            raise ConversionError("ffmpeg is not installed or not found in PATH.") from exc

    def _is_target_wav(self, path: Path) -> bool:
        try:
            import soundfile as sf
        except Exception:
            return False

        try:
            info = sf.info(str(path))
        except RuntimeError:
            return False

        return info.samplerate == self.sample_rate and info.channels == self.channels

    @staticmethod
    def _ensure_unique_path(path: Path) -> Path:
        if not path.exists():
            return path

        stem = path.stem
        suffix = path.suffix
        parent = path.parent
        index = 1
        while True:
            candidate = parent / f"{stem}_{index:02d}{suffix}"
            if not candidate.exists():
                return candidate
            index += 1

