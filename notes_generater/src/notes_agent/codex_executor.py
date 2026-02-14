from __future__ import annotations

import json
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
    def run(self, request: CodexRunRequest) -> CodexRunResult:
        if request.max_retries < 0:
            raise ValueError(f"max_retries must be >= 0, got {request.max_retries}")

        project_root = request.project_root.expanduser().resolve()
        notes_root = request.notes_root.expanduser().resolve()
        run_id = request.run_id or _default_run_id()
        run_dir = project_root / "runs" / run_id
        run_dir.mkdir(parents=True, exist_ok=False)

        prompt_path = run_dir / "prompt.md"
        stdout_log_path = run_dir / "codex_stdout.log"
        last_message_path = run_dir / "codex_last_message.md"
        run_manifest_path = run_dir / "run_manifest.json"
        prompt_path.write_text(request.prompt, encoding="utf-8")

        codex_version = self._read_codex_version()
        attempts_log: list[dict[str, Any]] = []
        final_exit_code = 1
        final_error: str | None = None
        combined_stdout_log: list[str] = []

        for attempt in range(1, request.max_retries + 2):
            started_at = _now_iso()
            command = self._build_command(
                request=request,
                project_root=project_root,
                notes_root=notes_root,
                last_message_path=last_message_path,
            )
            completed = subprocess.run(
                command,
                cwd=project_root,
                text=True,
                capture_output=True,
                check=False,
            )
            ended_at = _now_iso()
            final_exit_code = completed.returncode
            stdio = self._merge_stdio(completed.stdout, completed.stderr)
            combined_stdout_log.append(
                f"=== attempt {attempt} ({started_at} -> {ended_at}) ===\n{stdio}\n"
            )

            attempts_log.append(
                {
                    "attempt": attempt,
                    "started_at": started_at,
                    "ended_at": ended_at,
                    "exit_code": completed.returncode,
                    "retry_reason": None,
                }
            )

            if completed.returncode == 0:
                final_error = None
                break

            final_error = self._extract_error(stdio) or f"codex exited with {completed.returncode}"
            if attempt <= request.max_retries and self._is_retryable_failure(stdio):
                attempts_log[-1]["retry_reason"] = "retryable_failure"
                continue
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
            "writable_dirs": [str(project_root), str(notes_root)],
            "max_retries": request.max_retries,
            "attempts": attempts_log,
            "final_exit_code": final_exit_code,
            "success": final_exit_code == 0,
            "created_at": _now_iso(),
        }
        self._write_json(run_manifest_path, manifest)

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

    def _build_command(
        self,
        *,
        request: CodexRunRequest,
        project_root: Path,
        notes_root: Path,
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
        if request.model:
            command.extend(["--model", request.model])
        if request.search_enabled:
            command.append("--search")
        command.append(request.prompt)
        return command

    def _read_codex_version(self) -> str:
        completed = subprocess.run(
            ["codex", "--version"],
            text=True,
            capture_output=True,
            check=False,
        )
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

    def _write_json(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(payload, fp, indent=2, ensure_ascii=False, sort_keys=True)
            fp.write("\n")
        temp_path.replace(path)
