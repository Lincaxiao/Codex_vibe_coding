import time
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.constants import APP_TITLE, DEFAULT_LANGUAGE
from src.models import AppConfig, AppState, TranscriptBuffer, TranscribeRequest, TranscribeResult
from src.services.audio_service import AudioService, AudioServiceError
from src.services.cleanup_service import CleanupService, CleanupServiceError
from src.services.config_service import ConfigService
from src.services.convert_service import ConvertService
from src.services.path_service import (
    ensure_txt_filename,
    recording_wav_path,
    suggested_txt_filename_from_audio,
)
from src.services.save_service import SaveService, SaveServiceError
from src.services.transcribe_service import TranscribeService
from src.workers.transcribe_worker import TranscribeWorker


class MainWindow(QMainWindow):
    def __init__(self, config_service: ConfigService, config: AppConfig) -> None:
        super().__init__()
        self.config_service = config_service
        self.config = config

        self.audio_service = AudioService(sample_rate=config.sample_rate, channels=config.channels)
        self.audio_service.set_input_device(config.input_device_index)
        self.cleanup_service = CleanupService()
        self.convert_service = ConvertService(sample_rate=config.sample_rate, channels=config.channels)
        self.transcribe_service = TranscribeService(default_model_name=config.model_name)
        self.save_service = SaveService()

        self.current_state = AppState.IDLE
        self.transcript_buffer: TranscriptBuffer | None = None

        self._transcribe_thread: QThread | None = None
        self._transcribe_worker: TranscribeWorker | None = None
        self._pending_suggested_filename = "转写结果.txt"
        self._pending_source_audio_path = ""

        self._record_started_at: float | None = None
        self._recording_ui_timer = QTimer(self)
        self._recording_ui_timer.setInterval(120)
        self._recording_ui_timer.timeout.connect(self._update_recording_indicators)

        self.setWindowTitle(APP_TITLE)
        self.resize(1120, 720)

        self._build_ui()
        self._apply_styles()
        self._refresh_workspace_label()
        self._refresh_microphone_options()
        self._reset_recording_monitor()
        self._set_state(AppState.IDLE, "就绪。")

    def _build_ui(self) -> None:
        container = QWidget(self)
        root_layout = QHBoxLayout(container)
        root_layout.setContentsMargins(16, 16, 16, 16)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        root_layout.addWidget(splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(12)

        header_card, header_layout = self._create_card()
        title_label = QLabel("语音转写助手")
        title_label.setObjectName("Title")
        subtitle_label = QLabel("本地录音与音频转写工作台")
        subtitle_label.setObjectName("Subtitle")
        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        left_layout.addWidget(header_card)

        workspace_card, workspace_layout = self._create_card("工作区")
        self.workspace_label = QLabel()
        self.workspace_label.setObjectName("WorkspacePath")
        self.workspace_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.workspace_label.setWordWrap(True)

        self.change_workspace_button = QPushButton("更改工作区")
        self.change_workspace_button.setObjectName("SecondaryButton")
        self.change_workspace_button.clicked.connect(self.on_change_workspace_clicked)
        self.cleanup_cache_button = QPushButton("清理缓存")
        self.cleanup_cache_button.setObjectName("SecondaryButton")
        self.cleanup_cache_button.clicked.connect(self.on_cleanup_cache_clicked)

        workspace_layout.addWidget(self.workspace_label)
        workspace_action_row = QHBoxLayout()
        workspace_action_row.setSpacing(8)
        workspace_action_row.addWidget(self.change_workspace_button)
        workspace_action_row.addWidget(self.cleanup_cache_button)
        workspace_action_row.addStretch(1)
        workspace_layout.addLayout(workspace_action_row)
        left_layout.addWidget(workspace_card)

        mic_card, mic_layout = self._create_card("麦克风")
        self.current_mic_label = QLabel("当前麦克风：未初始化")
        self.current_mic_label.setWordWrap(True)

        mic_row = QHBoxLayout()
        mic_row.setSpacing(8)
        self.microphone_combo = QComboBox()
        self.microphone_combo.currentIndexChanged.connect(self.on_microphone_changed)
        self.refresh_microphone_button = QPushButton("刷新")
        self.refresh_microphone_button.setObjectName("SecondaryButton")
        self.refresh_microphone_button.clicked.connect(self.on_refresh_microphones_clicked)
        mic_row.addWidget(self.microphone_combo, stretch=1)
        mic_row.addWidget(self.refresh_microphone_button)

        mic_layout.addWidget(self.current_mic_label)
        mic_layout.addLayout(mic_row)
        left_layout.addWidget(mic_card)

        action_card, action_layout = self._create_card("操作")
        self.import_button = QPushButton("导入音频")
        self.import_button.setObjectName("PrimaryButton")
        self.import_button.clicked.connect(self.on_import_clicked)

        self.start_record_button = QPushButton("开始录音")
        self.start_record_button.setObjectName("PrimaryButton")
        self.start_record_button.clicked.connect(self.on_start_record_clicked)

        self.stop_record_button = QPushButton("停止录音")
        self.stop_record_button.setObjectName("DangerButton")
        self.stop_record_button.clicked.connect(self.on_stop_record_clicked)

        action_layout.addWidget(self.import_button)
        action_layout.addWidget(self.start_record_button)
        action_layout.addWidget(self.stop_record_button)
        left_layout.addWidget(action_card)

        monitor_card, monitor_layout = self._create_card("录音监控")
        timer_row = QHBoxLayout()
        timer_row.setSpacing(8)
        timer_label = QLabel("录音时长")
        timer_label.setObjectName("MutedLabel")
        self.recording_timer_label = QLabel("00:00")
        self.recording_timer_label.setObjectName("TimerValue")
        timer_row.addWidget(timer_label)
        timer_row.addStretch(1)
        timer_row.addWidget(self.recording_timer_label)

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

        level_row.addWidget(level_label)
        level_row.addWidget(self.level_bar, stretch=1)
        level_row.addWidget(self.level_value_label)

        monitor_layout.addLayout(timer_row)
        monitor_layout.addLayout(level_row)
        left_layout.addWidget(monitor_card)

        status_card, status_layout = self._create_card("状态")
        self.status_label = QLabel("就绪。")
        self.status_label.setWordWrap(True)

        self.loading = QProgressBar()
        self.loading.setObjectName("BusyBar")
        self.loading.setRange(0, 0)
        self.loading.setVisible(False)
        self.loading.setTextVisible(False)

        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.loading)
        left_layout.addWidget(status_card)
        left_layout.addStretch(1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setSpacing(12)

        transcript_card, transcript_layout = self._create_card("转写结果")
        self.transcript_edit = QPlainTextEdit()
        self.transcript_edit.setObjectName("TranscriptEdit")
        self.transcript_edit.setReadOnly(True)
        self.transcript_edit.setPlaceholderText("转写结果将显示在这里。")

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.copy_button = QPushButton("复制")
        self.copy_button.setObjectName("SecondaryButton")
        self.copy_button.clicked.connect(self.on_copy_clicked)

        self.save_button = QPushButton("保存为 TXT")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.on_save_clicked)

        action_row.addWidget(self.copy_button)
        action_row.addWidget(self.save_button)
        action_row.addStretch(1)

        transcript_layout.addWidget(self.transcript_edit, stretch=1)
        transcript_layout.addLayout(action_row)
        right_layout.addWidget(transcript_card)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 7)

        self.setCentralWidget(container)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow {
                background: #f4f7fb;
                color: #1f2937;
                font-family: "PingFang SC", "SF Pro Text", "Helvetica Neue";
                font-size: 14px;
            }
            QFrame#Card {
                background: #ffffff;
                border: 1px solid #dfe5ef;
                border-radius: 12px;
            }
            QLabel#Title {
                font-size: 24px;
                font-weight: 700;
                color: #0f172a;
            }
            QLabel#Subtitle {
                font-size: 13px;
                color: #64748b;
            }
            QLabel#CardTitle {
                font-size: 15px;
                font-weight: 600;
                color: #0f172a;
                margin-bottom: 4px;
            }
            QLabel#WorkspacePath {
                color: #334155;
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px;
            }
            QLabel#MutedLabel {
                color: #64748b;
            }
            QLabel#TimerValue {
                font-size: 26px;
                font-weight: 700;
                color: #0f172a;
            }
            QPushButton {
                min-height: 36px;
                padding: 0 14px;
                border-radius: 8px;
                font-weight: 600;
                border: 1px solid transparent;
            }
            QPushButton#PrimaryButton {
                color: #ffffff;
                background: #2563eb;
            }
            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }
            QPushButton#SecondaryButton {
                color: #1e293b;
                background: #f8fafc;
                border-color: #cbd5e1;
            }
            QPushButton#SecondaryButton:hover {
                background: #eef2f7;
            }
            QPushButton#DangerButton {
                color: #ffffff;
                background: #dc2626;
            }
            QPushButton#DangerButton:hover {
                background: #b91c1c;
            }
            QPushButton:disabled {
                color: #94a3b8;
                background: #e2e8f0;
                border-color: #e2e8f0;
            }
            QComboBox,
            QPlainTextEdit {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background: #ffffff;
                padding: 6px;
            }
            QComboBox {
                min-height: 34px;
                padding: 0 36px 0 8px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 30px;
                border: none;
                border-left: 1px solid #cbd5e1;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
                background: #f8fafc;
            }
            QComboBox::down-arrow {
                image: none;
                width: 8px;
                height: 8px;
                border-right: 2px solid #475569;
                border-bottom: 2px solid #475569;
                margin-right: 10px;
                margin-top: -2px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                background: #ffffff;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
                outline: none;
            }
            QPlainTextEdit#TranscriptEdit {
                font-size: 14px;
                line-height: 1.6;
                selection-background-color: #bfdbfe;
            }
            QProgressBar#BusyBar {
                min-height: 8px;
                border-radius: 4px;
                border: 1px solid #dbe4f0;
                background: #eef2f7;
            }
            QProgressBar#BusyBar::chunk {
                background: #2563eb;
                border-radius: 4px;
            }
            QProgressBar#LevelBar {
                min-height: 10px;
                border-radius: 5px;
                border: 1px solid #cbd5e1;
                background: #edf2f7;
            }
            QProgressBar#LevelBar::chunk {
                background: #16a34a;
                border-radius: 5px;
            }
            """
        )

    def _create_card(self, title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        if title:
            title_label = QLabel(title)
            title_label.setObjectName("CardTitle")
            layout.addWidget(title_label)
        return card, layout

    @property
    def workspace_dir(self) -> Path:
        return Path(self.config.workspace_dir).expanduser().resolve()

    def _set_state(self, state: AppState, status_message: str | None = None) -> None:
        self.current_state = state

        is_idle = state == AppState.IDLE
        is_recording = state == AppState.RECORDING
        is_transcribing = state == AppState.TRANSCRIBING

        self.import_button.setEnabled(not is_recording and not is_transcribing)
        self.start_record_button.setEnabled(is_idle)
        self.stop_record_button.setEnabled(is_recording)
        self.change_workspace_button.setEnabled(not is_recording and not is_transcribing)
        self.cleanup_cache_button.setEnabled(not is_recording and not is_transcribing)
        self.microphone_combo.setEnabled(not is_recording and not is_transcribing and self.microphone_combo.count() > 0)
        self.refresh_microphone_button.setEnabled(not is_recording and not is_transcribing)

        has_text = bool(self.transcript_edit.toPlainText().strip())
        self.copy_button.setEnabled(has_text)
        self.save_button.setEnabled(has_text)

        self.loading.setVisible(is_transcribing)
        if status_message:
            self.status_label.setText(status_message)

    def _refresh_workspace_label(self) -> None:
        self.workspace_label.setText(str(self.workspace_dir))

    def _show_error(self, title: str, message: str) -> None:
        QMessageBox.critical(self, title, message)

    @staticmethod
    def _format_bytes(size_in_bytes: int) -> str:
        if size_in_bytes <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        value = float(size_in_bytes)
        for unit in units:
            if value < 1024 or unit == units[-1]:
                if unit == "B":
                    return f"{int(value)} {unit}"
                return f"{value:.1f} {unit}"
            value /= 1024
        return "0 B"

    def _refresh_microphone_options(self) -> None:
        current_config_index = self.config.input_device_index
        try:
            devices = self.audio_service.list_input_devices()
            default_index = self.audio_service.get_default_input_device()
        except AudioServiceError as exc:
            self.microphone_combo.blockSignals(True)
            self.microphone_combo.clear()
            self.microphone_combo.addItem("无法读取设备")
            self.microphone_combo.blockSignals(False)
            self.current_mic_label.setText("当前麦克风：读取失败")
            self.status_label.setText(str(exc))
            return

        self.microphone_combo.blockSignals(True)
        self.microphone_combo.clear()
        self.microphone_combo.addItem("系统默认", None)
        for device_index, device_name in devices:
            self.microphone_combo.addItem(f"[{device_index}] {device_name}", device_index)

        target_device = current_config_index
        if target_device is not None and target_device not in {idx for idx, _ in devices}:
            target_device = None
            self.config.input_device_index = None
            self.audio_service.set_input_device(None)
            self.config_service.save(self.config)

        if target_device is None:
            self.microphone_combo.setCurrentIndex(0)
            self.audio_service.set_input_device(None)
        else:
            combo_index = self.microphone_combo.findData(target_device)
            if combo_index >= 0:
                self.microphone_combo.setCurrentIndex(combo_index)
                self.audio_service.set_input_device(target_device)
            else:
                self.microphone_combo.setCurrentIndex(0)
                self.audio_service.set_input_device(None)

        self.microphone_combo.blockSignals(False)
        self._update_current_microphone_label(default_index=default_index)

    def _sync_microphone_selection_from_service(self) -> None:
        target_device = self.audio_service.input_device_index
        self.microphone_combo.blockSignals(True)
        if target_device is None:
            self.microphone_combo.setCurrentIndex(0)
        else:
            combo_index = self.microphone_combo.findData(target_device)
            if combo_index >= 0:
                self.microphone_combo.setCurrentIndex(combo_index)
            else:
                self.microphone_combo.setCurrentIndex(0)
                self.audio_service.set_input_device(None)
                target_device = None
        self.microphone_combo.blockSignals(False)

        self.config.input_device_index = target_device
        self.config_service.save(self.config)
        self._update_current_microphone_label()

    def _update_current_microphone_label(self, default_index: int | None = None) -> None:
        selected_device = self.audio_service.input_device_index
        if default_index is None:
            default_index = self.audio_service.get_default_input_device()

        if selected_device is None:
            if default_index is None:
                self.current_mic_label.setText("当前麦克风：系统默认（未检测到可用默认设备）")
            else:
                default_text = self.microphone_combo.itemText(self.microphone_combo.findData(default_index))
                if default_text:
                    self.current_mic_label.setText(f"当前麦克风：系统默认（{default_text}）")
                else:
                    self.current_mic_label.setText(f"当前麦克风：系统默认（设备索引 {default_index}）")
            return

        selected_text = self.microphone_combo.itemText(self.microphone_combo.findData(selected_device))
        if not selected_text:
            selected_text = f"设备索引 {selected_device}"
        self.current_mic_label.setText(f"当前麦克风：{selected_text}")

    def _start_recording_monitor(self) -> None:
        self._record_started_at = time.monotonic()
        self._recording_ui_timer.start()
        self._update_recording_indicators()

    def _reset_recording_monitor(self) -> None:
        self._recording_ui_timer.stop()
        self._record_started_at = None
        self.recording_timer_label.setText("00:00")
        self.level_bar.setValue(0)
        self.level_value_label.setText("0%")

    def _update_recording_indicators(self) -> None:
        if self._record_started_at is None:
            return

        elapsed = int(max(0, time.monotonic() - self._record_started_at))
        minutes, seconds = divmod(elapsed, 60)
        self.recording_timer_label.setText(f"{minutes:02d}:{seconds:02d}")

        rms, peak = self.audio_service.get_live_levels()
        level_percent = max(0, min(100, int(max(rms, peak) * 100)))
        self.level_bar.setValue(level_percent)
        self.level_value_label.setText(f"{level_percent}%")

    def on_refresh_microphones_clicked(self) -> None:
        self._refresh_microphone_options()
        self.status_label.setText("麦克风列表已刷新。")

    def on_microphone_changed(self, index: int) -> None:
        if index < 0:
            return
        device_index = self.microphone_combo.itemData(index)
        if device_index is None:
            self.audio_service.set_input_device(None)
            self.config.input_device_index = None
        else:
            self.audio_service.set_input_device(int(device_index))
            self.config.input_device_index = int(device_index)

        self.config_service.save(self.config)
        self._update_current_microphone_label()
        self.status_label.setText("麦克风已更新。")

    def _has_unsaved_transcript(self) -> bool:
        return bool(self.transcript_buffer and self.transcript_buffer.text.strip() and not self.transcript_buffer.is_saved)

    def _prompt_unsaved_transcript(self) -> bool:
        if not self._has_unsaved_transcript():
            return True

        choice = QMessageBox.question(
            self,
            "有未保存文本",
            "当前转写结果尚未保存，是否先保存再继续？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )

        if choice == QMessageBox.Cancel:
            return False

        if choice == QMessageBox.Save:
            return self._save_transcript_via_dialog()

        self._discard_current_transcript()
        return True

    def _discard_current_transcript(self) -> None:
        self.transcript_buffer = None
        self.transcript_edit.clear()
        self._set_state(self.current_state)

    def _save_transcript_via_dialog(self) -> bool:
        if not self.transcript_buffer:
            return False

        default_name = ensure_txt_filename(self.transcript_buffer.suggested_filename)
        default_path = self.workspace_dir / default_name

        selected_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存转写文本",
            str(default_path),
            "文本文件 (*.txt)",
        )
        if not selected_path:
            self.status_label.setText("已取消保存。")
            return False

        try:
            target_path = self.save_service.save_txt(self.transcript_buffer.text, Path(selected_path))
        except SaveServiceError as exc:
            self._show_error("保存失败", str(exc))
            return False

        self.transcript_buffer.is_saved = True
        self.transcript_buffer.suggested_filename = target_path.name
        self.status_label.setText(f"已保存：{target_path}")
        self._set_state(self.current_state)
        return True

    def on_change_workspace_clicked(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择工作区", str(self.workspace_dir))
        if not selected:
            return

        selected_path = Path(selected)
        if not self.config_service.is_workspace_valid(selected_path):
            self._show_error("工作区无效", "所选目录不可写。")
            return

        self.config.workspace_dir = str(selected_path.resolve())
        self.config_service.save(self.config)
        self._refresh_workspace_label()
        self.status_label.setText("工作区已更新。")

    def on_cleanup_cache_clicked(self) -> None:
        if self.current_state in {AppState.RECORDING, AppState.TRANSCRIBING}:
            self.status_label.setText("当前任务进行中，暂时无法清理缓存。")
            return

        try:
            orphan_wavs = self.cleanup_service.find_orphan_wavs(self.workspace_dir)
        except CleanupServiceError as exc:
            self._show_error("清理失败", str(exc))
            return

        if not orphan_wavs:
            self.status_label.setText("无需清理：未发现可删除的 WAV 缓存。")
            QMessageBox.information(self, "清理缓存", "未发现没有对应 TXT 的 WAV 文件。")
            return

        reclaim_estimate = 0
        for wav_path in orphan_wavs:
            try:
                reclaim_estimate += wav_path.stat().st_size
            except OSError:
                continue

        confirm = QMessageBox.question(
            self,
            "清理缓存",
            (
                f"检测到 {len(orphan_wavs)} 个没有对应 TXT 的 WAV 文件。\n"
                f"预计可释放 {self._format_bytes(reclaim_estimate)}。\n\n"
                "是否继续清理？"
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            self.status_label.setText("已取消缓存清理。")
            return

        try:
            result = self.cleanup_service.cleanup_orphan_wavs(self.workspace_dir)
        except CleanupServiceError as exc:
            self._show_error("清理失败", str(exc))
            return

        failed_count = len(result.failed_paths)
        reclaimed_text = self._format_bytes(result.reclaimed_bytes)
        if failed_count:
            QMessageBox.warning(
                self,
                "清理完成（部分失败）",
                (
                    f"已删除 {result.deleted_count}/{result.orphan_count} 个 WAV 文件，"
                    f"释放 {reclaimed_text}。\n"
                    f"仍有 {failed_count} 个文件删除失败，请检查文件权限。"
                ),
            )
        else:
            QMessageBox.information(
                self,
                "清理完成",
                f"已删除 {result.deleted_count} 个 WAV 文件，释放 {reclaimed_text}。",
            )
        self.status_label.setText(f"清理完成：删除 {result.deleted_count} 个 WAV，释放 {reclaimed_text}。")

    def on_import_clicked(self) -> None:
        if self.current_state == AppState.TRANSCRIBING:
            self.status_label.setText("转写进行中，请等待当前任务完成。")
            return

        if not self._prompt_unsaved_transcript():
            return

        selected, _ = QFileDialog.getOpenFileName(
            self,
            "选择音频文件",
            str(self.workspace_dir),
            "音频文件 (*.wav *.mp3 *.m4a *.flac)",
        )
        if not selected:
            return

        selected_path = Path(selected)
        suggested_filename = suggested_txt_filename_from_audio(selected_path)
        self._start_transcription(
            source_audio_path=selected_path,
            suggested_filename=suggested_filename,
            original_source_path=selected_path,
        )

    def on_start_record_clicked(self) -> None:
        if self.current_state != AppState.IDLE:
            return

        if not self._prompt_unsaved_transcript():
            return

        # Re-scan device list before every recording start to tolerate dynamic device index changes.
        self._refresh_microphone_options()
        is_device_ready, detail, switched = self.audio_service.ensure_input_device_available()
        if switched:
            self._sync_microphone_selection_from_service()
            self.status_label.setText(detail)

        if not is_device_ready:
            self.status_label.setText("麦克风不可用。")
            self._show_error(
                "无法开始录音",
                f"{detail}\n\n请检查系统麦克风权限，或切换到其他输入设备后重试。",
            )
            return

        try:
            self.audio_service.start_recording()
        except AudioServiceError as exc:
            self._show_error("录音失败", str(exc))
            return

        self._start_recording_monitor()
        self._set_state(AppState.RECORDING, "录音中... 点击“停止录音”结束。")

    def on_stop_record_clicked(self) -> None:
        if self.current_state != AppState.RECORDING:
            return

        output_wav = recording_wav_path(self.workspace_dir)
        try:
            saved_wav = self.audio_service.stop_and_save(output_wav)
        except AudioServiceError as exc:
            self._reset_recording_monitor()
            self._set_state(AppState.IDLE, "录音结束时发生错误。")
            self._show_error("录音失败", str(exc))
            return

        self._reset_recording_monitor()
        suggested_filename = suggested_txt_filename_from_audio(saved_wav)
        self._start_transcription(
            source_audio_path=saved_wav,
            suggested_filename=suggested_filename,
            original_source_path=saved_wav,
        )

    def _start_transcription(
        self,
        source_audio_path: Path,
        suggested_filename: str,
        original_source_path: Path,
    ) -> None:
        if self.current_state == AppState.TRANSCRIBING:
            self.status_label.setText("转写进行中，请等待当前任务完成。")
            return

        self._pending_suggested_filename = ensure_txt_filename(suggested_filename)
        self._pending_source_audio_path = str(original_source_path)

        request = TranscribeRequest(
            source_audio_path=str(source_audio_path),
            workspace_dir=str(self.workspace_dir),
            model_name=self.config.model_name,
            language=DEFAULT_LANGUAGE,
        )

        self._transcribe_thread = QThread(self)
        self._transcribe_worker = TranscribeWorker(self.transcribe_service, self.convert_service, request)
        self._transcribe_worker.moveToThread(self._transcribe_thread)

        self._transcribe_thread.started.connect(self._transcribe_worker.run)
        self._transcribe_worker.started.connect(self._on_transcribe_started)
        self._transcribe_worker.stage_changed.connect(self._on_transcribe_stage_changed)
        self._transcribe_worker.finished.connect(self._on_transcribe_finished)
        self._transcribe_worker.failed.connect(self._on_transcribe_failed)

        self._transcribe_worker.finished.connect(self._transcribe_thread.quit)
        self._transcribe_worker.failed.connect(self._transcribe_thread.quit)
        self._transcribe_worker.finished.connect(self._transcribe_worker.deleteLater)
        self._transcribe_worker.failed.connect(self._transcribe_worker.deleteLater)
        self._transcribe_thread.finished.connect(self._transcribe_thread.deleteLater)
        self._transcribe_thread.finished.connect(self._clear_transcribe_refs)

        self._set_state(AppState.TRANSCRIBING, "正在准备音频...")
        self._transcribe_thread.start()

    def _on_transcribe_started(self) -> None:
        self._set_state(AppState.TRANSCRIBING, "正在准备音频...")

    def _on_transcribe_stage_changed(self, stage: str) -> None:
        if stage == "converting":
            self._set_state(AppState.TRANSCRIBING, "正在准备音频...")
            return
        if stage == "transcribing":
            self._set_state(AppState.TRANSCRIBING, "正在转写...")

    def _on_transcribe_finished(self, result: TranscribeResult) -> None:
        self.transcript_edit.setPlainText(result.text)
        self.transcript_buffer = TranscriptBuffer(
            text=result.text,
            source_audio_path=self._pending_source_audio_path,
            suggested_filename=self._pending_suggested_filename,
            is_saved=False,
        )
        self._set_state(
            AppState.IDLE,
            f"转写完成，用时 {result.duration_sec:.2f} 秒。尚未保存。",
        )

    def _on_transcribe_failed(self, error_message: str) -> None:
        self._set_state(AppState.IDLE, "转写失败。")
        self._show_error("转写失败", error_message)

    def _clear_transcribe_refs(self) -> None:
        self._transcribe_thread = None
        self._transcribe_worker = None

    def on_copy_clicked(self) -> None:
        text = self.transcript_edit.toPlainText()
        if not text.strip():
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.status_label.setText("已复制到剪贴板。")

    def on_save_clicked(self) -> None:
        if not self.transcript_buffer:
            return
        self._save_transcript_via_dialog()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.current_state == AppState.TRANSCRIBING:
            QMessageBox.information(self, "任务进行中", "当前正在转写，请等待完成后再关闭。")
            event.ignore()
            return

        if self.current_state == AppState.RECORDING:
            choice = QMessageBox.question(
                self,
                "录音进行中",
                "当前正在录音，是否停止录音并退出？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                event.ignore()
                return
            self.audio_service.abort_recording()
            self._reset_recording_monitor()

        if not self._prompt_unsaved_transcript():
            event.ignore()
            return

        event.accept()
