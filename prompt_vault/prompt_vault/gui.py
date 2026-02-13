from __future__ import annotations

from pathlib import Path


def launch_gui(db_path: Path | None = None) -> int:
    from .webapp import launch_gui as launch_web_gui

    return launch_web_gui(db_path=db_path)


def launch_legacy_tk_gui(db_path: Path | None = None) -> int:
    from .legacy_gui import launch_gui as launch_legacy

    return launch_legacy(db_path=db_path)
