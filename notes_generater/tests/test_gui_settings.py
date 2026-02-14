from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

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

    def test_load_invalid_json_falls_back_to_defaults(self) -> None:
        with TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text("{broken-json\n", encoding="utf-8")
            settings = load_gui_settings(settings_path)
            self.assertEqual(settings, GuiSettings())

    def test_from_dict_parses_boolean_and_int_safely(self) -> None:
        payload = {
            "pause_after_each_round": "false",
            "search_enabled": "true",
            "max_changed_lines": "not-an-int",
            "max_changed_files": None,
        }
        settings = GuiSettings.from_dict(payload)
        self.assertFalse(settings.pause_after_each_round)
        self.assertTrue(settings.search_enabled)
        self.assertEqual(settings.max_changed_lines, 500)
        self.assertEqual(settings.max_changed_files, 20)

    def test_load_settings_handles_os_error(self) -> None:
        with TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text("{}", encoding="utf-8")
            with mock.patch("pathlib.Path.open", side_effect=PermissionError("denied")):
                settings = load_gui_settings(settings_path)
            self.assertEqual(settings, GuiSettings())

    def test_save_settings_handles_os_error(self) -> None:
        with TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings = GuiSettings(course_id="c1")
            with mock.patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
                saved = save_gui_settings(settings, settings_path)
            self.assertEqual(saved, settings_path)


if __name__ == "__main__":
    unittest.main()
