from datetime import datetime
from pathlib import Path


def timestamp_token(now: datetime | None = None) -> str:
    now = now or datetime.now()
    return now.strftime("%Y%m%d_%H%M%S")


def ensure_txt_filename(name: str) -> str:
    if name.lower().endswith(".txt"):
        return name
    return f"{name}.txt"


def suggested_txt_filename_from_audio(audio_path: Path) -> str:
    return ensure_txt_filename(audio_path.stem)


def recording_wav_path(workspace_dir: Path, now: datetime | None = None) -> Path:
    base_name = f"record_{timestamp_token(now)}"
    candidate = workspace_dir / f"{base_name}.wav"
    if not candidate.exists():
        return candidate

    index = 1
    while True:
        candidate = workspace_dir / f"{base_name}_{index:02d}.wav"
        if not candidate.exists():
            return candidate
        index += 1

