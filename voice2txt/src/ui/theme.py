"""集中管理应用样式、配色和视觉效果。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect, QWidget


# ---------------------------------------------------------------------------
# 配色常量
# ---------------------------------------------------------------------------

PRIMARY = "#2563eb"
PRIMARY_HOVER = "#1d4ed8"
DANGER = "#dc2626"
DANGER_HOVER = "#b91c1c"
SUCCESS = "#16a34a"
WARNING = "#f59e0b"

BG_BASE = "#f0f4f8"
BG_CARD = "#ffffff"
BORDER_CARD = "#e2e8f0"
BORDER_INPUT = "#cbd5e1"

TEXT_PRIMARY = "#0f172a"
TEXT_BODY = "#1f2937"
TEXT_SECONDARY = "#334155"
TEXT_MUTED = "#64748b"
TEXT_DISABLED = "#94a3b8"

RECORDING_BORDER = "#ef4444"

# ---------------------------------------------------------------------------
# 卡片阴影
# ---------------------------------------------------------------------------


def apply_card_shadow(widget: QWidget, blur: int = 18, offset_y: int = 3) -> None:
    """给 widget 添加柔和的投影效果。"""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, offset_y)
    shadow.setColor(QColor(15, 23, 42, 22))
    widget.setGraphicsEffect(shadow)


# ---------------------------------------------------------------------------
# 全局 QSS 样式表
# ---------------------------------------------------------------------------

APP_STYLESHEET = f"""
/* ---- 主窗口 ---- */
QMainWindow {{
    background: {BG_BASE};
    color: {TEXT_BODY};
    font-family: "PingFang SC", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 14px;
}}

/* ---- 卡片 ---- */
QFrame#Card {{
    background: {BG_CARD};
    border: 1px solid {BORDER_CARD};
    border-radius: 14px;
}}
QFrame#CardRecording {{
    background: {BG_CARD};
    border: 2px solid {RECORDING_BORDER};
    border-radius: 14px;
}}

/* ---- 标题 ---- */
QLabel#Title {{
    font-size: 22px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    letter-spacing: 0.3px;
}}
QLabel#Subtitle {{
    font-size: 13px;
    color: {TEXT_MUTED};
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
    margin-bottom: 2px;
}}

/* ---- 标签 ---- */
QLabel#WorkspacePath {{
    color: {TEXT_SECONDARY};
    background: #f8fafc;
    border: 1px solid {BORDER_CARD};
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12px;
}}
QLabel#MutedLabel {{
    color: {TEXT_MUTED};
    font-size: 13px;
}}
QLabel#TimerValue {{
    font-size: 28px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    font-variant-numeric: tabular-nums;
}}
QLabel#EmptyHint {{
    color: {TEXT_MUTED};
    font-size: 15px;
}}
QLabel#WordCount {{
    color: {TEXT_MUTED};
    font-size: 12px;
}}

/* ---- 按钮通用 ---- */
QPushButton {{
    min-height: 36px;
    padding: 0 16px;
    border-radius: 8px;
    font-weight: 600;
    font-size: 13px;
    border: 1px solid transparent;
}}
QPushButton#PrimaryButton {{
    color: #ffffff;
    background: {PRIMARY};
}}
QPushButton#PrimaryButton:hover {{
    background: {PRIMARY_HOVER};
}}
QPushButton#PrimaryButton:pressed {{
    background: #1e40af;
}}
QPushButton#SecondaryButton {{
    color: {TEXT_PRIMARY};
    background: #f8fafc;
    border-color: {BORDER_INPUT};
}}
QPushButton#SecondaryButton:hover {{
    background: #eef2f7;
    border-color: #94a3b8;
}}
QPushButton#SecondaryButton:pressed {{
    background: #e2e8f0;
}}
QPushButton#DangerButton {{
    color: #ffffff;
    background: {DANGER};
}}
QPushButton#DangerButton:hover {{
    background: {DANGER_HOVER};
}}
QPushButton#DangerButton:pressed {{
    background: #991b1b;
}}
QPushButton:disabled {{
    color: {TEXT_DISABLED};
    background: #e2e8f0;
    border-color: #e2e8f0;
}}

/* ---- 输入控件 ---- */
QComboBox,
QPlainTextEdit {{
    border: 1px solid {BORDER_INPUT};
    border-radius: 8px;
    background: {BG_CARD};
    padding: 6px;
    font-size: 13px;
}}
QComboBox {{
    min-height: 34px;
    padding: 0 36px 0 10px;
}}
QComboBox:focus,
QPlainTextEdit:focus {{
    border-color: {PRIMARY};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border: none;
    border-left: 1px solid {BORDER_INPUT};
    border-top-right-radius: 8px;
    border-bottom-right-radius: 8px;
    background: #f8fafc;
}}
QComboBox::down-arrow {{
    image: none;
    width: 8px;
    height: 8px;
    border-right: 2px solid #475569;
    border-bottom: 2px solid #475569;
    margin-right: 10px;
    margin-top: -2px;
}}
QComboBox QAbstractItemView {{
    border: 1px solid {BORDER_INPUT};
    border-radius: 8px;
    background: {BG_CARD};
    selection-background-color: #dbeafe;
    selection-color: {TEXT_PRIMARY};
    outline: none;
    padding: 4px;
}}

/* ---- 转写结果编辑区 ---- */
QPlainTextEdit#TranscriptEdit {{
    font-size: 14px;
    line-height: 1.7;
    selection-background-color: #bfdbfe;
    padding: 10px;
}}

/* ---- 进度条 ---- */
QProgressBar#BusyBar {{
    min-height: 6px;
    max-height: 6px;
    border-radius: 3px;
    border: none;
    background: #e2e8f0;
}}
QProgressBar#BusyBar::chunk {{
    background: {PRIMARY};
    border-radius: 3px;
}}
QProgressBar#LevelBar {{
    min-height: 10px;
    max-height: 10px;
    border-radius: 5px;
    border: 1px solid {BORDER_INPUT};
    background: #f1f5f9;
}}
QProgressBar#LevelBar::chunk {{
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 {SUCCESS},
        stop:0.6 #facc15,
        stop:1.0 {DANGER}
    );
    border-radius: 5px;
}}

/* ---- Splitter ---- */
QSplitter::handle:horizontal {{
    background: {BORDER_CARD};
    width: 2px;
    margin: 40px 3px;
    border-radius: 1px;
}}
"""
