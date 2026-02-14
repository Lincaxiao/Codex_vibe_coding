from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class CheckRunResult:
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    payload: dict[str, Any] | None
    started_at: str
    finished_at: str
    check_script_path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "payload": self.payload,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "check_script_path": str(self.check_script_path),
        }


class CheckRunner:
    def run(
        self,
        *,
        project_root: Path | str,
        notes_root: Path | str,
        output_path: Path | str | None = None,
    ) -> CheckRunResult:
        project = Path(project_root).expanduser().resolve()
        notes = Path(notes_root).expanduser().resolve()
        check_script = notes / "scripts" / "check.sh"
        if not check_script.exists():
            raise FileNotFoundError(f"check script not found: {check_script}")

        started_at = _now_iso()
        completed = subprocess.run(
            [str(check_script), str(project)],
            text=True,
            capture_output=True,
            check=False,
        )
        finished_at = _now_iso()

        payload = self._parse_json_payload(completed.stdout)
        result = CheckRunResult(
            passed=completed.returncode == 0,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            payload=payload,
            started_at=started_at,
            finished_at=finished_at,
            check_script_path=check_script,
        )

        if output_path:
            self._write_json(Path(output_path), result.to_dict())
        return result

    def _parse_json_payload(self, stdout: str) -> dict[str, Any] | None:
        text = stdout.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
