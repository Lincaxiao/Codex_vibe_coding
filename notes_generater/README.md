# notes-generater

PR1 scaffolding for a local macOS notes agent.

## What is implemented in PR1

- Workspace + multi-course project creation
- Default path mapping:
  - `projects/<course_id>` -> `project_root`
  - `notes/<course_id>` -> `notes_root`
- Project scaffold creation:
  - `project.yaml`
  - `state/session.json`
  - `state/round_status.json`
  - `runs/`
  - `artifacts/`
- Minimal CLI for create/show/list project
- Source snapshot + hash verification CLI
- Codex executor CLI (single run with prompt/stdout/manifest persistence)

## Run commands

```bash
PYTHONPATH=src python3 -m notes_agent.cli create-project --course-id "CS 61A" --workspace-root "/path/to/workspace"
PYTHONPATH=src python3 -m notes_agent.cli list-projects --workspace-root "/path/to/workspace"
PYTHONPATH=src python3 -m notes_agent.cli show-project --project-root "/path/to/workspace/projects/cs-61a"
PYTHONPATH=src python3 -m notes_agent.cli snapshot-sources --project-root "/path/to/workspace/projects/cs-61a" --source "/path/to/slides" --source "/path/to/code"
PYTHONPATH=src python3 -m notes_agent.cli verify-snapshot --project-root "/path/to/workspace/projects/cs-61a"
PYTHONPATH=src python3 -m notes_agent.cli run-codex --project-root "/path/to/workspace/projects/cs-61a" --prompt "请列出当前目录文件"
```

## Run tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q
```
