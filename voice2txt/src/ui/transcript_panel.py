"""转录结果面板：展示转录文本、复制/保存按钮和字数统计。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from src.ui.theme import apply_card_shadow


class TranscriptPanel(QFrame):
    """独立的转录结果展示面板。"""

    copy_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._build_ui()
        apply_card_shadow(self)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        card_title = QLabel("\U0001F4DD  转写结果")
        card_title.setObjectName("CardTitle")
        layout.addWidget(card_title)

        self.transcript_edit = QPlainTextEdit()
        self.transcript_edit.setObjectName("TranscriptEdit")
        self.transcript_edit.setReadOnly(True)
        self.transcript_edit.setPlaceholderText(
            "转写结果将显示在这里\u2026\n\n"
            "\u2022 点击左侧「导入音频」选择文件\n"
            "\u2022 或点击「开始录音」后说话"
        )
        self.transcript_edit.textChanged.connect(self._on_text_changed)
        layout.addWidget(self.transcript_edit, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        self.word_count_label = QLabel("")
        self.word_count_label.setObjectName("WordCount")
        bottom_row.addWidget(self.word_count_label)
        bottom_row.addStretch(1)

        self.copy_button = QPushButton("\U0001F4CB  复制")
        self.copy_button.setObjectName("SecondaryButton")
        self.copy_button.clicked.connect(self.copy_requested.emit)

        self.save_button = QPushButton("\U0001F4BE  保存为 TXT")
        self.save_button.setObjectName("PrimaryButton")
        self.save_button.clicked.connect(self.save_requested.emit)

        bottom_row.addWidget(self.copy_button)
        bottom_row.addWidget(self.save_button)
        layout.addLayout(bottom_row)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def set_text(self, text: str) -> None:
        self.transcript_edit.setPlainText(text)

    def get_text(self) -> str:
        return self.transcript_edit.toPlainText()

    def clear_text(self) -> None:
        self.transcript_edit.clear()

    def set_buttons_enabled(self, enabled: bool) -> None:
        self.copy_button.setEnabled(enabled)
        self.save_button.setEnabled(enabled)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _on_text_changed(self) -> None:
        text = self.transcript_edit.toPlainText().strip()
        if not text:
            self.word_count_label.setText("")
            return
        words = len(text.split())
        chars = len(text)
        self.word_count_label.setText(f"{words} 词  ·  {chars} 字符")
