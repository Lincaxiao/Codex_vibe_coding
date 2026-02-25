import os
from pathlib import Path

import pytest

from src.models import TranscribeRequest
from src.services.transcribe_service import TranscribeError, TranscribeService


def test_transcribe_success_sets_env_and_returns_text(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    input_audio = tmp_path / "audio.wav"
    input_audio.write_text("fake", encoding="utf-8")

    captured = {}

    def fake_transcribe(audio_path, path_or_hf_repo, language):
        captured["audio_path"] = audio_path
        captured["repo"] = path_or_hf_repo
        captured["language"] = language
        return {"text": " hello world "}

    service = TranscribeService()
    monkeypatch.setattr(service, "_get_transcribe_callable", lambda: fake_transcribe)
    monkeypatch.setattr(service, "_resolve_model_path", lambda: "/mock/model/path")

    result = service.transcribe(
        TranscribeRequest(
            source_audio_path=str(input_audio),
            workspace_dir=str(workspace),
            model_name="base.en",
            language="en",
        )
    )

    assert result.text == "hello world"
    assert result.model_name == "large-v3-fp16"
    assert captured["repo"] == "/mock/model/path"
    assert os.environ["MLX_HOME"].startswith(str(workspace))
    assert os.environ["HF_HOME"].startswith(str(workspace))
    assert os.environ["HUGGINGFACE_HUB_CACHE"].startswith(str(workspace))
    assert os.environ["TMPDIR"].startswith(str(workspace))


def test_transcribe_failure_raises(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    service = TranscribeService()

    def fake_transcribe(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(service, "_get_transcribe_callable", lambda: fake_transcribe)
    monkeypatch.setattr(service, "_resolve_model_path", lambda: "/mock/model/path")

    with pytest.raises(TranscribeError):
        service.transcribe(
            TranscribeRequest(
                source_audio_path="x.wav",
                workspace_dir=str(workspace),
                model_name="base.en",
                language="en",
            )
        )


def test_ensure_compatible_weights_from_model_safetensors(tmp_path: Path) -> None:
    model_dir = tmp_path / "model_dir"
    model_dir.mkdir(parents=True, exist_ok=True)
    source = model_dir / "model.safetensors"
    source.write_bytes(b"fake")

    TranscribeService._ensure_compatible_weights(model_dir)
    alias = model_dir / "weights.safetensors"
    assert alias.exists()


def test_request_model_name_is_ignored_and_uses_single_model(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    input_audio = tmp_path / "audio.wav"
    input_audio.write_text("fake", encoding="utf-8")

    captured = {}

    def fake_transcribe(audio_path, path_or_hf_repo, language):
        captured["repo"] = path_or_hf_repo
        return {"text": "ok"}

    service = TranscribeService()
    monkeypatch.setattr(service, "_get_transcribe_callable", lambda: fake_transcribe)
    monkeypatch.setattr(service, "_resolve_model_path", lambda: "/mock/model/path")

    result = service.transcribe(
        TranscribeRequest(
            source_audio_path=str(input_audio),
            workspace_dir=str(workspace),
            model_name="base.en",
            language="en",
        )
    )

    assert result.text == "ok"
    assert result.model_name == "large-v3-fp16"
    assert captured["repo"] == "/mock/model/path"


def test_resolve_model_path_downloads_once(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "repo"
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "model.safetensors").write_bytes(b"fake")

    calls = {"count": 0}

    def fake_snapshot_download(*_args, **_kwargs):
        calls["count"] += 1
        return str(model_dir)

    monkeypatch.setattr("src.services.transcribe_service.snapshot_download", fake_snapshot_download)

    service = TranscribeService()
    first = service._resolve_model_path()
    second = service._resolve_model_path()

    assert first == str(model_dir)
    assert second == str(model_dir)
    assert calls["count"] == 1


def test_transcribe_retries_after_weight_loading_error(monkeypatch, tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    input_audio = tmp_path / "audio.wav"
    input_audio.write_text("fake", encoding="utf-8")

    path_calls = []

    def fake_resolve_model_path(force_download: bool = False):
        path_calls.append(force_download)
        return "/mock/model/path"

    attempt = {"n": 0}

    def fake_transcribe(audio_path, path_or_hf_repo, language):
        attempt["n"] += 1
        if attempt["n"] == 1:
            raise RuntimeError("[load_npz] Input must be a zip file")
        return {"text": "ok"}

    service = TranscribeService()
    monkeypatch.setattr(service, "_get_transcribe_callable", lambda: fake_transcribe)
    monkeypatch.setattr(service, "_resolve_model_path", fake_resolve_model_path)

    result = service.transcribe(
        TranscribeRequest(
            source_audio_path=str(input_audio),
            workspace_dir=str(workspace),
            model_name="anything",
            language="en",
        )
    )

    assert result.text == "ok"
    assert path_calls == [False, True]
