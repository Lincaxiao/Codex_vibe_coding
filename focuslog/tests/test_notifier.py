from __future__ import annotations

import io
from types import SimpleNamespace
import unittest
from unittest import mock

from focuslog.notifier import Notifier


class TestNotifier(unittest.TestCase):
    def test_fallback_when_command_fails(self) -> None:
        stream = io.StringIO()
        notifier = Notifier(stream=stream)

        with mock.patch("focuslog.notifier.platform.system", return_value="Linux"), mock.patch(
            "focuslog.notifier.shutil.which", return_value="/usr/bin/notify-send"
        ), mock.patch(
            "focuslog.notifier.subprocess.run", return_value=SimpleNamespace(returncode=1)
        ):
            notifier.notify("FocusLog", "测试通知")

        self.assertIn("[通知] FocusLog: 测试通知", stream.getvalue())

    def test_no_fallback_when_command_succeeds(self) -> None:
        stream = io.StringIO()
        notifier = Notifier(stream=stream)

        with mock.patch("focuslog.notifier.platform.system", return_value="Linux"), mock.patch(
            "focuslog.notifier.shutil.which", return_value="/usr/bin/notify-send"
        ), mock.patch(
            "focuslog.notifier.subprocess.run", return_value=SimpleNamespace(returncode=0)
        ):
            notifier.notify("FocusLog", "测试通知")

        self.assertEqual(stream.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
