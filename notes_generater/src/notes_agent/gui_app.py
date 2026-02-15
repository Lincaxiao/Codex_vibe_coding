from __future__ import annotations

import json
import traceback
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .check_runner import CheckRunner
from .cache_service import CacheService
from .codex_executor import CodexExecutor
from .feedback_service import FeedbackService
from .gui_settings import load_gui_settings, save_gui_settings
from .lecture_registry_service import LectureRegistryService
from .models import CreateProjectRequest, ProjectConfig
from .prompt_template_service import DEFAULT_PROMPT_TEMPLATES, PROMPT_TEMPLATE_KEYS, PromptTemplateService
from .project_service import PROJECT_REL_PATH, ProjectService, slugify_course_id
from .round0_initializer import Round0Initializer
from .run_history_service import RunHistoryService
from .workflow_orchestrator import WorkflowOrchestrator

ROUND_VALUES = ["round0", "round1", "round2", "round3", "final"]


def _to_json(payload: Any) -> str:
    if hasattr(payload, "to_dict"):
        payload = payload.to_dict()
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _safe_int(value: str, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _now_time() -> str:
    return datetime.now().strftime("%H:%M:%S")


def main() -> int:
    try:
        from PySide6.QtCore import QObject, QThread, Signal, Qt
        from PySide6.QtWidgets import (
            QApplication,
            QFileDialog,
            QFrame,
            QGridLayout,
            QGroupBox,
            QHBoxLayout,
            QLabel,
            QLineEdit,
            QListWidget,
            QMainWindow,
            QMessageBox,
            QPushButton,
            QPlainTextEdit,
            QComboBox,
            QStackedWidget,
            QTabWidget,
            QVBoxLayout,
            QWidget,
            QCheckBox,
        )
    except ImportError as exc:
        print("图形界面模式依赖 PySide6，请先执行: pip install '.[gui]'")
        print(f"导入失败: {exc}")
        return 1

    class TaskWorker(QObject):  # type: ignore[misc]
        finished = Signal(object)
        failed = Signal(str)
        progress = Signal(str)

        def __init__(self, fn: Callable[[Callable[[str], None]], Any]) -> None:
            super().__init__()
            self._fn = fn

        def run(self) -> None:
            try:
                result = self._fn(self._emit_progress)
                self.finished.emit(result)
            except Exception as exc:
                if isinstance(exc, ValueError):
                    self.failed.emit(str(exc))
                else:
                    self.failed.emit(traceback.format_exc())

        def _emit_progress(self, message: str) -> None:
            self.progress.emit(message)

    class MainWindow(QMainWindow):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("课程笔记助手")
            self.resize(1320, 860)

            self.project_service = ProjectService()
            self.round0_initializer = Round0Initializer()
            self.check_runner = CheckRunner()
            self.cache_service = CacheService()
            self.feedback_service = FeedbackService()
            self.run_history_service = RunHistoryService()
            self.lecture_registry_service = LectureRegistryService()
            self.prompt_template_service = PromptTemplateService()
            self.codex_executor = CodexExecutor(exec_timeout_seconds=10 * 60)
            self.workflow_orchestrator = WorkflowOrchestrator(
                project_service=self.project_service,
                codex_executor=self.codex_executor,
                check_runner=self.check_runner,
                round0_initializer=self.round0_initializer,
                prompt_template_service=self.prompt_template_service,
            )
            self.current_config: ProjectConfig | None = None
            self._threads: list[QThread] = []
            self._workers: list[TaskWorker] = []
            self.settings = load_gui_settings()
            self.nav_buttons: list[QPushButton] = []
            self.prompt_editors: dict[str, QPlainTextEdit] = {}
            self.lecture_entries: dict[str, list[str]] = {}

            self._build_ui()
            self._apply_theme()
            self._apply_settings()
            self._load_prompt_templates_for_current_project()
            self._switch_page(0)
            self._log("界面初始化完成")

        def _build_ui(self) -> None:
            root = QWidget(objectName="AppRoot")
            root_layout = QHBoxLayout(root)
            root_layout.setContentsMargins(16, 16, 16, 16)
            root_layout.setSpacing(14)

            sidebar = QFrame(objectName="Sidebar")
            sidebar.setFixedWidth(230)
            sidebar_layout = QVBoxLayout(sidebar)
            sidebar_layout.setContentsMargins(18, 22, 18, 18)
            sidebar_layout.setSpacing(10)

            title = QLabel("课程笔记助手", objectName="BrandTitle")
            subtitle = QLabel("本地多轮生成工作台", objectName="BrandSubtitle")
            sidebar_layout.addWidget(title)
            sidebar_layout.addWidget(subtitle)

            self._add_nav_button(sidebar_layout, "项目", 0)
            self._add_nav_button(sidebar_layout, "讲次", 1)
            self._add_nav_button(sidebar_layout, "流程", 2)
            self._add_nav_button(sidebar_layout, "审阅", 3)
            self._add_nav_button(sidebar_layout, "提示词", 4)
            self._add_nav_button(sidebar_layout, "运行记录", 5)
            sidebar_layout.addStretch(1)
            sidebar_layout.addWidget(QLabel("macOS 本地模式", objectName="SidebarFootnote"))

            main_panel = QFrame(objectName="MainPanel")
            main_layout = QVBoxLayout(main_panel)
            main_layout.setContentsMargins(10, 10, 10, 10)
            main_layout.setSpacing(12)

            header = QFrame(objectName="HeaderCard")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(16, 12, 16, 12)
            header_layout.setSpacing(12)
            self.header_title = QLabel("尚未加载项目", objectName="HeaderTitle")
            self.header_subtitle = QLabel("请先在“项目”页创建或加载", objectName="HeaderSubtitle")
            title_box = QVBoxLayout()
            title_box.setSpacing(2)
            title_box.addWidget(self.header_title)
            title_box.addWidget(self.header_subtitle)
            header_layout.addLayout(title_box, 1)
            self.status_badge = QLabel("空闲", objectName="StatusBadge")
            header_layout.addWidget(self.status_badge, 0, Qt.AlignRight | Qt.AlignVCenter)  # type: ignore[arg-type]

            self.page_stack = QStackedWidget(objectName="PageStack")
            self.page_stack.addWidget(self._build_project_page())
            self.page_stack.addWidget(self._build_lecture_page())
            self.page_stack.addWidget(self._build_workflow_page())
            self.page_stack.addWidget(self._build_review_page())
            self.page_stack.addWidget(self._build_prompt_page())
            self.page_stack.addWidget(self._build_runs_page())

            log_card = QFrame(objectName="LogCard")
            log_layout = QVBoxLayout(log_card)
            log_layout.setContentsMargins(12, 10, 12, 10)
            log_layout.setSpacing(8)
            self.status_label = QLabel("空闲", objectName="StatusLine")
            self.output = QPlainTextEdit()
            self.output.setReadOnly(True)
            self.output.setPlaceholderText("运行日志...")
            log_layout.addWidget(self.status_label)
            log_layout.addWidget(self.output, 1)

            main_layout.addWidget(header)
            main_layout.addWidget(self.page_stack, 1)
            main_layout.addWidget(log_card, 1)

            root_layout.addWidget(sidebar)
            root_layout.addWidget(main_panel, 1)
            self.setCentralWidget(root)

        def _build_project_page(self) -> QWidget:
            page = QFrame(objectName="PageCard")
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            heading = QLabel("项目设置", objectName="PageHeading")
            hint = QLabel("选择课程根目录后，创建或加载单课程项目。", objectName="PageHint")
            layout.addWidget(heading)
            layout.addWidget(hint)

            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)

            self.course_root_edit = QLineEdit()
            self.course_edit = QLineEdit()
            self.project_root_edit = QLineEdit()
            self.project_root_edit.setReadOnly(True)
            self.notes_root_edit = QLineEdit()
            self.notes_root_edit.setReadOnly(True)

            browse_btn = QPushButton("选择课程目录")
            browse_btn.clicked.connect(self._on_browse_course_root)
            create_btn = QPushButton("创建或加载项目")
            create_btn.clicked.connect(self._on_create_or_load_project)

            grid.addWidget(QLabel("课程根目录"), 0, 0)
            grid.addWidget(self.course_root_edit, 0, 1)
            grid.addWidget(browse_btn, 0, 2)
            grid.addWidget(QLabel("课程标识（可选）"), 1, 0)
            grid.addWidget(self.course_edit, 1, 1)
            grid.addWidget(create_btn, 1, 2)
            grid.addWidget(QLabel("项目目录"), 2, 0)
            grid.addWidget(self.project_root_edit, 2, 1, 1, 2)
            grid.addWidget(QLabel("笔记目录"), 3, 0)
            grid.addWidget(self.notes_root_edit, 3, 1, 1, 2)
            layout.addLayout(grid)
            layout.addStretch(1)
            return page

        def _build_lecture_page(self) -> QWidget:
            page = QFrame(objectName="PageCard")
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            heading = QLabel("讲次配置", objectName="PageHeading")
            hint = QLabel("维护 lec_id 到课程资料路径的映射。一个 lec_id 可绑定多个目录或文件。", objectName="PageHint")
            layout.addWidget(heading)
            layout.addWidget(hint)

            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)

            self.lecture_list = QListWidget()
            self.lecture_list.currentTextChanged.connect(self._on_select_lecture_item)
            self.lecture_id_edit = QLineEdit()
            self.lecture_paths_input = QPlainTextEdit()
            self.lecture_paths_input.setPlaceholderText("每行一个资料路径（目录或文件）")

            browse_dir_btn = QPushButton("添加目录")
            browse_dir_btn.clicked.connect(self._on_add_lecture_path)
            browse_file_btn = QPushButton("添加文件")
            browse_file_btn.clicked.connect(self._on_add_lecture_file)
            save_lecture_btn = QPushButton("保存讲次映射")
            save_lecture_btn.clicked.connect(self._on_save_lecture_mapping)
            remove_lecture_btn = QPushButton("删除讲次")
            remove_lecture_btn.clicked.connect(self._on_remove_lecture_mapping)
            refresh_lecture_btn = QPushButton("刷新列表")
            refresh_lecture_btn.clicked.connect(self._refresh_lecture_mappings)

            grid.addWidget(QLabel("讲次列表"), 0, 0)
            grid.addWidget(QLabel("讲次标识"), 0, 1)
            grid.addWidget(self.lecture_list, 1, 0, 5, 1)
            grid.addWidget(self.lecture_id_edit, 1, 1, 1, 2)
            grid.addWidget(QLabel("资料路径"), 2, 1)
            grid.addWidget(self.lecture_paths_input, 3, 1, 2, 2)
            grid.addWidget(browse_dir_btn, 5, 1)
            grid.addWidget(browse_file_btn, 5, 2)
            grid.addWidget(save_lecture_btn, 6, 1)
            grid.addWidget(remove_lecture_btn, 6, 2)
            grid.addWidget(refresh_lecture_btn, 7, 1, 1, 2)

            layout.addLayout(grid)
            layout.addStretch(1)
            return page

        def _build_workflow_page(self) -> QWidget:
            page = QFrame(objectName="PageCard")
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            heading = QLabel("流程控制", objectName="PageHeading")
            hint = QLabel("执行轮次、从暂停点恢复，并按 lec_id 指定目标讲次。", objectName="PageHint")
            layout.addWidget(heading)
            layout.addWidget(hint)

            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)

            self.from_round_combo = QComboBox()
            self.from_round_combo.addItems(ROUND_VALUES)
            self.to_round_combo = QComboBox()
            self.to_round_combo.addItems(ROUND_VALUES)
            self.target_lecture_combo = QComboBox()
            self.target_lecture_combo.setEditable(True)
            self.max_lines_edit = QLineEdit()
            self.max_files_edit = QLineEdit()
            self.pause_each_round_check = QCheckBox("每轮后暂停")
            self.search_check = QCheckBox("启用网页搜索")
            self.allow_external_refs_check = QCheckBox("允许外部参考（Final）")

            init_round0_btn = QPushButton("初始化第 0 轮")
            init_round0_btn.clicked.connect(self._on_init_round0)
            run_workflow_btn = QPushButton("执行流程")
            run_workflow_btn.clicked.connect(self._on_run_workflow)
            resume_workflow_btn = QPushButton("恢复流程")
            resume_workflow_btn.clicked.connect(self._on_resume_workflow)
            run_check_btn = QPushButton("执行检查")
            run_check_btn.clicked.connect(self._on_run_check)

            grid.addWidget(QLabel("起始轮次"), 0, 0)
            grid.addWidget(self.from_round_combo, 0, 1)
            grid.addWidget(QLabel("结束轮次"), 0, 2)
            grid.addWidget(self.to_round_combo, 0, 3)
            grid.addWidget(QLabel("目标讲次"), 1, 0)
            grid.addWidget(self.target_lecture_combo, 1, 1, 1, 3)
            grid.addWidget(QLabel("最大改动行数"), 2, 0)
            grid.addWidget(self.max_lines_edit, 2, 1)
            grid.addWidget(QLabel("最大改动文件数"), 2, 2)
            grid.addWidget(self.max_files_edit, 2, 3)
            grid.addWidget(self.pause_each_round_check, 3, 0, 1, 2)
            grid.addWidget(self.search_check, 3, 2)
            grid.addWidget(self.allow_external_refs_check, 3, 3)
            grid.addWidget(init_round0_btn, 4, 0)
            grid.addWidget(run_workflow_btn, 4, 1)
            grid.addWidget(run_check_btn, 4, 2)
            grid.addWidget(resume_workflow_btn, 4, 3)
            layout.addLayout(grid)
            layout.addStretch(1)
            return page

        def _build_review_page(self) -> QWidget:
            page = QFrame(objectName="PageCard")
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            heading = QLabel("审阅反馈", objectName="PageHeading")
            hint = QLabel("每行一条反馈，追加到反馈文件。", objectName="PageHint")
            layout.addWidget(heading)
            layout.addWidget(hint)

            self.feedback_input = QPlainTextEdit()
            self.feedback_input.setPlaceholderText("例如：\n术语解释不够清晰\n增加练习题")
            add_feedback_btn = QPushButton("追加反馈条目")
            add_feedback_btn.clicked.connect(self._on_add_feedback)
            layout.addWidget(self.feedback_input, 1)
            layout.addWidget(add_feedback_btn, 0, Qt.AlignLeft)  # type: ignore[arg-type]
            return page

        def _build_prompt_page(self) -> QWidget:
            page = QFrame(objectName="PageCard")
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            heading = QLabel("系统提示词", objectName="PageHeading")
            hint = QLabel("查看并修改各阶段提示词模板，保存后对后续轮次生效。", objectName="PageHint")
            layout.addWidget(heading)
            layout.addWidget(hint)

            tab = QTabWidget()
            stage_titles = {
                "round1": "Round1",
                "round2": "Round2",
                "round3": "Round3",
                "final": "Final",
                "repair": "Repair",
            }
            for key in PROMPT_TEMPLATE_KEYS:
                editor = QPlainTextEdit()
                editor.setPlaceholderText(f"{stage_titles.get(key, key)} 提示词")
                self.prompt_editors[key] = editor
                tab.addTab(editor, stage_titles.get(key, key))
            layout.addWidget(tab, 1)

            row = QHBoxLayout()
            row.setSpacing(10)
            load_btn = QPushButton("读取项目提示词")
            load_btn.clicked.connect(self._on_reload_prompt_templates)
            save_btn = QPushButton("保存提示词")
            save_btn.clicked.connect(self._on_save_prompt_templates)
            reset_btn = QPushButton("恢复默认模板")
            reset_btn.clicked.connect(self._on_reset_prompt_templates)
            row.addWidget(load_btn)
            row.addWidget(save_btn)
            row.addWidget(reset_btn)
            row.addStretch(1)
            layout.addLayout(row)
            return page

        def _build_runs_page(self) -> QWidget:
            page = QFrame(objectName="PageCard")
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            heading = QLabel("运行记录与差异补丁", objectName="PageHeading")
            hint = QLabel("查看运行历史，并按运行编号打开统一补丁。", objectName="PageHint")
            layout.addWidget(heading)
            layout.addWidget(hint)

            row = QHBoxLayout()
            row.setSpacing(10)
            self.patch_run_id_edit = QLineEdit()
            self.patch_run_id_edit.setPlaceholderText("输入运行编号")
            self.patch_round_edit = QLineEdit()
            self.patch_round_edit.setPlaceholderText("可选：轮次标识")
            list_runs_btn = QPushButton("列出运行记录")
            list_runs_btn.clicked.connect(self._on_list_runs)
            show_patch_btn = QPushButton("查看差异补丁")
            show_patch_btn.clicked.connect(self._on_show_patch)
            clear_cache_btn = QPushButton("清除缓存")
            clear_cache_btn.clicked.connect(self._on_clear_cache)

            row.addWidget(QLabel("运行编号"))
            row.addWidget(self.patch_run_id_edit, 1)
            row.addWidget(QLabel("轮次"))
            row.addWidget(self.patch_round_edit, 1)
            row.addWidget(list_runs_btn)
            row.addWidget(show_patch_btn)
            row.addWidget(clear_cache_btn)

            layout.addLayout(row)
            helper = QLabel("提示：先点“列出运行记录”，再复制运行编号查看补丁。", objectName="PageHint")
            layout.addWidget(helper)
            layout.addStretch(1)
            return page

        def _add_nav_button(self, layout: QVBoxLayout, label: str, page_index: int) -> None:
            btn = QPushButton(label, objectName="NavButton")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda: self._switch_page(page_index))
            self.nav_buttons.append(btn)
            layout.addWidget(btn)

        def _switch_page(self, index: int) -> None:
            self.page_stack.setCurrentIndex(index)
            if 0 <= index < len(self.nav_buttons):
                self.nav_buttons[index].setChecked(True)

        def _apply_theme(self) -> None:
            self.setStyleSheet(
                """
                QWidget#AppRoot {
                    background: #f3eee4;
                    color: #1f2937;
                    font-family: "PingFang SC", "Avenir Next";
                    font-size: 13px;
                }
                QFrame#Sidebar {
                    background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #12363a, stop:1 #1d4f52);
                    border-radius: 14px;
                }
                QLabel#BrandTitle {
                    color: #f9fafb;
                    font-size: 24px;
                    font-weight: 700;
                }
                QLabel#BrandSubtitle {
                    color: #d1e7e9;
                    font-size: 12px;
                    margin-bottom: 8px;
                }
                QLabel#SidebarFootnote {
                    color: #b9d8db;
                    font-size: 11px;
                }
                QPushButton#NavButton {
                    background: transparent;
                    color: #dfeff0;
                    border: 1px solid rgba(223,239,240,0.25);
                    border-radius: 10px;
                    text-align: left;
                    padding: 10px 12px;
                    font-weight: 600;
                }
                QPushButton#NavButton:checked {
                    background: #f8fafc;
                    color: #164e63;
                    border-color: #f8fafc;
                }
                QFrame#MainPanel {
                    background: transparent;
                }
                QFrame#HeaderCard, QFrame#PageCard, QFrame#LogCard {
                    background: #fffdf9;
                    border: 1px solid #eadfcf;
                    border-radius: 12px;
                }
                QLabel#HeaderTitle {
                    font-size: 18px;
                    font-weight: 700;
                    color: #0f172a;
                }
                QLabel#HeaderSubtitle {
                    font-size: 12px;
                    color: #6b7280;
                }
                QLabel#StatusBadge {
                    background: #f0fdfa;
                    color: #0f766e;
                    border: 1px solid #99f6e4;
                    border-radius: 9px;
                    padding: 6px 10px;
                    font-weight: 600;
                }
                QLabel#PageHeading {
                    font-size: 18px;
                    font-weight: 700;
                    color: #111827;
                }
                QLabel#PageHint, QLabel#StatusLine {
                    color: #6b7280;
                    font-size: 12px;
                }
                QLineEdit, QComboBox, QPlainTextEdit {
                    background: #fff;
                    border: 1px solid #d4c5b1;
                    border-radius: 8px;
                    padding: 7px 9px;
                    selection-background-color: #0f766e;
                }
                QComboBox {
                    padding-right: 28px;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 24px;
                    border-top-right-radius: 8px;
                    border-bottom-right-radius: 8px;
                }
                QComboBox QAbstractItemView {
                    background: #fffdf9;
                    border: 1px solid #d4c5b1;
                    border-radius: 8px;
                    padding: 4px;
                    outline: 0;
                    selection-background-color: #0f766e;
                    selection-color: #ffffff;
                }
                QComboBox QAbstractItemView::item {
                    border-radius: 6px;
                    padding: 7px 10px;
                    margin: 2px 0;
                }
                QComboBox QAbstractItemView::item:selected {
                    background: #0f766e;
                    color: #ffffff;
                }
                QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {
                    border-color: #0f766e;
                }
                QPlainTextEdit {
                    font-family: "Menlo";
                    font-size: 12px;
                }
                QPushButton {
                    background: #0f766e;
                    color: #ffffff;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 14px;
                    font-weight: 600;
                }
                QPushButton:hover {
                    background: #0d5f58;
                }
                QPushButton:pressed {
                    background: #0b4d47;
                }
                """
            )

        def _apply_settings(self) -> None:
            self.course_root_edit.setText(self.settings.course_root)
            self.course_edit.setText(self.settings.course_id)
            self.target_lecture_combo.clear()
            self.target_lecture_combo.addItem("")
            if self.settings.target_lecture:
                self.target_lecture_combo.addItem(self.settings.target_lecture)
            self.target_lecture_combo.setCurrentText(self.settings.target_lecture)
            self._set_combo_value(self.from_round_combo, self.settings.from_round)
            self._set_combo_value(self.to_round_combo, self.settings.to_round)
            self.max_lines_edit.setText(str(self.settings.max_changed_lines))
            self.max_files_edit.setText(str(self.settings.max_changed_files))
            self.pause_each_round_check.setChecked(self.settings.pause_after_each_round)
            self.search_check.setChecked(self.settings.search_enabled)
            self.allow_external_refs_check.setChecked(self.settings.allow_external_refs)

        def _save_settings(self) -> None:
            self.settings = replace(
                self.settings,
                course_root=self.course_root_edit.text().strip(),
                course_id=self.course_edit.text().strip(),
                target_lecture=self.target_lecture_combo.currentText().strip(),
                from_round=self.from_round_combo.currentText(),
                to_round=self.to_round_combo.currentText(),
                max_changed_lines=_safe_int(self.max_lines_edit.text().strip(), 500),
                max_changed_files=_safe_int(self.max_files_edit.text().strip(), 20),
                pause_after_each_round=self.pause_each_round_check.isChecked(),
                search_enabled=self.search_check.isChecked(),
                allow_external_refs=self.allow_external_refs_check.isChecked(),
            )
            save_gui_settings(self.settings)

        def _set_combo_value(self, combo: Any, value: str) -> None:
            idx = combo.findText(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)

        def _update_header(self) -> None:
            if not self.current_config:
                self.header_title.setText("尚未加载项目")
                self.header_subtitle.setText("请先在“项目”页创建或加载")
                return
            self.header_title.setText(self.current_config.course_id)
            self.header_subtitle.setText(str(self.current_config.project_root))

        def _set_status(self, text: str, running: bool = False) -> None:
            self.status_label.setText(text)
            self.status_badge.setText("运行中" if running else "空闲")

        def _on_browse_course_root(self) -> None:
            selected = QFileDialog.getExistingDirectory(self, "选择课程根目录")
            if selected:
                self.course_root_edit.setText(selected)
                if not self.course_edit.text().strip():
                    self.course_edit.setText(Path(selected).name)
                self._save_settings()

        def _on_create_or_load_project(self) -> None:
            course_root_text = self.course_root_edit.text().strip()
            course_text = self.course_edit.text().strip()
            if not course_root_text:
                self._error("课程根目录不能为空")
                return

            try:
                course_root = Path(course_root_text).expanduser().resolve()
                course_id = slugify_course_id(course_text) if course_text else None
                project_root = course_root / PROJECT_REL_PATH
                if (project_root / "project.yaml").exists():
                    config = self.project_service.load_project_config(project_root)
                else:
                    config = self.project_service.create_project(
                        CreateProjectRequest(course_root=course_root, course_id=course_id),
                        allow_existing=True,
                    )
            except (ValueError, FileNotFoundError, OSError) as exc:
                self._error(str(exc))
                return

            self.current_config = config
            self.course_root_edit.setText(str(config.course_root))
            self.course_edit.setText(config.course_id)
            self.project_root_edit.setText(str(config.project_root))
            self.notes_root_edit.setText(str(config.notes_root))
            self._update_header()
            self._load_prompt_templates_for_current_project()
            self._refresh_lecture_mappings()
            self._save_settings()
            self._log(f"项目已就绪: {config.project_root}")

        def _require_config(self) -> ProjectConfig | None:
            if self.current_config:
                return self.current_config

            project_text = self.project_root_edit.text().strip()
            if project_text:
                try:
                    self.current_config = self.project_service.load_project_config(Path(project_text))
                except (ValueError, FileNotFoundError, OSError) as exc:
                    self._error(str(exc))
                    return None
                self._update_header()
                self._load_prompt_templates_for_current_project()
                self._refresh_lecture_mappings()
                return self.current_config
            self._error("请先创建或加载项目")
            return None

        def _load_prompt_templates_for_current_project(self) -> None:
            if not self.current_config:
                self._fill_prompt_editors(DEFAULT_PROMPT_TEMPLATES)
                return
            templates = self.prompt_template_service.load_templates(project_root=self.current_config.project_root)
            self._fill_prompt_editors(templates)

        def _refresh_lecture_mappings(self) -> None:
            config = self._require_config()
            if not config:
                return
            entries = self.lecture_registry_service.list_lectures(project_root=config.project_root)
            self.lecture_entries = {
                entry.lec_id: [str(path) for path in entry.paths]
                for entry in entries
            }

            self.lecture_list.clear()
            for lec_id in sorted(self.lecture_entries.keys()):
                self.lecture_list.addItem(f"{lec_id} ({len(self.lecture_entries[lec_id])} 路径)")

            current_target = self.target_lecture_combo.currentText().strip()
            self.target_lecture_combo.blockSignals(True)
            self.target_lecture_combo.clear()
            self.target_lecture_combo.addItem("")
            for lec_id in sorted(self.lecture_entries.keys()):
                self.target_lecture_combo.addItem(lec_id)
            if current_target:
                self.target_lecture_combo.setCurrentText(current_target)
            self.target_lecture_combo.blockSignals(False)

        def _on_select_lecture_item(self, text: str) -> None:
            if not text:
                return
            lec_id = text.split(" (", 1)[0]
            paths = self.lecture_entries.get(lec_id, [])
            self.lecture_id_edit.setText(lec_id)
            self.lecture_paths_input.setPlainText("\n".join(paths))

        def _on_add_lecture_path(self) -> None:
            config = self._require_config()
            if not config:
                return
            start = self.course_root_edit.text().strip() or str(config.course_root)
            selected = QFileDialog.getExistingDirectory(self, "选择讲次资料目录", start)
            if not selected:
                return
            current_lines = [
                line.strip()
                for line in self.lecture_paths_input.toPlainText().splitlines()
                if line.strip()
            ]
            if selected not in current_lines:
                current_lines.append(selected)
            self.lecture_paths_input.setPlainText("\n".join(current_lines))

        def _on_add_lecture_file(self) -> None:
            config = self._require_config()
            if not config:
                return
            start = self.course_root_edit.text().strip() or str(config.course_root)
            selected, _ = QFileDialog.getOpenFileName(self, "选择讲次资料文件", start)
            if not selected:
                return
            current_lines = [
                line.strip()
                for line in self.lecture_paths_input.toPlainText().splitlines()
                if line.strip()
            ]
            if selected not in current_lines:
                current_lines.append(selected)
            self.lecture_paths_input.setPlainText("\n".join(current_lines))

        def _on_save_lecture_mapping(self) -> None:
            config = self._require_config()
            if not config:
                return
            lec_id = self.lecture_id_edit.text().strip()
            paths = [
                line.strip()
                for line in self.lecture_paths_input.toPlainText().splitlines()
                if line.strip()
            ]
            try:
                entry = self.lecture_registry_service.upsert_lecture(
                    project_root=config.project_root,
                    lec_id=lec_id,
                    paths=[Path(item) for item in paths],
                )
            except (ValueError, FileNotFoundError, OSError) as exc:
                self._error(str(exc))
                return
            self._refresh_lecture_mappings()
            self.target_lecture_combo.setCurrentText(entry.lec_id)
            self._save_settings()
            self._log(f"讲次映射已保存: {entry.lec_id}")

        def _on_remove_lecture_mapping(self) -> None:
            config = self._require_config()
            if not config:
                return
            lec_id = self.lecture_id_edit.text().strip()
            if not lec_id:
                self._error("请先选择要删除的 lec_id")
                return
            removed = self.lecture_registry_service.remove_lecture(
                project_root=config.project_root,
                lec_id=lec_id,
            )
            if not removed:
                self._error("未找到对应 lec_id")
                return
            self.lecture_id_edit.clear()
            self.lecture_paths_input.clear()
            self._refresh_lecture_mappings()
            self._save_settings()
            self._log(f"讲次映射已删除: {lec_id}")

        def _on_init_round0(self) -> None:
            config = self._require_config()
            if not config:
                return

            def task(progress: Callable[[str], None]) -> dict[str, Any]:
                progress("[round0] 开始初始化")
                init_result = self.round0_initializer.initialize(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    course_id=config.course_id,
                )
                progress("[round0] 初始化完成，开始检查")
                check_result = self.check_runner.run(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    progress_callback=progress,
                )
                return {"init": init_result.to_dict(), "check": check_result.to_dict()}

            self._run_task("初始化第 0 轮", task)

        def _on_run_workflow(self) -> None:
            config = self._require_config()
            if not config:
                return
            from_round = self.from_round_combo.currentText()
            to_round = self.to_round_combo.currentText()
            target = self.target_lecture_combo.currentText().strip()
            max_lines = _safe_int(self.max_lines_edit.text().strip(), config.max_changed_lines)
            max_files = _safe_int(self.max_files_edit.text().strip(), config.max_changed_files)
            search_enabled = self.search_check.isChecked()
            pause_each_round = self.pause_each_round_check.isChecked()
            allow_external_refs = self.allow_external_refs_check.isChecked()
            if search_enabled and not allow_external_refs:
                allow_external_refs = True
                self.allow_external_refs_check.setChecked(True)
                self._log("已自动启用“允许外部参考（Final）”：网页搜索仅在该选项开启时生效，请注意外部信息风险。")

            def task(progress: Callable[[str], None]) -> dict[str, Any]:
                result = self.workflow_orchestrator.run(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    from_round=from_round,  # type: ignore[arg-type]
                    to_round=to_round,  # type: ignore[arg-type]
                    target_lectures=[target] if target else [],
                    allow_external_refs=allow_external_refs,
                    search_enabled=search_enabled,
                    max_retries=0,
                    pause_after_each_round=pause_each_round,
                    max_changed_lines=max_lines,
                    max_changed_files=max_files,
                    progress_callback=progress,
                )
                return result.to_dict()

            try:
                self._save_prompt_templates_for_project(config)
            except OSError as exc:
                self._error(f"保存提示词失败: {exc}")
                return
            self._save_settings()
            self._run_task(f"执行流程 {from_round}->{to_round}", task)

        def _on_resume_workflow(self) -> None:
            config = self._require_config()
            if not config:
                return
            to_round = self.to_round_combo.currentText()
            target = self.target_lecture_combo.currentText().strip()
            max_lines = _safe_int(self.max_lines_edit.text().strip(), config.max_changed_lines)
            max_files = _safe_int(self.max_files_edit.text().strip(), config.max_changed_files)
            search_enabled = self.search_check.isChecked()
            pause_each_round = self.pause_each_round_check.isChecked()
            allow_external_refs = self.allow_external_refs_check.isChecked()
            if search_enabled and not allow_external_refs:
                allow_external_refs = True
                self.allow_external_refs_check.setChecked(True)
                self._log("已自动启用“允许外部参考（Final）”：网页搜索仅在该选项开启时生效，请注意外部信息风险。")

            def task(progress: Callable[[str], None]) -> dict[str, Any]:
                result = self.workflow_orchestrator.resume(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    to_round=to_round,  # type: ignore[arg-type]
                    target_lectures=[target] if target else [],
                    allow_external_refs=allow_external_refs,
                    search_enabled=search_enabled,
                    max_retries=0,
                    pause_after_each_round=pause_each_round,
                    max_changed_lines=max_lines,
                    max_changed_files=max_files,
                    progress_callback=progress,
                )
                return result.to_dict()

            try:
                self._save_prompt_templates_for_project(config)
            except OSError as exc:
                self._error(f"保存提示词失败: {exc}")
                return
            self._save_settings()
            self._run_task(f"恢复流程 -> {to_round}", task)

        def _on_run_check(self) -> None:
            config = self._require_config()
            if not config:
                return

            def task(progress: Callable[[str], None]) -> dict[str, Any]:
                return self.check_runner.run(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    progress_callback=progress,
                ).to_dict()

            self._run_task("执行检查", task)

        def _on_add_feedback(self) -> None:
            config = self._require_config()
            if not config:
                return
            lines = [line.strip() for line in self.feedback_input.toPlainText().splitlines() if line.strip()]
            if not lines:
                self._error("反馈输入不能为空")
                return

            result = self.feedback_service.append_feedback(notes_root=config.notes_root, items=lines)
            self.feedback_input.clear()
            self._log(_to_json(result.to_dict()))

        def _on_reload_prompt_templates(self) -> None:
            config = self._require_config()
            if not config:
                return
            templates = self.prompt_template_service.load_templates(project_root=config.project_root)
            self._fill_prompt_editors(templates)
            self._log(f"提示词已读取: {self.prompt_template_service.template_path(project_root=config.project_root)}")

        def _on_save_prompt_templates(self) -> None:
            config = self._require_config()
            if not config:
                return
            try:
                path = self._save_prompt_templates_for_project(config)
            except OSError as exc:
                self._error(f"保存提示词失败: {exc}")
                return
            self._log(f"提示词已保存: {path}")

        def _on_reset_prompt_templates(self) -> None:
            self._fill_prompt_editors(DEFAULT_PROMPT_TEMPLATES)
            self._log("已恢复默认提示词模板（请点击“保存提示词”写入项目）")

        def _fill_prompt_editors(self, templates: dict[str, str]) -> None:
            for key, editor in self.prompt_editors.items():
                editor.setPlainText(templates.get(key, ""))

        def _save_prompt_templates_for_project(self, config: ProjectConfig) -> Path:
            templates = {
                key: editor.toPlainText()
                for key, editor in self.prompt_editors.items()
            }
            return self.prompt_template_service.save_templates(
                project_root=config.project_root,
                templates=templates,
            )

        def _on_list_runs(self) -> None:
            config = self._require_config()
            if not config:
                return

            records = [item.to_dict() for item in self.run_history_service.list_runs(project_root=config.project_root)]
            if records and not self.patch_run_id_edit.text().strip():
                self.patch_run_id_edit.setText(str(records[0]["run_id"]))
            payload = {
                "round_status": self.run_history_service.load_round_status(project_root=config.project_root),
                "runs": records,
            }
            self._log(_to_json(payload))

        def _on_show_patch(self) -> None:
            config = self._require_config()
            if not config:
                return
            run_id = self.patch_run_id_edit.text().strip()
            if not run_id:
                self._error("请填写补丁对应的运行编号")
                return
            round_name = self.patch_round_edit.text().strip() or None
            patch = self.run_history_service.read_patch(
                project_root=config.project_root,
                run_id=run_id,
                round_name=round_name,
            )
            if patch is None:
                self._error("未找到对应补丁")
                return
            self._log(patch)

        def _on_clear_cache(self) -> None:
            config = self._require_config()
            if not config:
                return
            if self._threads:
                self._error("当前有任务运行中，请先等待完成后再清理缓存")
                return

            confirm = QMessageBox.question(
                self,
                "确认清除缓存",
                (
                    "将删除项目中的中间文件（runs 与 artifacts 缓存），\n"
                    "不会删除已生成的笔记内容。是否继续？"
                ),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                return

            def task(progress: Callable[[str], None]) -> dict[str, Any]:
                result = self.cache_service.clear_intermediate_files(
                    project_root=config.project_root,
                    preserve_prompt_templates=True,
                    progress_callback=progress,
                )
                return result.to_dict()

            self._run_task("清除中间缓存", task)

        def _run_task(self, title: str, fn: Callable[[Callable[[str], None]], Any]) -> None:
            if self._threads:
                self._error("当前已有任务运行中，请等待当前任务完成后再启动新任务")
                return
            self._set_status(f"执行中: {title}", running=True)
            worker = TaskWorker(fn)
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            def on_finished(result: Any) -> None:
                self._set_status("空闲", running=False)
                self._log(_to_json(result))
                thread.quit()

            def on_failed(err: str) -> None:
                self._set_status("空闲", running=False)
                self._error(err)
                thread.quit()

            def on_progress(message: str) -> None:
                self._set_status(message, running=True)
                self._log(message)

            worker.finished.connect(on_finished)
            worker.failed.connect(on_failed)
            worker.progress.connect(on_progress)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
            thread.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
            self._threads.append(thread)
            self._workers.append(worker)
            thread.start()

        def _log(self, message: str) -> None:
            self.output.appendPlainText(f"[{_now_time()}] {message}")
            self.output.appendPlainText("")

        def _error(self, message: str) -> None:
            self._log(message)
            QMessageBox.critical(self, "错误", message)

    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
