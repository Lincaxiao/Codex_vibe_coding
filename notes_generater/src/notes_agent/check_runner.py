from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .subprocess_stream import run_process_streaming

DEFAULT_CHECK_TIMEOUT_SECONDS = 5 * 60


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
    def __init__(self, *, timeout_seconds: int = DEFAULT_CHECK_TIMEOUT_SECONDS) -> None:
        if timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be > 0, got {timeout_seconds}")
        self.timeout_seconds = timeout_seconds

    def run(
        self,
        *,
        project_root: Path | str,
        notes_root: Path | str,
        output_path: Path | str | None = None,
        progress_callback: Callable[[str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> CheckRunResult:
        project = Path(project_root).expanduser().resolve()
        notes = Path(notes_root).expanduser().resolve()
        check_script = notes / "scripts" / "check.sh"
        if not check_script.exists():
            raise FileNotFoundError(f"check script not found: {check_script}")

        self._emit_progress(
            progress_callback,
            f"[check] 开始执行检查脚本：{check_script}",
        )
        started_at = _now_iso()
        timed_out = False
        cancelled = False
        try:
            if cancel_check is None:
                completed = subprocess.run(
                    [str(check_script), str(project)],
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=self.timeout_seconds,
                )
                exit_code = completed.returncode
                stdout = completed.stdout
                stderr = completed.stderr
            else:
                exit_code, stdout, stderr, timed_out, cancelled = self._run_with_cancel(
                    cmd=[str(check_script), str(project)],
                    timeout_seconds=self.timeout_seconds,
                    cancel_check=cancel_check,
                )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = 124
            stdout = self._timeout_output_text(exc.stdout)
            stderr = self._timeout_output_text(exc.stderr)
            timeout_error = f"check script timed out after {self.timeout_seconds}s"
            stderr = f"{stderr}\n{timeout_error}".strip()
            self._emit_progress(progress_callback, f"[check] 执行超时（>{self.timeout_seconds}s）")
        if cancelled:
            self._emit_progress(progress_callback, "[check] 已取消")
        finished_at = _now_iso()

        payload = self._parse_json_payload(stdout) if not timed_out and not cancelled else None
        result = CheckRunResult(
            passed=exit_code == 0,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            payload=payload,
            started_at=started_at,
            finished_at=finished_at,
            check_script_path=check_script,
        )
        self._emit_progress(
            progress_callback,
            f"[check] 执行完成：passed={result.passed}, exit_code={result.exit_code}",
        )

        if output_path:
            self._write_json(Path(output_path), result.to_dict())
            self._emit_progress(progress_callback, f"[check] 结果已写入：{Path(output_path)}")
        return result

    def _run_with_cancel(
        self,
        *,
        cmd: list[str],
        timeout_seconds: int,
        cancel_check: Callable[[], bool],
    ) -> tuple[int, str, str, bool, bool]:
        result = run_process_streaming(
            command=cmd,
            cwd=None,
            timeout_seconds=timeout_seconds,
            cancel_check=cancel_check,
        )
        if result.launch_error is not None:
            error = result.launch_error
            return (127, "", error, False, False)
        if result.timed_out:
            timeout_error = f"check script timed out after {timeout_seconds}s"
            stderr = f"{result.stderr}\n{timeout_error}".strip()
            return (124, result.stdout, stderr, True, False)
        if result.cancelled:
            stderr = f"{result.stderr}\ncancelled by user".strip()
            return (130, result.stdout, stderr, False, True)
        return (result.exit_code, result.stdout, result.stderr, False, False)

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

    def _timeout_output_text(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _emit_progress(
        self,
        progress_callback: Callable[[str], None] | None,
        message: str,
    ) -> None:
        if progress_callback is None:
            return
        try:
            progress_callback(message)
        except Exception:
            return
