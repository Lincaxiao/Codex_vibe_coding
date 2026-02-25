from datetime import datetime
from pathlib import Path

from src.services.path_service import (
    ensure_txt_filename,
    recording_wav_path,
    suggested_txt_filename_from_audio,
    timestamp_token,
)


def test_timestamp_token_stable() -> None:
    dt = datetime(2026, 2, 25, 10, 30, 45)
    assert timestamp_token(dt) == "20260225_103045"


def test_ensure_txt_filename() -> None:
    assert ensure_txt_filename("sample") == "sample.txt"
    assert ensure_txt_filename("sample.txt") == "sample.txt"


def test_suggested_txt_filename_from_audio() -> None:
    audio_path = Path("/tmp/abc/demo.wav")
    assert suggested_txt_filename_from_audio(audio_path) == "demo.txt"


def test_recording_wav_path_avoids_collision(tmp_path: Path) -> None:
    dt = datetime(2026, 2, 25, 10, 30, 45)
    first = recording_wav_path(tmp_path, now=dt)
    first.write_text("x", encoding="utf-8")
    second = recording_wav_path(tmp_path, now=dt)

    assert first.name == "record_20260225_103045.wav"
    assert second.name == "record_20260225_103045_01.wav"

