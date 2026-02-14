from __future__ import annotations

import json
import traceback
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .check_runner import CheckRunner
from .feedback_service import FeedbackService
from .gui_settings import load_gui_settings, save_gui_settings
from .models import CreateProjectRequest, ProjectConfig
from .project_service import ProjectService, slugify_course_id
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
            QMainWindow,
            QMessageBox,
            QPushButton,
            QPlainTextEdit,
            QComboBox,
            QStackedWidget,
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

        def __init__(self, fn: Callable[[], Any]) -> None:
            super().__init__()
            self._fn = fn

        def run(self) -> None:
            try:
                result = self._fn()
                self.finished.emit(result)
            except Exception as exc:
                if isinstance(exc, ValueError):
                    self.failed.emit(str(exc))
                else:
                    self.failed.emit(traceback.format_exc())

    class MainWindow(QMainWindow):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("课程笔记助手")
            self.resize(1320, 860)

            self.project_service = ProjectService()
            self.round0_initializer = Round0Initializer()
            self.check_runner = CheckRunner()
            self.feedback_service = FeedbackService()
            self.run_history_service = RunHistoryService()
            self.workflow_orchestrator = WorkflowOrchestrator(
                project_service=self.project_service,
                check_runner=self.check_runner,
                round0_initializer=self.round0_initializer,
            )
            self.current_config: ProjectConfig | None = None
            self._threads: list[QThread] = []
            self.settings = load_gui_settings()
            self.nav_buttons: list[QPushButton] = []

            self._build_ui()
            self._apply_theme()
            self._apply_settings()
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
            self._add_nav_button(sidebar_layout, "流程", 1)
            self._add_nav_button(sidebar_layout, "审阅", 2)
            self._add_nav_button(sidebar_layout, "运行记录", 3)
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
            self.page_stack.addWidget(self._build_workflow_page())
            self.page_stack.addWidget(self._build_review_page())
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
            hint = QLabel("选择工作区与课程后，创建或加载项目目录。", objectName="PageHint")
            layout.addWidget(heading)
            layout.addWidget(hint)

            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)

            self.workspace_edit = QLineEdit()
            self.course_edit = QLineEdit()
            self.project_root_edit = QLineEdit()
            self.project_root_edit.setReadOnly(True)
            self.notes_root_edit = QLineEdit()
            self.notes_root_edit.setReadOnly(True)

            browse_btn = QPushButton("选择工作区")
            browse_btn.clicked.connect(self._on_browse_workspace)
            create_btn = QPushButton("创建或加载项目")
            create_btn.clicked.connect(self._on_create_or_load_project)

            grid.addWidget(QLabel("工作区目录"), 0, 0)
            grid.addWidget(self.workspace_edit, 0, 1)
            grid.addWidget(browse_btn, 0, 2)
            grid.addWidget(QLabel("课程标识"), 1, 0)
            grid.addWidget(self.course_edit, 1, 1)
            grid.addWidget(create_btn, 1, 2)
            grid.addWidget(QLabel("项目目录"), 2, 0)
            grid.addWidget(self.project_root_edit, 2, 1, 1, 2)
            grid.addWidget(QLabel("笔记目录"), 3, 0)
            grid.addWidget(self.notes_root_edit, 3, 1, 1, 2)
            layout.addLayout(grid)
            layout.addStretch(1)
            return page

        def _build_workflow_page(self) -> QWidget:
            page = QFrame(objectName="PageCard")
            layout = QVBoxLayout(page)
            layout.setContentsMargins(16, 16, 16, 16)
            layout.setSpacing(12)

            heading = QLabel("流程控制", objectName="PageHeading")
            hint = QLabel("执行轮次、从暂停点恢复，并设置安全阈值。", objectName="PageHint")
            layout.addWidget(heading)
            layout.addWidget(hint)

            grid = QGridLayout()
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)

            self.from_round_combo = QComboBox()
            self.from_round_combo.addItems(ROUND_VALUES)
            self.to_round_combo = QComboBox()
            self.to_round_combo.addItems(ROUND_VALUES)
            self.target_lecture_edit = QLineEdit()
            self.max_lines_edit = QLineEdit()
            self.max_files_edit = QLineEdit()
            self.pause_each_round_check = QCheckBox("每轮后暂停")
            self.search_check = QCheckBox("启用网页搜索")

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
            grid.addWidget(self.target_lecture_edit, 1, 1, 1, 3)
            grid.addWidget(QLabel("最大改动行数"), 2, 0)
            grid.addWidget(self.max_lines_edit, 2, 1)
            grid.addWidget(QLabel("最大改动文件数"), 2, 2)
            grid.addWidget(self.max_files_edit, 2, 3)
            grid.addWidget(self.pause_each_round_check, 3, 0, 1, 2)
            grid.addWidget(self.search_check, 3, 2, 1, 2)
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

            row.addWidget(QLabel("运行编号"))
            row.addWidget(self.patch_run_id_edit, 1)
            row.addWidget(QLabel("轮次"))
            row.addWidget(self.patch_round_edit, 1)
            row.addWidget(list_runs_btn)
            row.addWidget(show_patch_btn)

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
            self.workspace_edit.setText(self.settings.workspace_root)
            self.course_edit.setText(self.settings.course_id)
            self.target_lecture_edit.setText(self.settings.target_lecture)
            self._set_combo_value(self.from_round_combo, self.settings.from_round)
            self._set_combo_value(self.to_round_combo, self.settings.to_round)
            self.max_lines_edit.setText(str(self.settings.max_changed_lines))
            self.max_files_edit.setText(str(self.settings.max_changed_files))
            self.pause_each_round_check.setChecked(self.settings.pause_after_each_round)
            self.search_check.setChecked(self.settings.search_enabled)

        def _save_settings(self) -> None:
            self.settings = replace(
                self.settings,
                workspace_root=self.workspace_edit.text().strip(),
                course_id=self.course_edit.text().strip(),
                target_lecture=self.target_lecture_edit.text().strip(),
                from_round=self.from_round_combo.currentText(),
                to_round=self.to_round_combo.currentText(),
                max_changed_lines=_safe_int(self.max_lines_edit.text().strip(), 500),
                max_changed_files=_safe_int(self.max_files_edit.text().strip(), 20),
                pause_after_each_round=self.pause_each_round_check.isChecked(),
                search_enabled=self.search_check.isChecked(),
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

        def _on_browse_workspace(self) -> None:
            selected = QFileDialog.getExistingDirectory(self, "选择工作区目录")
            if selected:
                self.workspace_edit.setText(selected)
                self._save_settings()

        def _on_create_or_load_project(self) -> None:
            workspace_text = self.workspace_edit.text().strip()
            course_text = self.course_edit.text().strip()
            if not workspace_text or not course_text:
                self._error("工作区目录和课程标识不能为空")
                return

            try:
                workspace_root = Path(workspace_text).expanduser().resolve()
                course_id = slugify_course_id(course_text)
                project_root = workspace_root / "projects" / course_id
                if (project_root / "project.yaml").exists():
                    config = self.project_service.load_project_config(project_root)
                else:
                    config = self.project_service.create_project(
                        CreateProjectRequest(course_id=course_id, workspace_root=workspace_root),
                        allow_existing=True,
                    )
            except (ValueError, FileNotFoundError, OSError) as exc:
                self._error(str(exc))
                return

            self.current_config = config
            self.project_root_edit.setText(str(config.project_root))
            self.notes_root_edit.setText(str(config.notes_root))
            self._update_header()
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
                return self.current_config
            self._error("请先创建或加载项目")
            return None

        def _on_init_round0(self) -> None:
            config = self._require_config()
            if not config:
                return

            def task() -> dict[str, Any]:
                init_result = self.round0_initializer.initialize(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    course_id=config.course_id,
                )
                check_result = self.check_runner.run(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                )
                return {"init": init_result.to_dict(), "check": check_result.to_dict()}

            self._run_task("初始化第 0 轮", task)

        def _on_run_workflow(self) -> None:
            config = self._require_config()
            if not config:
                return
            from_round = self.from_round_combo.currentText()
            to_round = self.to_round_combo.currentText()
            target = self.target_lecture_edit.text().strip()
            max_lines = _safe_int(self.max_lines_edit.text().strip(), config.max_changed_lines)
            max_files = _safe_int(self.max_files_edit.text().strip(), config.max_changed_files)
            search_enabled = self.search_check.isChecked()
            pause_each_round = self.pause_each_round_check.isChecked()

            def task() -> dict[str, Any]:
                result = self.workflow_orchestrator.run(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    from_round=from_round,  # type: ignore[arg-type]
                    to_round=to_round,  # type: ignore[arg-type]
                    target_lectures=[target] if target else [],
                    search_enabled=search_enabled,
                    pause_after_each_round=pause_each_round,
                    max_changed_lines=max_lines,
                    max_changed_files=max_files,
                )
                return result.to_dict()

            self._save_settings()
            self._run_task(f"执行流程 {from_round}->{to_round}", task)

        def _on_resume_workflow(self) -> None:
            config = self._require_config()
            if not config:
                return
            to_round = self.to_round_combo.currentText()
            target = self.target_lecture_edit.text().strip()
            max_lines = _safe_int(self.max_lines_edit.text().strip(), config.max_changed_lines)
            max_files = _safe_int(self.max_files_edit.text().strip(), config.max_changed_files)
            search_enabled = self.search_check.isChecked()
            pause_each_round = self.pause_each_round_check.isChecked()

            def task() -> dict[str, Any]:
                result = self.workflow_orchestrator.resume(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    to_round=to_round,  # type: ignore[arg-type]
                    target_lectures=[target] if target else [],
                    search_enabled=search_enabled,
                    pause_after_each_round=pause_each_round,
                    max_changed_lines=max_lines,
                    max_changed_files=max_files,
                )
                return result.to_dict()

            self._save_settings()
            self._run_task(f"恢复流程 -> {to_round}", task)

        def _on_run_check(self) -> None:
            config = self._require_config()
            if not config:
                return

            def task() -> dict[str, Any]:
                return self.check_runner.run(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
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

        def _run_task(self, title: str, fn: Callable[[], Any]) -> None:
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

            worker.finished.connect(on_finished)
            worker.failed.connect(on_failed)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(lambda: self._threads.remove(thread) if thread in self._threads else None)
            self._threads.append(thread)
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
