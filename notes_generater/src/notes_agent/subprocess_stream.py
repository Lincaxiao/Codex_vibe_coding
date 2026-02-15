from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Callable


@dataclass(frozen=True)
class StreamProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    cancelled: bool
    launch_error: str | None


def run_process_streaming(
    *,
    command: list[str],
    cwd: Path | None,
    timeout_seconds: int,
    cancel_check: Callable[[], bool] | None,
    poll_interval_seconds: float = 0.1,
) -> StreamProcessResult:
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            text=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        error = f"failed to launch process: {exc}"
        return StreamProcessResult(
            exit_code=127,
            stdout="",
            stderr=error,
            timed_out=False,
            cancelled=False,
            launch_error=error,
        )

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []

    stdout_thread = threading.Thread(
        target=_drain_pipe,
        args=(process.stdout, stdout_chunks),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain_pipe,
        args=(process.stderr, stderr_chunks),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    cancelled = False
    while True:
        if cancel_check is not None and cancel_check():
            cancelled = True
            _terminate_process(process)
            break
        if process.poll() is not None:
            break
        if time.monotonic() >= deadline:
            timed_out = True
            _terminate_process(process)
            break
        time.sleep(poll_interval_seconds)

    if process.poll() is None:
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)

    stdout_text = b"".join(stdout_chunks).decode("utf-8", errors="replace")
    stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")
    return StreamProcessResult(
        exit_code=process.returncode if process.returncode is not None else 1,
        stdout=stdout_text,
        stderr=stderr_text,
        timed_out=timed_out,
        cancelled=cancelled,
        launch_error=None,
    )


def _drain_pipe(
    pipe: IO[bytes] | None,
    sink: list[bytes],
) -> None:
    if pipe is None:
        return
    try:
        while True:
            chunk = pipe.read(4096)
            if not chunk:
                break
            sink.append(chunk)
    finally:
        try:
            pipe.close()
        except OSError:
            return


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
