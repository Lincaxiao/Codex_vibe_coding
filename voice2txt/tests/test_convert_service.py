import subprocess
from pathlib import Path

import pytest

from src.services.convert_service import ConversionError, ConvertService, UnsupportedFormatError


def test_unsupported_format_raises(tmp_path: Path) -> None:
    input_file = tmp_path / "sample.txt"
    input_file.write_text("not audio", encoding="utf-8")
    service = ConvertService()

    with pytest.raises(UnsupportedFormatError):
        service.prepare_for_transcribe(input_file, tmp_path)


def test_prepare_wav_without_conversion(monkeypatch, tmp_path: Path) -> None:
    input_file = tmp_path / "sample.wav"
    input_file.write_text("fake", encoding="utf-8")
    service = ConvertService()

    monkeypatch.setattr(service, "_is_target_wav", lambda _p: True)
    output = service.prepare_for_transcribe(input_file, tmp_path)

    assert output == input_file


def test_to_wav_builds_ffmpeg_command(monkeypatch, tmp_path: Path) -> None:
    input_file = tmp_path / "input.mp3"
    input_file.write_text("fake", encoding="utf-8")
    output_file = tmp_path / "output.wav"

    captured: dict[str, list[str]] = {}
    service = ConvertService(sample_rate=16000, channels=1)

    def fake_run_command(cmd: list[str]) -> None:
        captured["cmd"] = cmd

    monkeypatch.setattr(service, "_run_command", fake_run_command)
    service.to_wav_16k_mono(input_file, output_file)

    assert captured["cmd"][0] == "ffmpeg"
    assert "-i" in captured["cmd"]
    assert str(input_file) in captured["cmd"]
    assert str(output_file) in captured["cmd"]


def test_run_command_failure_raises() -> None:
    service = ConvertService()
    with pytest.raises(ConversionError):
        service._run_command(["ffmpeg", "-i", "missing.wav", "out.wav"])

