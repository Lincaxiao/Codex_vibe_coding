from PySide6.QtCore import QObject, Signal, Slot

from src.models import TranscribeRequest
from src.services.convert_service import ConvertService
from src.services.transcribe_service import TranscribeService
from src.workers.transcribe_pipeline import prepare_transcribe_request


class TranscribeWorker(QObject):
    started = Signal()
    stage_changed = Signal(str)
    finished = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        service: TranscribeService,
        convert_service: ConvertService,
        request: TranscribeRequest,
    ) -> None:
        super().__init__()
        self._service = service
        self._convert_service = convert_service
        self._request = request

    @Slot()
    def run(self) -> None:
        self.started.emit()
        try:
            self.stage_changed.emit("converting")
            request = prepare_transcribe_request(
                convert_service=self._convert_service,
                request=self._request,
            )

            self.stage_changed.emit("transcribing")
            result = self._service.transcribe(request)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)
