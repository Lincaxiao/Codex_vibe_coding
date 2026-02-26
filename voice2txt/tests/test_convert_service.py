import subprocess
from pathlib import Path

import pytest

from src.models import TranscribeRequest
from src.services.convert_service import ConversionError, ConvertService, UnsupportedFormatError
from src.workers.transcribe_pipeline import prepare_transcribe_request


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


def test_pipeline_prepares_converted_request(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "input.mp3"
    source.write_text("fake", encoding="utf-8")
    converted = workspace / ".tmp" / "converted.wav"

    convert_service = ConvertService()
    monkeypatch.setattr(
        convert_service,
        "prepare_for_transcribe",
        lambda input_path, workspace_dir: converted,
    )

    request = prepare_transcribe_request(
        convert_service=convert_service,
        request=TranscribeRequest(
            source_audio_path=str(source),
            workspace_dir=str(workspace),
            model_name="large-v3-fp16",
            language="en",
        ),
    )

    assert request.source_audio_path == str(converted)
    assert request.workspace_dir == str(workspace)
