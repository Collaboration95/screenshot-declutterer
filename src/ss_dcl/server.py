"""Managed LiteRT server process: command resolution, pidfile ownership,
readiness polling, and start/stop lifecycle.

Ownership rule: this module only ever records and later kills the PID it
spawned itself (``LITERT_PIDFILE``). A live PID that isn't responding is
left alone — it may be the user's own server booting or a foreign process.
Logs go to the app state dir.
"""

import logging
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path

from src.ss_dcl import llm

logger = logging.getLogger(__name__)

LITERT_SERVE_CMD = os.environ.get("LITERT_SERVE_CMD", "litert-lm serve")
LITERT_SERVE_READY_TIMEOUT = 30  # seconds to wait for /v1/models after spawn
LITERT_PIDFILE = str(Path.home() / ".ss-dcl" / "litert.pid")
LITERT_LOG_FILE = str(Path.home() / ".ss-dcl" / "litert.log")
# Fallback binary: the sample venv used in the verified workflow.
LITERT_VENV_FALLBACK = str(Path.home() / "litert-lm" / ".venv" / "bin" / "litert-lm")


def _litert_serve_cmd() -> list[str]:
    """Resolve the serve command: env override, then PATH, then the sample venv."""
    parts = LITERT_SERVE_CMD.split()
    if not parts:
        raise ValueError("LITERT_SERVE_CMD is empty")
    resolved = shutil.which(parts[0])
    if resolved:
        return [resolved, *parts[1:]]
    if os.path.exists(LITERT_VENV_FALLBACK):
        return [LITERT_VENV_FALLBACK, *parts[1:]]
    return parts  # let Popen fail with a clear FileNotFoundError


def _read_litert_pid() -> int | None:
    """Read the pidfile; returns None when absent or malformed."""
    try:
        return int(Path(LITERT_PIDFILE).read_text().strip())
    except (FileNotFoundError, ValueError, OSError):
        return None


def _pid_alive(pid: int) -> bool:
    """True when a process with this pid exists (any owner)."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists, owned by another user


def start_server() -> tuple[bool, str]:
    """Start the LiteRT server unless one is already running.

    Returns ``(ok, message)``; the caller maps this to an HTTP status.
    """
    if llm._litert_healthy():
        return True, "LiteRT server is already running."

    pid = _read_litert_pid()
    if pid is not None and _pid_alive(pid):
        return (
            False,
            f"Process {pid} is already running and not responding — won't double-spawn. "
            f"Check {LITERT_LOG_FILE} or stop it manually.",
        )
    if pid is not None:  # stale pidfile
        Path(LITERT_PIDFILE).unlink(missing_ok=True)

    try:
        cmd = _litert_serve_cmd()
    except ValueError as exc:
        return False, str(exc)

    with open(LITERT_LOG_FILE, "ab") as log_handle:
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=str(Path.home()),
            )
        except FileNotFoundError:
            return (
                False,
                f"litert-lm not found — install it or set LITERT_SERVE_CMD. Tried: {cmd}",
            )

    Path(LITERT_PIDFILE).write_text(str(proc.pid))

    deadline = time.monotonic() + LITERT_SERVE_READY_TIMEOUT
    while time.monotonic() < deadline:
        # Bust the TTL-cached negative verdict so each poll is a real probe.
        llm.reset_health_cache()
        if llm._litert_healthy():
            return True, f"LiteRT server started (pid {proc.pid}) and is ready."
        time.sleep(0.5)
    return (
        False,
        f"LiteRT server started (pid {proc.pid}) but not ready within "
        f"{LITERT_SERVE_READY_TIMEOUT}s. See {LITERT_LOG_FILE}.",
    )


def stop_server() -> tuple[dict, int]:
    """Stop a LiteRT server this app started. Never touches foreign PIDs.

    Returns ``(payload, status_code)`` ready to be returned as JSON.
    """
    pid = _read_litert_pid()
    if pid is None:
        return {"ok": False, "error": "No LiteRT server was started from this app."}, 409
    if not _pid_alive(pid):
        Path(LITERT_PIDFILE).unlink(missing_ok=True)
        llm.reset_health_cache()
        return {"ok": True, "message": "Server was already stopped; stale pidfile cleaned up."}, 200
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        Path(LITERT_PIDFILE).unlink(missing_ok=True)
        llm.reset_health_cache()
        return {"ok": True, "message": "Server was already stopped."}, 200
    except PermissionError:
        msg = f"Process {pid} isn't yours — refusing to kill it."
        return {"ok": False, "error": msg}, 403

    deadline = time.monotonic() + 5
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.2)
    Path(LITERT_PIDFILE).unlink(missing_ok=True)
    llm.reset_health_cache()
    return {"ok": True, "message": f"LiteRT server (pid {pid}) stopped."}, 200
