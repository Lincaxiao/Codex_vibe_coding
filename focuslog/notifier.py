from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from typing import TextIO


class Notifier:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def notify(self, title: str, message: str) -> None:
        sent = False
        system_name = platform.system().lower()

        try:
            if system_name == "darwin" and shutil.which("osascript"):
                script = (
                    "display notification "
                    f"\"{self._escape(message)}\" with title \"{self._escape(title)}\""
                )
                result = subprocess.run(
                    ["osascript", "-e", script],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                sent = result.returncode == 0
            elif system_name == "linux" and shutil.which("notify-send"):
                result = subprocess.run(
                    ["notify-send", title, message],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                sent = result.returncode == 0
        except Exception:
            sent = False

        if not sent:
            self.stream.write(f"[通知] {title}: {message}\n")
            self.stream.flush()

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"')
