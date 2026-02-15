from __future__ import annotations

import unittest

from notes_agent.cli import build_parser


class CliSingleCourseParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = build_parser()

    def test_create_project_requires_course_root(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            self.parser.parse_args(["create-project", "--course-id", "ece364"])
        self.assertEqual(ctx.exception.code, 2)

    def test_create_project_accepts_course_root(self) -> None:
        args = self.parser.parse_args(
            [
                "create-project",
                "--course-root",
                "/tmp/ECE364",
                "--course-id",
                "ece364",
            ]
        )
        self.assertEqual(args.command, "create-project")
        self.assertEqual(str(args.course_root), "/tmp/ECE364")
        self.assertEqual(args.course_id, "ece364")

    def test_list_projects_command_removed(self) -> None:
        with self.assertRaises(SystemExit) as ctx:
            self.parser.parse_args(["list-projects", "--workspace-root", "/tmp/ws"])
        self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
