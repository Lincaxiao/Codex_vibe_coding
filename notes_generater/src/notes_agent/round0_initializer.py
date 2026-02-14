from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Round0InitResult:
    notes_root: Path
    created_files: list[str]
    updated_files: list[str]
    skipped_files: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "notes_root": str(self.notes_root),
            "created_files": self.created_files,
            "updated_files": self.updated_files,
            "skipped_files": self.skipped_files,
        }


class Round0Initializer:
    def initialize(
        self,
        *,
        project_root: Path | str,
        notes_root: Path | str,
        course_id: str | None = None,
        force: bool = False,
        enable_flashcards: bool = True,
    ) -> Round0InitResult:
        project = Path(project_root).expanduser().resolve()
        notes = Path(notes_root).expanduser().resolve()
        notes.mkdir(parents=True, exist_ok=True)

        created_files: list[str] = []
        updated_files: list[str] = []
        skipped_files: list[str] = []

        now = datetime.now(tz=timezone.utc).isoformat()
        course = course_id or "unknown-course"
        manifest_template = self._manifest_template(course_id=course, generated_at=now)

        files_to_write: dict[Path, str] = {
            notes / "index" / "manifest.yml": manifest_template,
            notes / "index" / "questions_backlog.md": self._questions_backlog_template(),
            notes / "index" / "glossary.md": self._glossary_template(),
            notes / "notes" / "lectures" / "README.md": self._lectures_readme_template(),
            notes / "notes" / "cheatsheet.md": self._cheatsheet_template(),
            notes / "review" / "feedback.md": self._feedback_template(),
            notes / "review" / "rubric.md": self._rubric_template(),
            notes / "scripts" / "check_notes.py": self._check_notes_py_template(),
            notes / "scripts" / "check.sh": self._check_sh_template(),
        }
        if enable_flashcards:
            files_to_write[notes / "notes" / "flashcards.csv"] = self._flashcards_template()

        for path, content in files_to_write.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            if not path.exists():
                path.write_text(content, encoding="utf-8")
                created_files.append(str(path))
                continue

            if force:
                path.write_text(content, encoding="utf-8")
                updated_files.append(str(path))
            else:
                skipped_files.append(str(path))

        check_sh_path = notes / "scripts" / "check.sh"
        if check_sh_path.exists():
            check_sh_path.chmod(0o755)
            if str(check_sh_path) not in created_files and str(check_sh_path) not in updated_files:
                skipped_files.append(str(check_sh_path))

        project_round0_marker = project / "state" / "round0_initialized_at.txt"
        project_round0_marker.parent.mkdir(parents=True, exist_ok=True)
        marker_existed = project_round0_marker.exists()
        if (not marker_existed) or force:
            project_round0_marker.write_text(now + "\n", encoding="utf-8")
            if marker_existed:
                updated_files.append(str(project_round0_marker))
            else:
                created_files.append(str(project_round0_marker))
        else:
            skipped_files.append(str(project_round0_marker))

        # Deduplicate while preserving order.
        created_files = list(dict.fromkeys(created_files))
        updated_files = list(dict.fromkeys(updated_files))
        skipped_files = list(dict.fromkeys(skipped_files))

        return Round0InitResult(
            notes_root=notes,
            created_files=created_files,
            updated_files=updated_files,
            skipped_files=skipped_files,
        )

    def _manifest_template(self, *, course_id: str, generated_at: str) -> str:
        return (
            "version: 1\n"
            f"course_id: {course_id}\n"
            "language: zh-CN\n"
            "review_granularity: lecture\n"
            "human_review_timing: final_only\n"
            f"generated_at: {generated_at}\n"
        )

    def _questions_backlog_template(self) -> str:
        return (
            "# Questions Backlog\n\n"
            "- [ ] Add unresolved questions here.\n"
        )

    def _glossary_template(self) -> str:
        return (
            "# Glossary\n\n"
            "| Term | Definition |\n"
            "| --- | --- |\n"
        )

    def _lectures_readme_template(self) -> str:
        return (
            "# Lectures\n\n"
            "Put generated lecture markdown files in this folder.\n"
        )

    def _cheatsheet_template(self) -> str:
        return (
            "# Cheatsheet\n\n"
            "Final quick reference will be consolidated here.\n"
        )

    def _flashcards_template(self) -> str:
        return "front,back,source\n"

    def _feedback_template(self) -> str:
        return (
            "# Final Review Feedback\n\n"
            "- [ ] Add requested changes in checklist form.\n"
        )

    def _rubric_template(self) -> str:
        return (
            "# Review Rubric\n\n"
            "## Structure\n"
            "- Lecture organization is consistent.\n\n"
            "## Correctness\n"
            "- Claims map to sources.\n\n"
            "## Readability\n"
            "- Explanations are concise and clear.\n"
        )

    def _check_sh_template(self) -> str:
        return (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n\n"
            'SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
            'NOTES_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"\n'
            'PROJECT_ROOT="${1:-}"\n\n'
            'if [[ -z "${PROJECT_ROOT}" ]]; then\n'
            '  echo "Usage: check.sh <project_root>" >&2\n'
            "  exit 2\n"
            "fi\n\n"
            'python3 "${SCRIPT_DIR}/check_notes.py" \\\n'
            '  --notes-root "${NOTES_ROOT}" \\\n'
            '  --project-root "${PROJECT_ROOT}"\n'
        )

    def _check_notes_py_template(self) -> str:
        return (
            "#!/usr/bin/env python3\n"
            "from __future__ import annotations\n\n"
            "import argparse\n"
            "import json\n"
            "import re\n"
            "from pathlib import Path\n\n"
            "REQUIRED_PATHS = [\n"
            '    "index/manifest.yml",\n'
            '    "index/questions_backlog.md",\n'
            '    "index/glossary.md",\n'
            '    "notes/cheatsheet.md",\n'
            '    "review/feedback.md",\n'
            '    "review/rubric.md",\n'
            '    "scripts/check_notes.py",\n'
            '    "scripts/check.sh",\n'
            "]\n\n"
            "ZH_CHAR_RE = re.compile(r\"[\\u4e00-\\u9fff]\")\n"
            "LATIN_CHAR_RE = re.compile(r\"[A-Za-z]\")\n\n"
            "def strip_code_blocks(text: str) -> str:\n"
            "    lines = text.splitlines()\n"
            "    in_code = False\n"
            "    kept = []\n"
            "    for line in lines:\n"
            "        if line.strip().startswith('```'):\n"
            "            in_code = not in_code\n"
            "            continue\n"
            "        if not in_code:\n"
            "            kept.append(line)\n"
            "    return '\\n'.join(kept)\n\n"
            "def chinese_ratio(text: str) -> float:\n"
            "    zh = len(ZH_CHAR_RE.findall(text))\n"
            "    latin = len(LATIN_CHAR_RE.findall(text))\n"
            "    total = zh + latin\n"
            "    if total == 0:\n"
            "        return 1.0\n"
            "    return zh / total\n\n"
            "def collect_errors(notes_root: Path) -> tuple[list[str], list[str], dict[str, float]]:\n"
            "    errors: list[str] = []\n"
            "    warnings: list[str] = []\n"
            "    ratios: dict[str, float] = {}\n\n"
            "    for rel in REQUIRED_PATHS:\n"
            "        if not (notes_root / rel).exists():\n"
            "            errors.append(f\"missing required path: {rel}\")\n\n"
            "    lecture_dir = notes_root / 'notes' / 'lectures'\n"
            "    if not lecture_dir.exists():\n"
            "        errors.append(\"missing required path: notes/lectures\")\n"
            "    else:\n"
            "        lecture_files = sorted(lecture_dir.glob('*.md'))\n"
            "        for path in lecture_files:\n"
            "            text = path.read_text(encoding='utf-8')\n"
            "            clean_text = strip_code_blocks(text)\n"
            "            ratio = chinese_ratio(clean_text)\n"
            "            ratios[str(path)] = ratio\n"
            "            if len(clean_text.strip()) >= 80 and ratio < 0.75:\n"
            "                errors.append(f\"low Chinese ratio in {path}: {ratio:.3f}\")\n"
            "            if 'Source:' not in text and len(clean_text.strip()) >= 120:\n"
            "                warnings.append(f\"missing Source tag in {path}\")\n\n"
            "    return errors, warnings, ratios\n\n"
            "def main() -> int:\n"
            "    parser = argparse.ArgumentParser()\n"
            "    parser.add_argument('--notes-root', required=True, type=Path)\n"
            "    parser.add_argument('--project-root', required=True, type=Path)\n"
            "    args = parser.parse_args()\n\n"
            "    notes_root = args.notes_root.expanduser().resolve()\n"
            "    project_root = args.project_root.expanduser().resolve()\n\n"
            "    errors, warnings, ratios = collect_errors(notes_root)\n"
            "    payload = {\n"
            "        'passed': len(errors) == 0,\n"
            "        'errors': errors,\n"
            "        'warnings': warnings,\n"
            "        'metrics': {\n"
            "            'chinese_ratio_by_file': ratios,\n"
            "        },\n"
            "        'notes_root': str(notes_root),\n"
            "        'project_root': str(project_root),\n"
            "    }\n"
            "    print(json.dumps(payload, ensure_ascii=False, indent=2))\n"
            "    return 0 if payload['passed'] else 1\n\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(main())\n"
        )
