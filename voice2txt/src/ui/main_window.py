"""应用主窗口，编排各子组件与服务交互。"""

from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from src.constants import APP_TITLE, DEFAULT_LANGUAGE, SUPPORTED_IMPORT_SUFFIXES
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
from src.ui.recording_monitor import RecordingMonitor
from src.ui.theme import APP_STYLESHEET, apply_card_shadow
from src.ui.transcript_panel import TranscriptPanel
from src.workers.transcribe_worker import TranscribeWorker


class MainWindow(QMainWindow):
    def __init__(self, config_service: ConfigService, config: AppConfig) -> None:
        super().__init__()
        self.config_service = config_service
        self.config = config

        # ---- 服务 ----
        self.audio_service = AudioService(sample_rate=config.sample_rate, channels=config.channels)
        self.audio_service.set_input_device(config.input_device_index)
        self.cleanup_service = CleanupService()
        self.convert_service = ConvertService(sample_rate=config.sample_rate, channels=config.channels)
        self.transcribe_service = TranscribeService(default_model_name=config.model_name)
        self.save_service = SaveService()

        # ---- 状态 ----
        self.current_state = AppState.IDLE
        self.transcript_buffer: TranscriptBuffer | None = None
        self._transcribe_thread: QThread | None = None
        self._transcribe_worker: TranscribeWorker | None = None
        self._pending_suggested_filename = "转写结果.txt"
        self._pending_source_audio_path = ""

        # ---- 窗口基本属性 ----
        self.setWindowTitle(APP_TITLE)
        self.resize(1120, 720)
        self.setAcceptDrops(True)
        self.setStyleSheet(APP_STYLESHEET)

        self._build_ui()
        self._setup_shortcuts()
        self._refresh_workspace_label()
        self._refresh_microphone_options()
        self._set_state(AppState.IDLE, "\u2713  就绪")

    # ==================================================================
    # UI 构建
    # ==================================================================

    def _build_ui(self) -> None:
        container = QWidget(self)
        root_layout = QHBoxLayout(container)
        root_layout.setContentsMargins(16, 16, 16, 16)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)
        root_layout.addWidget(splitter)

        # ---- 左侧面板 ----
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)

        left_layout.addWidget(self._build_header_card())
        left_layout.addWidget(self._build_workspace_card())
        left_layout.addWidget(self._build_mic_card())
        left_layout.addWidget(self._build_action_card())

        self.recording_monitor = RecordingMonitor(self.audio_service)
        left_layout.addWidget(self.recording_monitor)

        left_layout.addWidget(self._build_status_card())
        left_layout.addStretch(1)

        # ---- 右侧面板 ----
        self.transcript_panel = TranscriptPanel()
        self.transcript_panel.copy_requested.connect(self.on_copy_clicked)
        self.transcript_panel.save_requested.connect(self.on_save_clicked)

        splitter.addWidget(left_panel)
        splitter.addWidget(self.transcript_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 7)

        self.setCentralWidget(container)

    def _build_header_card(self) -> QFrame:
        card, layout = _create_card()
        title = QLabel("\U0001F399\uFE0F  语音转写助手")
        title.setObjectName("Title")
        subtitle = QLabel("本地录音与音频转写工作台  \u00B7  支持拖放导入")
        subtitle.setObjectName("Subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        return card

    def _build_workspace_card(self) -> QFrame:
        card, layout = _create_card("\U0001F4C2  工作区")
        self.workspace_label = QLabel()
        self.workspace_label.setObjectName("WorkspacePath")
        self.workspace_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.workspace_label.setWordWrap(True)
        layout.addWidget(self.workspace_label)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.change_workspace_button = QPushButton("更改工作区")
        self.change_workspace_button.setObjectName("SecondaryButton")
        self.change_workspace_button.clicked.connect(self.on_change_workspace_clicked)
        self.cleanup_cache_button = QPushButton("\U0001F5D1  清理缓存")
        self.cleanup_cache_button.setObjectName("SecondaryButton")
        self.cleanup_cache_button.clicked.connect(self.on_cleanup_cache_clicked)
        row.addWidget(self.change_workspace_button)
        row.addWidget(self.cleanup_cache_button)
        row.addStretch(1)
        layout.addLayout(row)
        return card

    def _build_mic_card(self) -> QFrame:
        card, layout = _create_card("\U0001F3A4  麦克风")
        self.current_mic_label = QLabel("当前麦克风：未初始化")
        self.current_mic_label.setObjectName("MutedLabel")
        self.current_mic_label.setWordWrap(True)
        layout.addWidget(self.current_mic_label)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.microphone_combo = QComboBox()
        self.microphone_combo.currentIndexChanged.connect(self.on_microphone_changed)
        self.refresh_microphone_button = QPushButton("\u21BB  刷新")
        self.refresh_microphone_button.setObjectName("SecondaryButton")
        self.refresh_microphone_button.clicked.connect(self.on_refresh_microphones_clicked)
        row.addWidget(self.microphone_combo, stretch=1)
        row.addWidget(self.refresh_microphone_button)
        layout.addLayout(row)
        return card

    def _build_action_card(self) -> QFrame:
        card, layout = _create_card("\u26A1  操作")

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        self.import_button = QPushButton("\U0001F4C1  导入音频")
        self.import_button.setObjectName("PrimaryButton")
        self.import_button.clicked.connect(self.on_import_clicked)
        self.start_record_button = QPushButton("\u23FA  开始录音")
        self.start_record_button.setObjectName("PrimaryButton")
        self.start_record_button.clicked.connect(self.on_start_record_clicked)
        row1.addWidget(self.import_button)
        row1.addWidget(self.start_record_button)
        layout.addLayout(row1)

        self.stop_record_button = QPushButton("\u23F9  停止录音")
        self.stop_record_button.setObjectName("DangerButton")
        self.stop_record_button.clicked.connect(self.on_stop_record_clicked)
        layout.addWidget(self.stop_record_button)
        return card

    def _build_status_card(self) -> QFrame:
        card, layout = _create_card()
        self.status_label = QLabel("\u2713  就绪")
        self.status_label.setObjectName("MutedLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.loading = QProgressBar()
        self.loading.setObjectName("BusyBar")
        self.loading.setRange(0, 0)
        self.loading.setVisible(False)
        self.loading.setTextVisible(False)
        layout.addWidget(self.loading)
        return card

    # ==================================================================
    # 快捷键
    # ==================================================================

    def _setup_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.on_import_clicked)
        QShortcut(QKeySequence("Ctrl+R"), self).activated.connect(self._toggle_recording)
        QShortcut(QKeySequence("Ctrl+S"), self).activated.connect(self.on_save_clicked)

    def _toggle_recording(self) -> None:
        if self.current_state == AppState.RECORDING:
            self.on_stop_record_clicked()
        elif self.current_state == AppState.IDLE:
            self.on_start_record_clicked()

    # ==================================================================
    # 拖放支持
    # ==================================================================

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._is_busy:
            return
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED_IMPORT_SUFFIXES:
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent) -> None:
        if self._is_busy:
            self.status_label.setText("\u26A0  当前任务进行中，无法导入")
            return
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            file_path = Path(url.toLocalFile())
            if file_path.suffix.lower() not in SUPPORTED_IMPORT_SUFFIXES:
                continue
            event.acceptProposedAction()
            self._import_audio_file(file_path)
            return

    # ==================================================================
    # 状态管理
    # ==================================================================

    @property
    def workspace_dir(self) -> Path:
        return Path(self.config.workspace_dir).expanduser().resolve()

    @property
    def _is_busy(self) -> bool:
        return self.current_state in {AppState.RECORDING, AppState.TRANSCRIBING}

    def _set_state(self, state: AppState, status_message: str | None = None) -> None:
        self.current_state = state

        is_idle = state == AppState.IDLE
        is_recording = state == AppState.RECORDING
        is_transcribing = state == AppState.TRANSCRIBING
        is_busy = is_recording or is_transcribing

        self.import_button.setEnabled(not is_busy)
        self.start_record_button.setEnabled(is_idle)
        self.stop_record_button.setEnabled(is_recording)
        self.change_workspace_button.setEnabled(not is_busy)
        self.cleanup_cache_button.setEnabled(not is_busy)
        has_devices = self.microphone_combo.count() > 0
        self.microphone_combo.setEnabled(not is_busy and has_devices)
        self.refresh_microphone_button.setEnabled(not is_busy)

        has_text = bool(self.transcript_panel.get_text().strip())
        self.transcript_panel.set_buttons_enabled(has_text)

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
                return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        return "0 B"

    # ==================================================================
    # 麦克风管理
    # ==================================================================

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

    # ==================================================================
    # 事件处理
    # ==================================================================

    def on_refresh_microphones_clicked(self) -> None:
        self._refresh_microphone_options()
        self.status_label.setText("\u21BB  麦克风列表已刷新")

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
        self.status_label.setText("\u2713  麦克风已更新")

    # ---- 未保存文本 ----

    def _has_unsaved_transcript(self) -> bool:
        return bool(
            self.transcript_buffer
            and self.transcript_buffer.text.strip()
            and not self.transcript_buffer.is_saved
        )

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
        self.transcript_panel.clear_text()
        self._set_state(self.current_state)

    def _save_transcript_via_dialog(self) -> bool:
        if not self.transcript_buffer:
            return False
        default_name = ensure_txt_filename(self.transcript_buffer.suggested_filename)
        default_path = self.workspace_dir / default_name
        selected_path, _ = QFileDialog.getSaveFileName(
            self, "保存转写文本", str(default_path), "文本文件 (*.txt)",
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
        self.status_label.setText(f"\u2713  已保存：{target_path}")
        self._set_state(self.current_state)
        return True

    # ---- 工作区 ----

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
        self.status_label.setText("\u2713  工作区已更新")

    # ---- 缓存清理 ----

    def on_cleanup_cache_clicked(self) -> None:
        if self.current_state in {AppState.RECORDING, AppState.TRANSCRIBING}:
            self.status_label.setText("\u26A0  当前任务进行中，暂时无法清理缓存")
            return
        try:
            orphan_wavs = self.cleanup_service.find_orphan_wavs(self.workspace_dir)
        except CleanupServiceError as exc:
            self._show_error("清理失败", str(exc))
            return
        if not orphan_wavs:
            self.status_label.setText("\u2713  无需清理：未发现可删除的 WAV 缓存")
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

        result = self.cleanup_service.delete_wavs(orphan_wavs)
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
        self.status_label.setText(f"\u2713  清理完成：删除 {result.deleted_count} 个 WAV，释放 {reclaimed_text}")

    # ---- 导入 ----

    def on_import_clicked(self) -> None:
        if self._is_busy:
            self.status_label.setText("\u26A0  当前任务进行中，请等待完成")
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
        self._import_audio_file(Path(selected))

    def _import_audio_file(self, file_path: Path) -> None:
        if self._is_busy:
            self.status_label.setText("\u26A0  当前任务进行中，请等待完成")
            return
        if not self._prompt_unsaved_transcript():
            return
        suggested_filename = suggested_txt_filename_from_audio(file_path)
        self._start_transcription(
            source_audio_path=file_path,
            suggested_filename=suggested_filename,
            original_source_path=file_path,
        )

    # ---- 录音 ----

    def on_start_record_clicked(self) -> None:
        if self.current_state != AppState.IDLE:
            return
        if not self._prompt_unsaved_transcript():
            return
        self._refresh_microphone_options()
        is_device_ready, detail, switched = self.audio_service.ensure_input_device_available()
        if switched:
            self._sync_microphone_selection_from_service()
            self.status_label.setText(detail)
        if not is_device_ready:
            self.status_label.setText("\u26A0  麦克风不可用")
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
        self.recording_monitor.start()
        self._set_state(AppState.RECORDING, "\u23FA  录音中\u2026 点击「停止录音」或按 Ctrl+R 结束")

    def on_stop_record_clicked(self) -> None:
        if self.current_state != AppState.RECORDING:
            return
        output_wav = recording_wav_path(self.workspace_dir)
        try:
            saved_wav = self.audio_service.stop_and_save(output_wav)
        except AudioServiceError as exc:
            self.recording_monitor.reset()
            self._set_state(AppState.IDLE, "\u26A0  录音结束时发生错误")
            self._show_error("录音失败", str(exc))
            return
        self.recording_monitor.reset()
        self._set_state(AppState.IDLE)
        suggested_filename = suggested_txt_filename_from_audio(saved_wav)
        self._start_transcription(
            source_audio_path=saved_wav,
            suggested_filename=suggested_filename,
            original_source_path=saved_wav,
        )

    # ==================================================================
    # 转写流程
    # ==================================================================

    def _start_transcription(
        self,
        source_audio_path: Path,
        suggested_filename: str,
        original_source_path: Path,
    ) -> None:
        if self._is_busy:
            self.status_label.setText("\u26A0  当前任务进行中，请等待完成")
            return
        self._pending_suggested_filename = ensure_txt_filename(suggested_filename)
        self._pending_source_audio_path = str(original_source_path)

        request = TranscribeRequest(
            source_audio_path=str(source_audio_path),
            workspace_dir=str(self.workspace_dir),
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

        self._set_state(AppState.TRANSCRIBING, "\u23F3  正在准备音频\u2026")
        self._transcribe_thread.start()

    def _on_transcribe_started(self) -> None:
        self._set_state(AppState.TRANSCRIBING, "\u23F3  正在准备音频\u2026")

    def _on_transcribe_stage_changed(self, stage: str) -> None:
        if stage == "converting":
            self._set_state(AppState.TRANSCRIBING, "\u23F3  正在准备音频\u2026")
        elif stage == "transcribing":
            self._set_state(AppState.TRANSCRIBING, "\u23F3  正在转写\u2026")

    def _on_transcribe_finished(self, result: TranscribeResult) -> None:
        self.transcript_panel.set_text(result.text)
        self.transcript_buffer = TranscriptBuffer(
            text=result.text,
            source_audio_path=self._pending_source_audio_path,
            suggested_filename=self._pending_suggested_filename,
            is_saved=False,
        )
        self._set_state(
            AppState.IDLE,
            f"\u2713  转写完成，用时 {result.duration_sec:.2f} 秒（尚未保存）",
        )

    def _on_transcribe_failed(self, error_message: str) -> None:
        self._set_state(AppState.IDLE, "\u2717  转写失败")
        self._show_error("转写失败", error_message)

    def _clear_transcribe_refs(self) -> None:
        self._transcribe_thread = None
        self._transcribe_worker = None

    # ---- 复制 / 保存 ----

    def on_copy_clicked(self) -> None:
        text = self.transcript_panel.get_text()
        if not text.strip():
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self.status_label.setText("\u2713  已复制到剪贴板")

    def on_save_clicked(self) -> None:
        if not self.transcript_buffer:
            return
        self._save_transcript_via_dialog()

    # ==================================================================
    # 窗口关闭
    # ==================================================================

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
            self.recording_monitor.reset()
        if not self._prompt_unsaved_transcript():
            event.ignore()
            return
        event.accept()


# ======================================================================
# 工具函数
# ======================================================================


def _create_card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    if title:
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        layout.addWidget(title_label)
    apply_card_shadow(card)
    return card, layout
