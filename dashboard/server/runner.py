"""Subprocess bridge to the framework's own scripts.

The dashboard reads registry data by importing `registry` directly (fast, in
process). But anything that RUNS a tool/agent or writes a credential goes through
the existing scripts as a subprocess, so each runs in its own venv-correct process
exactly as it does from the terminal - the dashboard never reimplements a tool's
logic or its credential handling.

Every well-behaved tool emits exactly one JSON object on stdout (io.emit / io.fail)
and logs to stderr, so we parse stdout as JSON and keep stderr for diagnostics.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VENV_PY = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"


def python_exe() -> str:
    """The interpreter to launch scripts with. Prefer the project venv; the
    scripts also self-reexec into it, so this is belt-and-suspenders."""
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def flags_from(args: dict[str, Any] | None) -> list[str]:
    """Turn {name: value} into ['--name', 'value', ...].

    Booleans become a bare flag when True and are dropped when False (the common
    argparse store_true convention). Everything else is stringified. Values that
    are dict/list are JSON-encoded (some tools take JSON string args)."""
    out: list[str] = []
    for k, v in (args or {}).items():
        flag = f"--{k}"
        if isinstance(v, bool):
            if v:
                out.append(flag)
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        out.extend([flag, str(v)])
    return out


def run_script(script_rel: str, argv: list[str], *, stdin_text: str | None = None,
               timeout: float = 60.0, env: dict[str, str] | None = None) -> dict[str, Any]:
    """Run scripts/<script_rel> with argv. Returns raw process result.

    `env` overlays extra environment on the inherited env (e.g. AAT_USER_ID for the
    multi-user web platform, so userdata + creds resolve per-user in the subprocess).
    Never raises on a non-zero exit - the caller inspects returncode/stdout."""
    script = PROJECT_ROOT / "scripts" / script_rel
    cmd = [python_exe(), str(script), *argv]
    proc_env = {**os.environ, **env} if env else None
    try:
        proc = subprocess.run(
            cmd, input=stdin_text, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
            cwd=str(PROJECT_ROOT), env=proc_env,
        )
    except subprocess.TimeoutExpired as e:
        return {"returncode": -1, "stdout": "", "stderr": f"timeout after {timeout}s",
                "timed_out": True, "cmd": cmd}
    return {"returncode": proc.returncode, "stdout": proc.stdout or "",
            "stderr": proc.stderr or "", "timed_out": False, "cmd": cmd}


def _parse_json(text: str) -> Any:
    """Parse a tool's stdout as one JSON object. Tolerate leading/trailing noise
    by falling back to the last line that parses."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except ValueError:
        for line in reversed(text.splitlines()):
            line = line.strip()
            if line and line[0] in "{[":
                try:
                    return json.loads(line)
                except ValueError:
                    continue
    return None


def run_tool(tool: str, argv: list[str], *, timeout: float = 60.0,
             env: dict[str, str] | None = None) -> dict[str, Any]:
    """Run a tool via scripts/run-tool.py and normalize the outcome.

    Returns {ok, data, error, returncode, stderr}. `ok` is True only when the
    process exited 0 AND stdout parsed to a non-error JSON object. `env` overlays
    extra environment (e.g. AAT_USER_ID for per-user isolation)."""
    res = run_script("run-tool.py", [tool, *argv], timeout=timeout, env=env)
    return _normalize(res)


def run_agent(agent: str, argv: list[str], *, timeout: float = 120.0,
              env: dict[str, str] | None = None) -> dict[str, Any]:
    res = run_script("run-agent.py", [agent, *argv], timeout=timeout, env=env)
    return _normalize(res)


def _normalize(res: dict[str, Any]) -> dict[str, Any]:
    data = _parse_json(res["stdout"])
    is_err_envelope = isinstance(data, dict) and "error" in data
    ok = res["returncode"] == 0 and data is not None and not is_err_envelope
    err = None
    if not ok:
        if is_err_envelope:
            err = data["error"]
        elif res.get("timed_out"):
            err = {"code": "timeout", "message": res["stderr"]}
        elif data is None:
            err = {"code": "no_json",
                   "message": (res["stderr"] or res["stdout"] or "").strip()[:800]
                   or "tool produced no JSON output"}
        else:
            err = {"code": "nonzero_exit",
                   "message": (res["stderr"] or "").strip()[:800]}
    return {"ok": ok, "data": data, "error": err,
            "returncode": res["returncode"], "stderr": res["stderr"][:2000]}


def check_credential(tool: str, secret: str) -> bool:
    """True if the secret is present in Credential Manager (via set-credential
    --check, which honors namespace:name shared secrets the same way)."""
    res = run_script("set-credential.py", [tool, secret, "--check"], timeout=20)
    return res["returncode"] == 0


def set_credential(tool: str, secret: str, value: str) -> dict[str, Any]:
    """Store a secret by piping it to set-credential.py --stdin. The value is
    never placed on the command line, never logged, never written to disk here."""
    res = run_script("set-credential.py", [tool, secret, "--stdin"],
                     stdin_text=value, timeout=25)
    ok = res["returncode"] == 0
    msg = (res["stdout"] or res["stderr"] or "").strip()
    return {"ok": ok, "message": msg}


def delete_credential(tool: str, secret: str) -> dict[str, Any]:
    res = run_script("set-credential.py", [tool, secret, "--delete"], timeout=20)
    return {"ok": res["returncode"] == 0,
            "message": (res["stdout"] or res["stderr"]).strip()}
