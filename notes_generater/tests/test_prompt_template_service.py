from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from notes_agent.prompt_template_service import (
    DEFAULT_PROMPT_TEMPLATES,
    PROMPT_TEMPLATE_KEYS,
    PromptTemplateService,
)


class PromptTemplateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PromptTemplateService()

    def test_load_defaults_when_file_missing(self) -> None:
        with TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            project_root.mkdir(parents=True, exist_ok=True)

            templates = self.service.load_templates(project_root=project_root)
            self.assertEqual(templates, DEFAULT_PROMPT_TEMPLATES)

    def test_save_and_load_templates_roundtrip(self) -> None:
        with TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            project_root.mkdir(parents=True, exist_ok=True)
            expected = dict(DEFAULT_PROMPT_TEMPLATES)
            expected["round1"] = "round1 custom {{lecture_scope}}"

            path = self.service.save_templates(project_root=project_root, templates=expected)
            loaded = self.service.load_templates(project_root=project_root)

            self.assertTrue(path.exists())
            self.assertEqual(loaded["round1"], "round1 custom {{lecture_scope}}")
            for key in PROMPT_TEMPLATE_KEYS:
                self.assertIn(key, loaded)

    def test_invalid_payload_falls_back_to_defaults(self) -> None:
        with TemporaryDirectory() as tmp:
            project_root = Path(tmp) / "project"
            project_root.mkdir(parents=True, exist_ok=True)
            path = self.service.template_path(project_root=project_root)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"round1": "", "unknown": "x"}, ensure_ascii=False), encoding="utf-8")

            loaded = self.service.load_templates(project_root=project_root)
            self.assertEqual(loaded["round1"], DEFAULT_PROMPT_TEMPLATES["round1"])
            self.assertNotIn("unknown", loaded)


if __name__ == "__main__":
    unittest.main()

