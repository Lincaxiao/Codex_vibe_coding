from pathlib import Path

from src.models import TranscribeRequest
from src.services.convert_service import ConvertService


def prepare_transcribe_request(
    convert_service: ConvertService,
    request: TranscribeRequest,
) -> TranscribeRequest:
    workspace_dir = Path(request.workspace_dir).expanduser().resolve()
    source_audio_path = Path(request.source_audio_path)
    prepared_audio_path = convert_service.prepare_for_transcribe(
        source_audio_path,
        workspace_dir=workspace_dir,
    )
    return TranscribeRequest(
        source_audio_path=str(prepared_audio_path),
        workspace_dir=request.workspace_dir,
        model_name=request.model_name,
        language=request.language,
    )
