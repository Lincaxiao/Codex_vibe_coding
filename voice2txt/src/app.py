from pathlib import Path

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from src.constants import APP_TITLE, PROJECT_ROOT
from src.models import AppConfig
from src.services.config_service import ConfigService
from src.ui.main_window import MainWindow


def _prompt_workspace(config_service: ConfigService) -> AppConfig | None:
    while True:
        selected = QFileDialog.getExistingDirectory(
            None,
            f"{APP_TITLE} - 选择工作区",
            str(Path.home()),
        )

        if selected:
            selected_path = Path(selected)
            if config_service.is_workspace_valid(selected_path):
                return config_service.make_default(selected_path)
            QMessageBox.critical(None, "工作区无效", "所选目录不可写，请重新选择。")
            continue

        choice = QMessageBox.question(
            None,
            "必须选择工作区",
            "继续使用前必须先选择工作区。\n\n点击“是”退出，点击“否”继续选择。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if choice == QMessageBox.Yes:
            return None


def run_app() -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(APP_TITLE)

    config_service = ConfigService(PROJECT_ROOT)
    config = config_service.load()

    if config is None:
        config = _prompt_workspace(config_service)
        if config is None:
            return 0
        config_service.save(config)

    window = MainWindow(config_service=config_service, config=config)
    window.show()
    return app.exec()
