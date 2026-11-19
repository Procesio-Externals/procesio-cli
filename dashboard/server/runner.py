"""Subprocess bridge to the framework's own scripts.

The dashboard reads registry data by importing `registry` directly (fast, in
process). But anything that RUNS a tool/agent or writes a credential goes through
the existing scripts as a subprocess, so each runs in its own venv-correct process
exactly as it does from the terminal - the dashboard never reimplements a tool's
logic or its credential handling.

One caller is different: a run inside a PROCESIO turn (`inherit_env=False`). There the
tool's or agent's entry point is started directly, without the launcher script - see
_run_entry for why.

Every well-behaved tool emits exactly one JSON object on stdout (io.emit / io.fail)
and logs to stderr, so we parse stdout as JSON and keep stderr for diagnostics.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
def _venv_python(platform: str = sys.platform) -> Path:
    """Where the project venv keeps its interpreter: Scripts/python.exe on Windows, bin/python
    everywhere else. The launcher scripts make the same choice in the same way."""
    if platform == "win32":
        return PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    return PROJECT_ROOT / ".venv" / "bin" / "python"


VENV_PY = _venv_python()


def python_exe() -> str:
    """The interpreter to launch with. Prefer the project venv. The launcher scripts also
    re-run themselves under it, but a run inside a turn starts no launcher script, so
    there this choice is the only one made. Without a project venv - the container installs
    its packages for the system interpreter - it is the interpreter that runs this process."""
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _flag_value(value: Any) -> str:
    """One value as one argv element. A dict or a list is JSON (some tools take JSON)."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def flags_from(args: dict[str, Any] | None, repeatable=()) -> list[str]:
    """Turn {name: value} into ['--name', 'value', ...].

    Booleans become a bare flag when True and are dropped when False (the common
    argparse store_true convention). Everything else is stringified. Values that
    are dict/list are JSON-encoded (some tools take JSON string args).

    `repeatable` names the flags the tool accepts several times, one value each (the
    manifest marks them). A list given for one of those becomes one flag per item. For
    any other name a list is still ONE JSON value, because many tools take a JSON list
    in a single flag and the value alone cannot say which of the two is meant."""
    out: list[str] = []
    for k, v in (args or {}).items():
        flag = f"--{k}"
        if isinstance(v, bool):
            if v:
                out.append(flag)
            continue
        if k in repeatable and isinstance(v, list):
            for item in v:
                out.extend([flag, _flag_value(item)])
            continue
        out.extend([flag, _flag_value(v)])
    return out


# What a subprocess may inherit when it must NOT see the parent's environment (a tool run
# inside a PROCESIO turn, see run_script inherit_env). Enough to start Python, find the
# venv, resolve user data, reach the network and write temp files - and nothing that can
# carry a secret. Names are exact; the prefixes cover locale and interpreter settings.
# Extend per deployment with AAT_TOOL_ENV_ALLOW (comma-separated names), never with a
# secret's name.
_SAFE_ENV_NAMES = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "OS",
    "TEMP", "TMP", "TMPDIR", "HOME", "USERPROFILE", "USERNAME", "HOMEDRIVE", "HOMEPATH",
    "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "PROGRAMFILES(X86)",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "TZ", "LANG", "LANGUAGE",
    "VIRTUAL_ENV", "PLAYWRIGHT_BROWSERS_PATH",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "AAT_USERDATA_DIR",
    # Where tools keep the locks they share (tools/procesio/handlers/editlock.py). An isolated
    # call gets a temp folder of its own, so a lock kept there is seen by no other call.
    "AAT_LOCK_DIR",
}
_SAFE_ENV_PREFIXES = ("LC_", "PYTHON", "XDG_")


def _safe_base_env() -> dict[str, str]:
    extra = {n.strip() for n in os.environ.get("AAT_TOOL_ENV_ALLOW", "").split(",") if n.strip()}
    allowed = _SAFE_ENV_NAMES | extra
    return {k: v for k, v in os.environ.items()
            if k in allowed or k.upper() in allowed or k.upper().startswith(_SAFE_ENV_PREFIXES)}


# Process isolation for tools run inside a PROCESIO turn (inherit_env=False) on a POSIX host where
# this process is root - the aat-runtime container. Each such subprocess runs as its OWN
# unprivileged uid, drawn from AAT_TOOL_UID_RANGE ("first-last") and held until the process group
# is gone, with the shared group AAT_TOOL_GID for the user-data folder. A tool then cannot read
# another tool's /proc/<pid>/environ (another user's secrets) nor this server's (its service code
# and bearer token): /proc/<pid>/environ is readable by the same uid only. Unset = no isolation
# (local runs, Windows), exactly as before.
_uid_lock = threading.Lock()
_uids_in_use: set[int] = set()


def _isolation() -> tuple[range, int] | None:
    spec = os.environ.get("AAT_TOOL_UID_RANGE", "").strip()
    if not spec or os.name != "posix" or os.geteuid() != 0:
        return None
    try:
        first, last = (int(p) for p in spec.split("-", 1))
        gid = int(os.environ.get("AAT_TOOL_GID", str(first)))
    except ValueError:
        return None
    return (range(first, last + 1), gid) if 0 < first <= last else None


def _take_uid(uids: range) -> int:
    with _uid_lock:
        for uid in uids:
            if uid not in _uids_in_use:
                _uids_in_use.add(uid)
                return uid
    raise RuntimeError("no free tool uid: raise AAT_TOOL_UID_RANGE")


def _release_uid(uid: int) -> None:
    with _uid_lock:
        _uids_in_use.discard(uid)


def _run_isolated(cmd: list[str], stdin_text: str | None, timeout: float,
                  proc_env: dict[str, str], uids: range, gid: int) -> dict[str, Any]:
    """Run `cmd` as a fresh uid, in its own session, with a private HOME/TMP that is removed after."""
    uid = _take_uid(uids)
    home = tempfile.mkdtemp(prefix=f"aat-tool-{uid}-")
    proc: subprocess.Popen | None = None
    try:
        os.chown(home, uid, gid)
        os.chmod(home, 0o700)
        env = {**proc_env, "HOME": home, "TMPDIR": home, "TEMP": home, "TMP": home,
               "PYTHONDONTWRITEBYTECODE": "1"}
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", cwd=str(PROJECT_ROOT), env=env,
            user=uid, group=gid, extra_groups=[], umask=0o007, start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(stdin_text, timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            # What the tool printed before it was stopped says where it was stuck.
            _, stderr = proc.communicate()
            tail = (stderr or "")[-1500:].strip()
            return {"returncode": -1, "stdout": "",
                    "stderr": f"timeout after {timeout}s" + (f"; last stderr:\n{tail}" if tail else ""),
                    "timed_out": True, "cmd": cmd}
        return {"returncode": proc.returncode, "stdout": stdout, "stderr": stderr,
                "timed_out": False, "cmd": cmd}
    finally:
        # Nothing of this call may outlive it under a uid the next call is handed: the whole
        # session goes, including anything the tool left running in the background.
        if proc is not None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        shutil.rmtree(home, ignore_errors=True)
        _release_uid(uid)


def run_script(script_rel: str, argv: list[str], *, stdin_text: str | None = None,
               timeout: float = 60.0, env: dict[str, str] | None = None,
               inherit_env: bool = True) -> dict[str, Any]:
    """Run scripts/<script_rel> with argv. Returns raw process result.

    `env` overlays extra environment on the inherited env (e.g. AAT_USER_ID for the
    multi-user web platform, so userdata + creds resolve per-user in the subprocess).

    `inherit_env=False` starts the subprocess from a SAFE BASE (_SAFE_ENV_NAMES) instead of
    this process's whole environment, then overlays `env`. The AAT MCP server uses it for
    tools run inside a PROCESIO turn: the container's own secrets (shared AAT_SECRETS_JSON,
    service codes, bearer tokens) must not reach a tool, which gets only what `env` gives it.

    Never raises on a non-zero exit - the caller inspects returncode/stdout."""
    script = PROJECT_ROOT / "scripts" / script_rel
    cmd = [python_exe(), str(script), *argv]
    return _run_command(cmd, stdin_text=stdin_text, timeout=timeout, env=env, inherit_env=inherit_env)


def _run_command(cmd: list[str], *, stdin_text: str | None = None, timeout: float = 60.0,
                 env: dict[str, str] | None = None, inherit_env: bool = True) -> dict[str, Any]:
    """Run one command from the project root and return the raw process result (see run_script
    for `env` and `inherit_env`)."""
    if not inherit_env:
        # AAT_RUNNER=0, and last so nothing can turn it back on: a tool run inside a turn never
        # goes through the shared warm runner. A worker there outlives the call and keeps what it
        # loaded for it, the caller's credentials included.
        proc_env = {**_safe_base_env(), **(env or {}), "AAT_RUNNER": "0"}
        isolation = _isolation()
        if isolation is not None:
            return _run_isolated(cmd, stdin_text, timeout, proc_env, *isolation)
    else:
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
             env: dict[str, str] | None = None, inherit_env: bool = True) -> dict[str, Any]:
    """Run a tool via scripts/run-tool.py and normalize the outcome.

    Returns {ok, data, error, returncode, stderr}. `ok` is True only when the
    process exited 0 AND stdout parsed to a non-error JSON object. `env` overlays
    extra environment (e.g. AAT_USER_ID for per-user isolation); `inherit_env=False`
    starts from a safe base instead of this process's environment (see run_script)."""
    if inherit_env:
        res = run_script("run-tool.py", [tool, *argv], timeout=timeout, env=env)
    else:
        res = _run_entry("tool", tool, argv, timeout=timeout, env=env)
    return _normalize(res)


def run_agent(agent: str, argv: list[str], *, timeout: float = 120.0,
              env: dict[str, str] | None = None, inherit_env: bool = True) -> dict[str, Any]:
    if inherit_env:
        res = run_script("run-agent.py", [agent, *argv], timeout=timeout, env=env)
    else:
        res = _run_entry("agent", agent, argv, timeout=timeout, env=env)
    return _normalize(res)


def _refused(cmd: list[str], returncode: int, message: str) -> dict[str, Any]:
    """The process result of a call that was not started, shaped like one that was."""
    return {"returncode": returncode, "stdout": "", "stderr": message, "timed_out": False, "cmd": cmd}


def _run_entry(kind: str, name: str, argv: list[str], *, timeout: float,
               env: dict[str, str] | None) -> dict[str, Any]:
    """Start a tool's or an agent's entry point itself, for a run inside a PROCESIO turn.

    scripts/run-tool.py and run-agent.py do two things before they start the entry point: try
    the warm runner, which a turn never uses (see _run_command), and look the name up in the
    registry. This process has already read that manifest, so doing both again in a second
    interpreter is start-up time on every call and nothing else. The answers to a name that
    cannot be started are the scripts' own, word for word, so a caller reads the same error.

    The lookup happens HERE, in the server, so what the server hides (AAT_TOOLS_HIDE) is
    refused here too - the tool process never sees that variable and could not refuse it."""
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    import registry

    label = [f"<{kind}>", name, *argv]
    try:
        manifest = registry.get_tool(name) if kind == "tool" else registry.get_agent(name)
    except KeyError as e:
        return _refused(label, 2, f"error: {e}")
    except Exception as e:  # noqa: BLE001 - an unreadable manifest is this call's error, not the server's
        return _refused(label, 1, f"error: {type(e).__name__}: {e}")
    if manifest.path is None:
        return _refused(label, 2, f"error: manifest for {name} has no path")
    entry = manifest.path / manifest.entrypoint
    if not entry.exists():
        return _refused(label, 2, f"error: entrypoint not found: {entry}")
    return _run_command([python_exe(), str(entry), *argv], timeout=timeout, env=env, inherit_env=False)


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
