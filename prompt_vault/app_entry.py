from __future__ import annotations

import sys

try:
    from prompt_vault.prompt_vault.cli import main as cli_main
    from prompt_vault.prompt_vault.webapp import launch_gui
except ModuleNotFoundError:
    # Fallback for direct script execution: python prompt_vault/app_entry.py
    from prompt_vault.cli import main as cli_main
    from prompt_vault.webapp import launch_gui


def main() -> int:
    # Default behavior is GUI-first for desktop usage.
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        return cli_main(sys.argv[2:])
    return launch_gui()


if __name__ == "__main__":
    raise SystemExit(main())
