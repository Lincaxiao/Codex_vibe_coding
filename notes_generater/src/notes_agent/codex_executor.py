from __future__ import annotations

import json
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .path_utils import validate_path_component
from .subprocess_stream import run_process_streaming

DEFAULT_CODEX_EXEC_TIMEOUT_SECONDS = 30 * 60
DEFAULT_CODEX_VERSION_TIMEOUT_SECONDS = 20


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _default_run_id() -> str:
    timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"run_{timestamp}_{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True)
class CodexRunRequest:
    project_root: Path
    notes_root: Path
    prompt: str
    run_id: str | None = None
    model: str | None = None
    search_enabled: bool = False
    max_retries: int = 2
    extra_allowed_dirs: list[Path] | None = None


@dataclass(frozen=True)
class CodexRunResult:
    run_id: str
    run_dir: Path
    success: bool
    attempts: int
    exit_code: int
    prompt_path: Path
    stdout_log_path: Path
    last_message_path: Path
    run_manifest_path: Path
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "run_dir": str(self.run_dir),
            "success": self.success,
            "attempts": self.attempts,
            "exit_code": self.exit_code,
            "prompt_path": str(self.prompt_path),
            "stdout_log_path": str(self.stdout_log_path),
            "last_message_path": str(self.last_message_path),
            "run_manifest_path": str(self.run_manifest_path),
            "error": self.error,
        }


class CodexExecutor:
    def __init__(
        self,
        *,
        exec_timeout_seconds: int = DEFAULT_CODEX_EXEC_TIMEOUT_SECONDS,
        version_timeout_seconds: int = DEFAULT_CODEX_VERSION_TIMEOUT_SECONDS,
        progress_interval_seconds: float = 10.0,
    ) -> None:
        if exec_timeout_seconds <= 0:
            raise ValueError(f"exec_timeout_seconds must be > 0, got {exec_timeout_seconds}")
        if version_timeout_seconds <= 0:
            raise ValueError(f"version_timeout_seconds must be > 0, got {version_timeout_seconds}")
        if progress_interval_seconds <= 0:
            raise ValueError(f"progress_interval_seconds must be > 0, got {progress_interval_seconds}")
        self.exec_timeout_seconds = exec_timeout_seconds
        self.version_timeout_seconds = version_timeout_seconds
        self.progress_interval_seconds = progress_interval_seconds

    def run(
        self,
        request: CodexRunRequest,
        *,
        progress_callback: Callable[[str], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> CodexRunResult:
        if request.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {request.max_retries}")

        project_root = request.project_root.expanduser().resolve()
        notes_root = request.notes_root.expanduser().resolve()
        extra_dirs = self._normalize_extra_allowed_dirs(
            request.extra_allowed_dirs,
            project_root=project_root,
            notes_root=notes_root,
        )
        run_id = (
            validate_path_component(request.run_id, field_name="run_id")
            if request.run_id is not None
            else _default_run_id()
        )
        run_dir = project_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        prompt_path = run_dir / "prompt.md"
        stdout_log_path = run_dir / "codex_stdout.log"
        last_message_path = run_dir / "codex_last_message.md"
        run_manifest_path = run_dir / "run_manifest.json"
        prompt_path.write_text(request.prompt, encoding="utf-8")
        self._emit_progress(
            progress_callback,
            (
                f"[codex] 启动 run_id={run_id}，最多尝试 {request.max_retries + 1} 次 "
                f"(单次超时 {self.exec_timeout_seconds}s，理论最长约 {(request.max_retries + 1) * self.exec_timeout_seconds}s)"
            ),
        )

        codex_version = self._read_codex_version()
        attempts_log: list[dict[str, Any]] = []
        final_exit_code = 1
        final_error: str | None = None
        combined_stdout_log: list[str] = []

        for attempt in range(1, request.max_retries + 2):
            if cancel_check is not None and cancel_check():
                final_exit_code = 130
                final_error = "cancelled by user"
                attempts_log.append(
                    {
                        "attempt": attempt,
                        "started_at": _now_iso(),
                        "ended_at": _now_iso(),
                        "exit_code": 130,
                        "retry_reason": "cancelled",
                    }
                )
                self._emit_progress(progress_callback, f"[codex] attempt {attempt} 已取消")
                break
            started_at = _now_iso()
            self._emit_progress(
                progress_callback,
                f"[codex] attempt {attempt}/{request.max_retries + 1} 开始",
            )
            command = self._build_command(
                request=request,
                project_root=project_root,
                notes_root=notes_root,
                extra_allowed_dirs=extra_dirs,
                last_message_path=last_message_path,
            )
            timed_out = False
            timeout_error = f"codex exec timed out after {self.exec_timeout_seconds}s"
            launch_error: str | None = None
            cancelled = False
            heartbeat = self._start_attempt_heartbeat(
                progress_callback=progress_callback,
                attempt=attempt,
                total_attempts=request.max_retries + 1,
            )
            try:
                if cancel_check is None:
                    completed = subprocess.run(
                        command,
                        cwd=project_root,
                        text=True,
                        capture_output=True,
                        check=False,
                        timeout=self.exec_timeout_seconds,
                    )
                    exit_code = completed.returncode
                    stdio = self._merge_stdio(completed.stdout, completed.stderr)
                else:
                    exit_code, stdio, timed_out, cancelled, launch_error = self._run_exec_with_cancel(
                        command=command,
                        cwd=project_root,
                        timeout_seconds=self.exec_timeout_seconds,
                        cancel_check=cancel_check,
                    )
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                exit_code = 124
                stdio = self._merge_stdio(
                    self._timeout_output_text(exc.stdout),
                    self._timeout_output_text(exc.stderr),
                )
                stdio = f"{stdio}\n{timeout_error}".strip()
                self._emit_progress(
                    progress_callback,
                    f"[codex] attempt {attempt} 超时（>{self.exec_timeout_seconds}s）",
                )
            except OSError as exc:
                exit_code = 127
                launch_error = f"failed to launch codex: {exc}"
                stdio = launch_error
                self._emit_progress(progress_callback, f"[codex] 启动失败：{exc}")
            finally:
                self._stop_attempt_heartbeat(heartbeat)
            ended_at = _now_iso()
            final_exit_code = exit_code
            combined_stdout_log.append(
                f"=== attempt {attempt} ({started_at} -> {ended_at}) ===\n{stdio}\n"
            )

            attempts_log.append(
                {
                    "attempt": attempt,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "exit_code": exit_code,
                    "retry_reason": None,
                }
            )

            if cancelled:
                final_error = "cancelled by user"
                attempts_log[-1]["retry_reason"] = "cancelled"
                self._emit_progress(progress_callback, f"[codex] attempt {attempt} 已取消")
                break

            if exit_code == 0:
                final_error = None
                self._emit_progress(progress_callback, f"[codex] attempt {attempt} 成功")
                break

            if launch_error is not None:
                final_error = launch_error
            else:
                final_error = timeout_error if timed_out else self._extract_error(stdio) or f"codex exited with {exit_code}"
            if attempt <= request.max_retries and (timed_out or self._is_retryable_failure(stdio)):
                attempts_log[-1]["retry_reason"] = "timeout" if timed_out else "retryable_failure"
                reason = "timeout" if timed_out else "retryable_failure"
                self._emit_progress(
                    progress_callback,
                    f"[codex] attempt {attempt} 失败（{reason}），准备重试",
                )
                continue
            self._emit_progress(
                progress_callback,
                f"[codex] attempt {attempt} 失败（exit_code={exit_code}）",
            )
            break

        stdout_log_path.write_text("".join(combined_stdout_log), encoding="utf-8")
        if not last_message_path.exists():
            last_message_path.write_text("", encoding="utf-8")

        manifest = {
            "run_id": run_id,
            "project_root": str(project_root),
            "notes_root": str(notes_root),
            "model": request.model,
            "codex_cli_version": codex_version,
            "sandbox_mode": "workspace-write",
            "ask_for_approval_mode": "never",
            "search_enabled": request.search_enabled,
            "network_enabled": request.search_enabled,
            "writable_dirs": [str(project_root), str(notes_root), *[str(path) for path in extra_dirs]],
            "max_retries": request.max_retries,
            "attempts": attempts_log,
            "final_exit_code": final_exit_code,
            "success": final_exit_code == 0,
            "created_at": _now_iso(),
        }
        self._write_json(run_manifest_path, manifest)
        self._emit_progress(
            progress_callback,
            f"[codex] 结束 success={final_exit_code == 0}，日志目录：{run_dir}",
        )

        return CodexRunResult(
            run_id=run_id,
            run_dir=run_dir,
            success=final_exit_code == 0,
            attempts=len(attempts_log),
            exit_code=final_exit_code,
            prompt_path=prompt_path,
            stdout_log_path=stdout_log_path,
            last_message_path=last_message_path,
            run_manifest_path=run_manifest_path,
            error=final_error,
        )

    def probe_cli(
        self,
        *,
        cancel_check: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        version = self._read_codex_version(cancel_check=cancel_check)
        if version == "unknown (cancelled)":
            return {
                "available": False,
                "version": version,
                "error": "cancelled by user",
                "cancelled": True,
            }
        if version.startswith("unknown"):
            return {
                "available": False,
                "version": version,
                "error": "codex CLI unavailable",
                "cancelled": False,
            }
        return {
            "available": True,
            "version": version,
            "error": None,
            "cancelled": False,
        }

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

    def _start_attempt_heartbeat(
        self,
        *,
        progress_callback: Callable[[str], None] | None,
        attempt: int,
        total_attempts: int,
    ) -> tuple[threading.Event, threading.Thread] | None:
        if progress_callback is None:
            return None

        stop_event = threading.Event()
        started_at = time.monotonic()

        def _heartbeat() -> None:
            while not stop_event.wait(self.progress_interval_seconds):
                elapsed = int(time.monotonic() - started_at)
                remaining = max(self.exec_timeout_seconds - elapsed, 0)
                self._emit_progress(
                    progress_callback,
                    f"[codex] attempt {attempt}/{total_attempts} 进行中，已等待 {elapsed}s，距超时剩余 {remaining}s",
                )

        thread = threading.Thread(target=_heartbeat, daemon=True)
        thread.start()
        return (stop_event, thread)

    def _stop_attempt_heartbeat(self, heartbeat: tuple[threading.Event, threading.Thread] | None) -> None:
        if heartbeat is None:
            return
        stop_event, thread = heartbeat
        stop_event.set()
        thread.join(timeout=0.2)

    def _build_command(
        self,
        *,
        request: CodexRunRequest,
        project_root: Path,
        notes_root: Path,
        extra_allowed_dirs: list[Path],
        last_message_path: Path,
    ) -> list[str]:
        command = [
            "codex",
            "--ask-for-approval",
            "never",
            "exec",
            "--cd",
            str(project_root),
            "--sandbox",
            "workspace-write",
            "--add-dir",
            str(notes_root),
            "--skip-git-repo-check",
            "--output-last-message",
            str(last_message_path),
        ]
        for path in extra_allowed_dirs:
            command.extend(["--add-dir", str(path)])
        if request.model:
            command.extend(["--model", request.model])
        if request.search_enabled:
            command.append("--search")
        command.append(request.prompt)
        return command

    def _run_exec_with_cancel(
        self,
        *,
        command: list[str],
        cwd: Path,
        timeout_seconds: int,
        cancel_check: Callable[[], bool],
    ) -> tuple[int, str, bool, bool, str | None]:
        result = run_process_streaming(
            command=command,
            cwd=cwd,
            timeout_seconds=timeout_seconds,
            cancel_check=cancel_check,
        )
        if result.launch_error is not None:
            error = result.launch_error.replace("failed to launch process", "failed to launch codex", 1)
            return (127, error, False, False, error)

        stdio = self._merge_stdio(result.stdout, result.stderr)
        if result.timed_out:
            stdio = f"{stdio}\ncodex exec timed out after {timeout_seconds}s".strip()
            return (124, stdio, True, False, None)
        if result.cancelled:
            stdio = f"{stdio}\ncancelled by user".strip()
            return (130, stdio, False, True, None)
        return (result.exit_code, stdio, False, False, None)

    def _normalize_extra_allowed_dirs(
        self,
        raw_paths: list[Path] | None,
        *,
        project_root: Path,
        notes_root: Path,
    ) -> list[Path]:
        if not raw_paths:
            return []
        normalized: list[Path] = []
        seen: set[str] = {str(project_root), str(notes_root)}
        for raw in raw_paths:
            path = Path(raw).expanduser().resolve()
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(path)
        return normalized

    def _read_codex_version(
        self,
        *,
        cancel_check: Callable[[], bool] | None = None,
    ) -> str:
        if cancel_check is not None:
            result = run_process_streaming(
                command=["codex", "--version"],
                cwd=None,
                timeout_seconds=self.version_timeout_seconds,
                cancel_check=cancel_check,
            )
            if result.cancelled:
                return "unknown (cancelled)"
            if result.timed_out:
                return f"unknown (timeout>{self.version_timeout_seconds}s)"
            if result.launch_error is not None:
                return "unknown (codex-not-found)"
            stdio = self._merge_stdio(result.stdout, result.stderr)
            line = self._first_nonempty_line(stdio)
            return line or "unknown"

        try:
            completed = subprocess.run(
                ["codex", "--version"],
                text=True,
                capture_output=True,
                check=False,
                timeout=self.version_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return f"unknown (timeout>{self.version_timeout_seconds}s)"
        except OSError:
            return "unknown (codex-not-found)"
        stdio = self._merge_stdio(completed.stdout, completed.stderr)
        line = self._first_nonempty_line(stdio)
        return line or "unknown"

    def _is_retryable_failure(self, stdio: str) -> bool:
        text = stdio.lower()
        retryable_markers = (
            "timeout",
            "timed out",
            "network",
            "stream disconnected",
            "error sending request",
            "reconnecting",
            "connection reset",
            "connection refused",
            "temporarily unavailable",
            "stream error",
            "502",
            "503",
            "504",
        )
        return any(marker in text for marker in retryable_markers)

    def _merge_stdio(self, stdout: str, stderr: str) -> str:
        chunks = []
        if stdout:
            chunks.append(stdout.rstrip("\n"))
        if stderr:
            chunks.append(stderr.rstrip("\n"))
        return "\n".join(chunks).strip()

    def _first_nonempty_line(self, text: str) -> str | None:
        for line in text.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return None

    def _extract_error(self, text: str) -> str | None:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return None

        for line in lines:
            if line.lower().startswith("error:"):
                return line

        for line in lines:
            if not line.lower().startswith("warning:"):
                return line

        return lines[0]

    def _timeout_output_text(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
