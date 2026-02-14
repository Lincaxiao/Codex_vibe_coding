from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.gui_settings import GuiSettings, default_settings_path, load_gui_settings, save_gui_settings


class GuiSettingsTests(unittest.TestCase):
    def test_load_defaults_when_file_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "missing.json"
            settings = load_gui_settings(settings_path)
            self.assertEqual(settings.workspace_root, "")
            self.assertEqual(settings.from_round, "round0")

    def test_save_and_load_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            original = GuiSettings(
                workspace_root="/tmp/ws",
                course_id="cs61a",
                target_lecture="lecture01",
                from_round="round1",
                to_round="round3",
                max_changed_lines=300,
                max_changed_files=12,
                pause_after_each_round=True,
                search_enabled=True,
            )
            save_gui_settings(original, settings_path)
            loaded = load_gui_settings(settings_path)
            self.assertEqual(loaded, original)

    def test_default_settings_path_under_home(self) -> None:
        with TemporaryDirectory() as tmp:
            path = default_settings_path(Path(tmp))
            self.assertTrue(str(path).startswith(tmp))
            self.assertEqual(path.name, "settings.json")


if __name__ == "__main__":
    unittest.main()
