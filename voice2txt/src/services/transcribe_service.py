import os
import shutil
import time
from pathlib import Path
from typing import Callable

from huggingface_hub import snapshot_download

from src.constants import (
    DEFAULT_LANGUAGE,
    DEFAULT_MODEL_NAME,
    DEFAULT_MODEL_REPO,
    MODEL_CACHE_DIRNAME,
    TMP_DIRNAME,
)
from src.models import TranscribeRequest, TranscribeResult


class TranscribeError(Exception):
    pass


class TranscribeService:
    def __init__(self, default_model_name: str = DEFAULT_MODEL_NAME, default_language: str = DEFAULT_LANGUAGE):
        self.default_model_name = default_model_name
        self.default_language = default_language
        self._transcribe_callable: Callable | None = None
        self._model_path_by_workspace: dict[str, str] = {}

    def transcribe(self, request: TranscribeRequest) -> TranscribeResult:
        """执行转写。request.model_name 被忽略，始终使用 DEFAULT_MODEL_NAME。"""
        workspace_dir = Path(request.workspace_dir).expanduser().resolve()
        self._configure_cache(workspace_dir)

        model_name = self.default_model_name
        language = request.language or self.default_language
        transcribe_callable = self._get_transcribe_callable()
        model_path = self._resolve_model_path(workspace_dir=workspace_dir)

        start = time.perf_counter()
        try:
            raw_result = self._run_transcribe_once(
                transcribe_callable=transcribe_callable,
                audio_path=str(request.source_audio_path),
                model_path=model_path,
                language=language,
            )
        except Exception as exc:
            if self._is_weight_loading_error(str(exc)):
                refreshed_path = self._resolve_model_path(workspace_dir=workspace_dir, force_download=True)
                try:
                    raw_result = self._run_transcribe_once(
                        transcribe_callable=transcribe_callable,
                        audio_path=str(request.source_audio_path),
                        model_path=refreshed_path,
                        language=language,
                    )
                except Exception as retry_exc:
                    raise TranscribeError(f"Transcription failed: {retry_exc}") from retry_exc
            else:
                raise TranscribeError(f"Transcription failed: {exc}") from exc

        duration = time.perf_counter() - start

        text = self._extract_text(raw_result)
        return TranscribeResult(
            text=text.strip(),
            duration_sec=duration,
            source_audio_path=request.source_audio_path,
            model_name=model_name,
        )

    @staticmethod
    def _run_transcribe_once(
        transcribe_callable: Callable,
        audio_path: str,
        model_path: str,
        language: str,
    ):
        return transcribe_callable(
            audio_path,
            path_or_hf_repo=model_path,
            language=language,
        )

    @staticmethod
    def _is_weight_loading_error(message: str) -> bool:
        lowered = message.lower()
        return "load_npz" in lowered or "safetensors" in lowered

    def _resolve_model_path(self, workspace_dir: Path, force_download: bool = False) -> str:
        workspace_key = str(workspace_dir.expanduser().resolve())
        cached_model_path = self._model_path_by_workspace.get(workspace_key)
        if not force_download and cached_model_path and Path(cached_model_path).exists():
            return cached_model_path

        try:
            model_dir = Path(
                snapshot_download(
                    repo_id=DEFAULT_MODEL_REPO,
                    token=False,
                    local_files_only=False,
                    force_download=force_download,
                )
            )
        except Exception as exc:
            raise TranscribeError(f"Failed to download model '{DEFAULT_MODEL_REPO}': {exc}") from exc

        self._ensure_compatible_weights(model_dir)
        resolved_model_path = str(model_dir)
        self._model_path_by_workspace[workspace_key] = resolved_model_path
        return resolved_model_path

    @staticmethod
    def _ensure_compatible_weights(model_dir: Path) -> None:
        weights_safetensors = model_dir / "weights.safetensors"
        weights_npz = model_dir / "weights.npz"
        if weights_safetensors.exists() or weights_npz.exists():
            return

        source_candidates = []
        model_safetensors = model_dir / "model.safetensors"
        if model_safetensors.exists():
            source_candidates.append(model_safetensors)
        source_candidates.extend(sorted(model_dir.glob("*.safetensors")))

        if not source_candidates:
            available = sorted(p.name for p in model_dir.iterdir() if p.is_file())
            raise TranscribeError(
                "Model weights not found in downloaded snapshot. "
                f"Expected weights.safetensors/weights.npz. Available files: {available}"
            )

        source = source_candidates[0]
        try:
            if weights_safetensors.exists():
                weights_safetensors.unlink()
            weights_safetensors.symlink_to(source.name)
        except OSError:
            shutil.copy2(source, weights_safetensors)

    def _configure_cache(self, workspace_dir: Path) -> None:
        cache_root = workspace_dir / MODEL_CACHE_DIRNAME
        mlx_home = cache_root / "mlx"
        hf_home = cache_root / "hf"
        hf_hub = hf_home / "hub"
        tmp_dir = workspace_dir / TMP_DIRNAME

        for path in (mlx_home, hf_home, hf_hub, tmp_dir):
            path.mkdir(parents=True, exist_ok=True)

        os.environ["MLX_HOME"] = str(mlx_home)
        os.environ["HF_HOME"] = str(hf_home)
        os.environ["HUGGINGFACE_HUB_CACHE"] = str(hf_hub)
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        os.environ["TMPDIR"] = str(tmp_dir)

    def _get_transcribe_callable(self) -> Callable:
        if self._transcribe_callable is None:
            try:
                from mlx_whisper import transcribe as mlx_transcribe
            except Exception as exc:  # pragma: no cover
                raise TranscribeError("mlx-whisper is not installed or import failed.") from exc
            self._transcribe_callable = mlx_transcribe
        return self._transcribe_callable

    @staticmethod
    def _extract_text(raw_result) -> str:
        if isinstance(raw_result, dict) and "text" in raw_result:
            return str(raw_result["text"])
        if isinstance(raw_result, str):
            return raw_result
        raise TranscribeError("mlx-whisper returned an unexpected result type.")
