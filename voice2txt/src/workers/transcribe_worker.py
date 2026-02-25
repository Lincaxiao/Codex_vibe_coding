from PySide6.QtCore import QObject, Signal, Slot

from src.models import TranscribeRequest
from src.services.transcribe_service import TranscribeService


class TranscribeWorker(QObject):
    started = Signal()
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, service: TranscribeService, request: TranscribeRequest) -> None:
        super().__init__()
        self._service = service
        self._request = request

    @Slot()
    def run(self) -> None:
        self.started.emit()
        try:
            result = self._service.transcribe(self._request)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)

