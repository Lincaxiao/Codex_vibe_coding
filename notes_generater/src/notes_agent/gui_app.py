from __future__ import annotations

import json
import traceback
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from .feedback_service import FeedbackService
from .gui_settings import GuiSettings, load_gui_settings, save_gui_settings
from .models import CreateProjectRequest, ProjectConfig
from .project_service import ProjectService, slugify_course_id
from .round0_initializer import Round0Initializer
from .check_runner import CheckRunner
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


def main() -> int:
    try:
        from PySide6.QtCore import QObject, QThread, Signal, Qt
        from PySide6.QtWidgets import (
            QApplication,
            QFileDialog,
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
            QVBoxLayout,
            QWidget,
            QCheckBox,
        )
    except ImportError as exc:
        print("PySide6 is required for GUI mode. Install with: pip install '.[gui]'")
        print(f"ImportError: {exc}")
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
            except Exception:
                self.failed.emit(traceback.format_exc())

    class MainWindow(QMainWindow):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("Notes Agent Desktop")
            self.resize(1200, 760)

            self.project_service = ProjectService()
            self.round0_initializer = Round0Initializer()
            self.check_runner = CheckRunner()
            self.feedback_service = FeedbackService()
            self.workflow_orchestrator = WorkflowOrchestrator(
                project_service=self.project_service,
                check_runner=self.check_runner,
                round0_initializer=self.round0_initializer,
            )
            self.current_config: ProjectConfig | None = None
            self._threads: list[QThread] = []
            self.settings = load_gui_settings()

            self._build_ui()
            self._apply_settings()
            self._log("GUI initialized")

        def _build_ui(self) -> None:
            root = QWidget()
            root_layout = QVBoxLayout(root)

            project_box = QGroupBox("Project")
            project_layout = QGridLayout(project_box)
            self.workspace_edit = QLineEdit()
            self.course_edit = QLineEdit()
            self.project_root_edit = QLineEdit()
            self.project_root_edit.setReadOnly(True)
            self.notes_root_edit = QLineEdit()
            self.notes_root_edit.setReadOnly(True)

            browse_btn = QPushButton("Browse Workspace")
            browse_btn.clicked.connect(self._on_browse_workspace)
            create_btn = QPushButton("Create or Load Project")
            create_btn.clicked.connect(self._on_create_or_load_project)

            project_layout.addWidget(QLabel("Workspace Root"), 0, 0)
            project_layout.addWidget(self.workspace_edit, 0, 1)
            project_layout.addWidget(browse_btn, 0, 2)
            project_layout.addWidget(QLabel("Course ID"), 1, 0)
            project_layout.addWidget(self.course_edit, 1, 1)
            project_layout.addWidget(create_btn, 1, 2)
            project_layout.addWidget(QLabel("Project Root"), 2, 0)
            project_layout.addWidget(self.project_root_edit, 2, 1, 1, 2)
            project_layout.addWidget(QLabel("Notes Root"), 3, 0)
            project_layout.addWidget(self.notes_root_edit, 3, 1, 1, 2)

            action_box = QGroupBox("Workflow")
            action_layout = QGridLayout(action_box)
            self.from_round_combo = QComboBox()
            self.from_round_combo.addItems(ROUND_VALUES)
            self.to_round_combo = QComboBox()
            self.to_round_combo.addItems(ROUND_VALUES)
            self.target_lecture_edit = QLineEdit()
            self.max_lines_edit = QLineEdit()
            self.max_files_edit = QLineEdit()
            self.pause_each_round_check = QCheckBox("Pause After Each Round")
            self.search_check = QCheckBox("Enable Web Search")

            init_round0_btn = QPushButton("Init Round0")
            init_round0_btn.clicked.connect(self._on_init_round0)
            run_workflow_btn = QPushButton("Run Workflow")
            run_workflow_btn.clicked.connect(self._on_run_workflow)
            resume_workflow_btn = QPushButton("Resume Workflow")
            resume_workflow_btn.clicked.connect(self._on_resume_workflow)
            run_check_btn = QPushButton("Run Check")
            run_check_btn.clicked.connect(self._on_run_check)

            action_layout.addWidget(QLabel("From"), 0, 0)
            action_layout.addWidget(self.from_round_combo, 0, 1)
            action_layout.addWidget(QLabel("To"), 0, 2)
            action_layout.addWidget(self.to_round_combo, 0, 3)
            action_layout.addWidget(QLabel("Target Lecture"), 1, 0)
            action_layout.addWidget(self.target_lecture_edit, 1, 1, 1, 3)
            action_layout.addWidget(QLabel("Max Changed Lines"), 2, 0)
            action_layout.addWidget(self.max_lines_edit, 2, 1)
            action_layout.addWidget(QLabel("Max Changed Files"), 2, 2)
            action_layout.addWidget(self.max_files_edit, 2, 3)
            action_layout.addWidget(self.pause_each_round_check, 3, 0, 1, 2)
            action_layout.addWidget(self.search_check, 3, 2, 1, 2)
            action_layout.addWidget(init_round0_btn, 4, 0)
            action_layout.addWidget(run_workflow_btn, 4, 1)
            action_layout.addWidget(run_check_btn, 4, 2)
            action_layout.addWidget(resume_workflow_btn, 4, 3)

            feedback_box = QGroupBox("Feedback")
            feedback_layout = QVBoxLayout(feedback_box)
            self.feedback_input = QPlainTextEdit()
            self.feedback_input.setPlaceholderText("One feedback item per line")
            add_feedback_btn = QPushButton("Append Feedback Items")
            add_feedback_btn.clicked.connect(self._on_add_feedback)
            feedback_layout.addWidget(self.feedback_input)
            feedback_layout.addWidget(add_feedback_btn)

            self.status_label = QLabel("Idle")
            self.status_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # type: ignore[arg-type]
            self.output = QPlainTextEdit()
            self.output.setReadOnly(True)

            root_layout.addWidget(project_box)
            root_layout.addWidget(action_box)
            root_layout.addWidget(feedback_box)
            root_layout.addWidget(self.status_label)
            root_layout.addWidget(self.output, 1)
            self.setCentralWidget(root)

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

        def _on_browse_workspace(self) -> None:
            selected = QFileDialog.getExistingDirectory(self, "Select Workspace Directory")
            if selected:
                self.workspace_edit.setText(selected)
                self._save_settings()

        def _on_create_or_load_project(self) -> None:
            workspace_text = self.workspace_edit.text().strip()
            course_text = self.course_edit.text().strip()
            if not workspace_text or not course_text:
                self._error("Workspace root and course ID are required")
                return

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

            self.current_config = config
            self.project_root_edit.setText(str(config.project_root))
            self.notes_root_edit.setText(str(config.notes_root))
            self._save_settings()
            self._log(f"Project ready: {config.project_root}")

        def _require_config(self) -> ProjectConfig | None:
            if self.current_config:
                return self.current_config

            project_text = self.project_root_edit.text().strip()
            if project_text:
                self.current_config = self.project_service.load_project_config(Path(project_text))
                return self.current_config
            self._error("Create or load project first")
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
                return {
                    "init": init_result.to_dict(),
                    "check": check_result.to_dict(),
                }

            self._run_task("Init Round0", task)

        def _on_run_workflow(self) -> None:
            config = self._require_config()
            if not config:
                return

            from_round = self.from_round_combo.currentText()
            to_round = self.to_round_combo.currentText()
            target = self.target_lecture_edit.text().strip()
            max_lines = _safe_int(self.max_lines_edit.text().strip(), config.max_changed_lines)
            max_files = _safe_int(self.max_files_edit.text().strip(), config.max_changed_files)

            def task() -> dict[str, Any]:
                result = self.workflow_orchestrator.run(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    from_round=from_round,  # type: ignore[arg-type]
                    to_round=to_round,  # type: ignore[arg-type]
                    target_lectures=[target] if target else [],
                    search_enabled=self.search_check.isChecked(),
                    pause_after_each_round=self.pause_each_round_check.isChecked(),
                    max_changed_lines=max_lines,
                    max_changed_files=max_files,
                )
                return result.to_dict()

            self._save_settings()
            self._run_task(f"Run Workflow {from_round}->{to_round}", task)

        def _on_resume_workflow(self) -> None:
            config = self._require_config()
            if not config:
                return

            to_round = self.to_round_combo.currentText()
            target = self.target_lecture_edit.text().strip()
            max_lines = _safe_int(self.max_lines_edit.text().strip(), config.max_changed_lines)
            max_files = _safe_int(self.max_files_edit.text().strip(), config.max_changed_files)

            def task() -> dict[str, Any]:
                result = self.workflow_orchestrator.resume(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                    to_round=to_round,  # type: ignore[arg-type]
                    target_lectures=[target] if target else [],
                    search_enabled=self.search_check.isChecked(),
                    pause_after_each_round=self.pause_each_round_check.isChecked(),
                    max_changed_lines=max_lines,
                    max_changed_files=max_files,
                )
                return result.to_dict()

            self._save_settings()
            self._run_task(f"Resume Workflow -> {to_round}", task)

        def _on_run_check(self) -> None:
            config = self._require_config()
            if not config:
                return

            def task() -> dict[str, Any]:
                return self.check_runner.run(
                    project_root=config.project_root,
                    notes_root=config.notes_root,
                ).to_dict()

            self._run_task("Run Check", task)

        def _on_add_feedback(self) -> None:
            config = self._require_config()
            if not config:
                return

            lines = [line.strip() for line in self.feedback_input.toPlainText().splitlines() if line.strip()]
            if not lines:
                self._error("Feedback input is empty")
                return

            result = self.feedback_service.append_feedback(
                notes_root=config.notes_root,
                items=lines,
            )
            self.feedback_input.clear()
            self._log(_to_json(result.to_dict()))

        def _run_task(self, title: str, fn: Callable[[], Any]) -> None:
            self.status_label.setText(f"Running: {title}")
            worker = TaskWorker(fn)
            thread = QThread(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run)

            def on_finished(result: Any) -> None:
                self.status_label.setText("Idle")
                self._log(_to_json(result))
                thread.quit()

            def on_failed(err: str) -> None:
                self.status_label.setText("Idle")
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
            self.output.appendPlainText(message)
            self.output.appendPlainText("")

        def _error(self, message: str) -> None:
            self._log(message)
            QMessageBox.critical(self, "Error", message)

    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
