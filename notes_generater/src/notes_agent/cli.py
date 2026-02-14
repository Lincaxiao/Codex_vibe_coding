from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import CreateProjectRequest
from .project_service import ProjectService
from .snapshot_service import SnapshotService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Notes agent project tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create-project", help="Create a course project scaffold")
    create_parser.add_argument("--course-id", required=True, help="Unique course identifier")
    create_parser.add_argument("--workspace-root", type=Path, help="Workspace root containing projects/ and notes/")
    create_parser.add_argument("--project-root", type=Path, help="Explicit project_root override")
    create_parser.add_argument("--notes-root", type=Path, help="Explicit notes_root override")
    create_parser.add_argument(
        "--review-granularity",
        choices=["section", "lecture"],
        default="lecture",
        help="Review granularity",
    )
    create_parser.add_argument("--allow-existing", action="store_true", help="Allow existing project.yaml")

    show_parser = subparsers.add_parser("show-project", help="Show a project config")
    show_parser.add_argument("--project-root", required=True, type=Path)

    list_parser = subparsers.add_parser("list-projects", help="List projects under a workspace")
    list_parser.add_argument("--workspace-root", required=True, type=Path)

    snapshot_parser = subparsers.add_parser("snapshot-sources", help="Copy sources into read-only snapshot")
    snapshot_parser.add_argument("--project-root", required=True, type=Path)
    snapshot_parser.add_argument(
        "--source",
        dest="sources",
        action="append",
        required=True,
        type=Path,
        help="Source file or directory (repeatable)",
    )
    snapshot_parser.add_argument(
        "--lecture-mapping-file",
        type=Path,
        help="Optional JSON file: {\"/abs/source/path\": \"lecture_name\"}",
    )
    snapshot_parser.add_argument("--snapshot-id", help="Optional explicit snapshot id")

    verify_snapshot_parser = subparsers.add_parser(
        "verify-snapshot", help="Verify snapshot hashes from artifacts/source_hashes.json"
    )
    verify_snapshot_parser.add_argument("--project-root", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    service = ProjectService()
    snapshot_service = SnapshotService()

    if args.command == "create-project":
        request = CreateProjectRequest(
            course_id=args.course_id,
            workspace_root=args.workspace_root,
            project_root=args.project_root,
            notes_root=args.notes_root,
            review_granularity=args.review_granularity,
        )
        config = service.create_project(request, allow_existing=args.allow_existing)
        print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "show-project":
        config = service.load_project_config(args.project_root)
        print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "list-projects":
        configs = service.discover_workspace_projects(args.workspace_root)
        print(json.dumps([config.to_dict() for config in configs], indent=2, ensure_ascii=False))
        return 0

    if args.command == "snapshot-sources":
        lecture_mapping = None
        if args.lecture_mapping_file:
            lecture_mapping = json.loads(args.lecture_mapping_file.read_text(encoding="utf-8"))
        result = snapshot_service.create_snapshot(
            project_root=args.project_root,
            sources=args.sources,
            lecture_mapping=lecture_mapping,
            snapshot_id=args.snapshot_id,
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "verify-snapshot":
        result = snapshot_service.verify_snapshot_hashes(project_root=args.project_root)
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0 if result.valid else 1

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
