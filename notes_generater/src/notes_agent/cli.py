from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .check_runner import CheckRunner
from .codex_executor import CodexExecutor, CodexRunRequest
from .models import CreateProjectRequest
from .project_service import ProjectService
from .round0_initializer import Round0Initializer
from .snapshot_service import SnapshotService
from .workflow_orchestrator import WorkflowOrchestrator


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

    run_parser = subparsers.add_parser(
        "run-codex", help="Run one codex exec round and persist prompt/stdout/manifest"
    )
    run_parser.add_argument("--project-root", required=True, type=Path)
    run_parser.add_argument("--notes-root", type=Path, help="Optional override; defaults to project config")
    prompt_group = run_parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Prompt text")
    prompt_group.add_argument("--prompt-file", type=Path, help="Prompt file path")
    run_parser.add_argument("--run-id", help="Optional run_id override")
    run_parser.add_argument("--model", help="Optional model override")
    run_parser.add_argument("--search", action="store_true", help="Enable codex web search")
    run_parser.add_argument("--max-retries", type=int, default=2, help="Retry count for retryable failures")

    init_round0_parser = subparsers.add_parser(
        "init-round0", help="Initialize notes_root scaffold and check scripts"
    )
    init_round0_parser.add_argument("--project-root", required=True, type=Path)
    init_round0_parser.add_argument("--notes-root", type=Path, help="Optional override; defaults to project config")
    init_round0_parser.add_argument("--force", action="store_true", help="Overwrite existing template files")
    init_round0_parser.add_argument(
        "--disable-flashcards",
        action="store_true",
        help="Do not create notes/flashcards.csv",
    )
    init_round0_parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Only scaffold files, do not run check script",
    )

    run_check_parser = subparsers.add_parser("run-check", help="Run notes_root/scripts/check.sh")
    run_check_parser.add_argument("--project-root", required=True, type=Path)
    run_check_parser.add_argument("--notes-root", type=Path, help="Optional override; defaults to project config")

    workflow_parser = subparsers.add_parser(
        "run-workflow",
        help="Run workflow rounds (round0/1/2/3/final) with per-round check",
    )
    workflow_parser.add_argument("--project-root", required=True, type=Path)
    workflow_parser.add_argument("--notes-root", type=Path, help="Optional override; defaults to project config")
    workflow_parser.add_argument(
        "--from-round",
        choices=["round0", "round1", "round2", "round3", "final"],
        default="round1",
    )
    workflow_parser.add_argument(
        "--to-round",
        choices=["round0", "round1", "round2", "round3", "final"],
        default="final",
    )
    workflow_parser.add_argument(
        "--target-lecture",
        dest="target_lectures",
        action="append",
        help="Target lecture identifier (repeatable)",
    )
    workflow_parser.add_argument(
        "--allow-external-refs",
        action="store_true",
        help="Allow external references in Final round prompt",
    )
    workflow_parser.add_argument(
        "--search",
        action="store_true",
        help="Enable codex web search during workflow rounds",
    )
    workflow_parser.add_argument("--max-retries", type=int, default=2)
    workflow_parser.add_argument("--workflow-run-id", help="Optional workflow run id override")
    workflow_parser.add_argument(
        "--disable-auto-repair",
        action="store_true",
        help="Disable automatic single repair run when check fails",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    service = ProjectService()
    snapshot_service = SnapshotService()
    codex_executor = CodexExecutor()
    round0_initializer = Round0Initializer()
    check_runner = CheckRunner()
    workflow_orchestrator = WorkflowOrchestrator(
        project_service=service,
        codex_executor=codex_executor,
        check_runner=check_runner,
        round0_initializer=round0_initializer,
    )

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

    if args.command == "run-codex":
        if args.prompt:
            prompt_text = args.prompt
        else:
            prompt_text = args.prompt_file.read_text(encoding="utf-8")

        notes_root = args.notes_root
        if not notes_root:
            config = service.load_project_config(args.project_root)
            notes_root = config.notes_root

        result = codex_executor.run(
            CodexRunRequest(
                project_root=args.project_root,
                notes_root=notes_root,
                prompt=prompt_text,
                run_id=args.run_id,
                model=args.model,
                search_enabled=args.search,
                max_retries=args.max_retries,
            )
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0 if result.success else 1

    if args.command == "init-round0":
        config = service.load_project_config(args.project_root)
        notes_root = args.notes_root or config.notes_root

        init_result = round0_initializer.initialize(
            project_root=args.project_root,
            notes_root=notes_root,
            course_id=config.course_id,
            force=args.force,
            enable_flashcards=not args.disable_flashcards,
        )

        response: dict[str, object] = {
            "round": "round0",
            "project_root": str(Path(args.project_root).expanduser().resolve()),
            "notes_root": str(Path(notes_root).expanduser().resolve()),
            "scaffold": init_result.to_dict(),
        }

        if not args.skip_check:
            run_id = f"round0_{datetime.now(tz=timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
            run_dir = Path(args.project_root).expanduser().resolve() / "runs" / run_id
            run_dir.mkdir(parents=True, exist_ok=False)
            check_result = check_runner.run(
                project_root=args.project_root,
                notes_root=notes_root,
                output_path=run_dir / "check_result.json",
            )
            response["run_id"] = run_id
            response["check"] = check_result.to_dict()
            print(json.dumps(response, indent=2, ensure_ascii=False))
            return 0 if check_result.passed else 1

        print(json.dumps(response, indent=2, ensure_ascii=False))
        return 0

    if args.command == "run-check":
        config = service.load_project_config(args.project_root)
        notes_root = args.notes_root or config.notes_root
        check_result = check_runner.run(project_root=args.project_root, notes_root=notes_root)
        print(json.dumps(check_result.to_dict(), indent=2, ensure_ascii=False))
        return 0 if check_result.passed else 1

    if args.command == "run-workflow":
        result = workflow_orchestrator.run(
            project_root=args.project_root,
            notes_root=args.notes_root,
            from_round=args.from_round,
            to_round=args.to_round,
            target_lectures=args.target_lectures or [],
            allow_external_refs=args.allow_external_refs,
            search_enabled=args.search,
            max_retries=args.max_retries,
            workflow_run_id=args.workflow_run_id,
            auto_repair_check_failures=not args.disable_auto_repair,
        )
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0 if result.status == "succeeded" else 1

    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
