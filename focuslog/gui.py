from __future__ import annotations

from pathlib import Path


def launch_gui(db_path: Path | None = None) -> int:
    from .desktop.main import launch_desktop

    return launch_desktop(db_path=db_path)


def launch_legacy_tk_gui(db_path: Path | None = None) -> int:
    from .legacy_gui import launch_gui as launch_legacy

    return launch_legacy(db_path=db_path)
