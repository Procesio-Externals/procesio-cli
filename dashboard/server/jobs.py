"""Background jobs for interactive setup steps that outlive one request.

Two shapes:
  * a plain job that runs a script to completion and streams its output
    (OAuth login: the tool opens a browser and self-completes on the localhost
    redirect), and
  * a signal job that launches a script which blocks for a stdin ENTER
    (web save-session: a headed browser opens, the human logs in, then the UI
    sends the signal to persist the session).

Jobs live in memory only. The dashboard is single-user and local; a restart just
drops in-flight logins, which the user re-runs.
"""
from __future__ import annotations

import subprocess
import threading
import time
import uuid
from typing import Any

from . import runner

_JOBS: dict[str, "Job"] = {}
_LOCK = threading.Lock()


class Job:
    def __init__(self, kind: str, argv: list[str], *, stdin_signal: bool):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.argv = argv
        self.stdin_signal = stdin_signal
        self.status = "starting"   # starting|awaiting_signal|running|done|failed
        self.logs: list[str] = []
        self.result: dict | None = None
        self.error: str | None = None
        self.created = time.time()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def _log(self, line: str):
        with self._lock:
            self.logs.append(line.rstrip("\n"))
            if len(self.logs) > 400:
                self.logs = self.logs[-400:]

    def start(self):
        cmd = [runner.python_exe(), str(runner.PROJECT_ROOT / "scripts" / self.argv[0]),
               *self.argv[1:]]
        try:
            self._proc = subprocess.Popen(
                cmd, cwd=str(runner.PROJECT_ROOT), text=True, encoding="utf-8",
                errors="replace", bufsize=1,
                stdin=subprocess.PIPE if self.stdin_signal else subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except Exception as e:  # noqa: BLE001
            self.status = "failed"
            self.error = f"could not launch: {e}"
            return
        self.status = "awaiting_signal" if self.stdin_signal else "running"
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        assert self._proc is not None
        for line in self._proc.stdout:  # blocks until each line / EOF
            self._log(line)
        self._proc.wait()
        result = runner._parse_json("\n".join(self.logs))
        if self._proc.returncode == 0 and isinstance(result, dict) and "error" not in result:
            self.status = "done"
            self.result = result
        else:
            self.status = "failed"
            if isinstance(result, dict) and "error" in result:
                self.error = result["error"].get("message") if isinstance(
                    result["error"], dict) else str(result["error"])
            else:
                self.error = (self.logs[-1] if self.logs else
                              f"exited with code {self._proc.returncode}")

    def signal(self) -> bool:
        """Send the ENTER that a save-session subprocess is blocking on."""
        if not (self._proc and self._proc.stdin and self.status == "awaiting_signal"):
            return False
        try:
            self._proc.stdin.write("\n")
            self._proc.stdin.flush()
            self.status = "running"
            return True
        except Exception:  # noqa: BLE001
            return False

    def wait(self, timeout: float) -> None:
        if self._proc:
            try:
                self._proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                pass

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"id": self.id, "kind": self.kind, "status": self.status,
                    "logs": list(self.logs[-40:]), "result": self.result,
                    "error": self.error}


def create(kind: str, argv: list[str], *, stdin_signal: bool = False) -> Job:
    job = Job(kind, argv, stdin_signal=stdin_signal)
    with _LOCK:
        _JOBS[job.id] = job
    job.start()
    return job


def get(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)
