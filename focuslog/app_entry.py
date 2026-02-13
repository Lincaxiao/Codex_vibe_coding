from __future__ import annotations

import sys
from pathlib import Path

try:
    from focuslog.cli import main as cli_main
    from focuslog.gui import launch_gui, launch_legacy_tk_gui
except ModuleNotFoundError:
    # Fallback for direct script execution: python focuslog/app_entry.py
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from focuslog.cli import main as cli_main
    from focuslog.gui import launch_gui, launch_legacy_tk_gui


def main() -> int:
    # Default behavior is GUI-first for desktop usage.
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        return cli_main(sys.argv[2:])
    result = launch_gui()
    if result == 0:
        return 0
    print("回退到 Tk GUI...")
    return launch_legacy_tk_gui()


if __name__ == "__main__":
    raise SystemExit(main())
