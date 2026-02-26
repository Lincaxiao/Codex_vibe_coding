"""录音监控组件：显示录音时长和实时输入电平。"""

import time

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
)

from src.services.audio_service import AudioService
from src.ui.theme import apply_card_shadow


class RecordingMonitor(QFrame):
    """自包含的录音监控卡片。"""

    def __init__(self, audio_service: AudioService, parent=None) -> None:
        super().__init__(parent)
        self._audio_service = audio_service
        self._record_started_at: float | None = None

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(120)
        self._poll_timer.timeout.connect(self._update_indicators)

        self.setObjectName("Card")
        self._build_ui()
        apply_card_shadow(self)
        self.reset()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        card_title = QLabel("\U0001F3A4  录音监控")
        card_title.setObjectName("CardTitle")
        layout.addWidget(card_title)

        timer_row = QHBoxLayout()
        timer_row.setSpacing(8)
        timer_label = QLabel("录音时长")
        timer_label.setObjectName("MutedLabel")
        self.recording_timer_label = QLabel("00:00")
        self.recording_timer_label.setObjectName("TimerValue")
        timer_row.addWidget(timer_label)
        timer_row.addStretch(1)
        timer_row.addWidget(self.recording_timer_label)
        layout.addLayout(timer_row)

        level_row = QHBoxLayout()
        level_row.setSpacing(8)
        level_label = QLabel("输入电平")
        level_label.setObjectName("MutedLabel")
        self.level_bar = QProgressBar()
        self.level_bar.setObjectName("LevelBar")
        self.level_bar.setRange(0, 100)
        self.level_bar.setTextVisible(False)
        self.level_value_label = QLabel("0%")
        self.level_value_label.setObjectName("MutedLabel")
        self.level_value_label.setMinimumWidth(36)
        level_row.addWidget(level_label)
        level_row.addWidget(self.level_bar, stretch=1)
        level_row.addWidget(self.level_value_label)
        layout.addLayout(level_row)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._record_started_at = time.monotonic()
        self.setObjectName("CardRecording")
        self.style().unpolish(self)
        self.style().polish(self)
        self._poll_timer.start()
        self._update_indicators()

    def reset(self) -> None:
        self._poll_timer.stop()
        self._record_started_at = None
        self.recording_timer_label.setText("00:00")
        self.level_bar.setValue(0)
        self.level_value_label.setText("0%")
        self.setObjectName("Card")
        self.style().unpolish(self)
        self.style().polish(self)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _update_indicators(self) -> None:
        if self._record_started_at is None:
            return

        elapsed = int(max(0, time.monotonic() - self._record_started_at))
        minutes, seconds = divmod(elapsed, 60)
        self.recording_timer_label.setText(f"{minutes:02d}:{seconds:02d}")

        rms, peak = self._audio_service.get_live_levels()
        level_percent = max(0, min(100, int(max(rms, peak) * 100)))
        self.level_bar.setValue(level_percent)
        self.level_value_label.setText(f"{level_percent}%")
