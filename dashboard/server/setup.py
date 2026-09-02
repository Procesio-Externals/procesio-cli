"""Setup actions the dashboard performs on the user's behalf.

Everything a colleague would otherwise do in a terminal or a chat: store/delete
credentials, seed the user-data folder, edit validated config, capture a web
login, run an OAuth flow. Secrets flow browser -> loopback POST -> the existing
set-credential script (stdin) -> Windows Credential Manager; they are never
logged, echoed, or written to disk here. Config edits and jobs stay under
context-state-knowledge/ via userdata, preserving the wipe-safe boundary.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.orchestrator import bootstraplib
from tools._lib import userdata

from . import config_schemas, inventory, jobs, runner


def _resolve_secret(tool: str, secret: str) -> tuple[str, str]:
    """A `namespace:name` secret (e.g. google:oauth-client) is stored under the
    namespace, matching registry._has_secret. Everything else stays as-is."""
    if ":" in secret:
        ns, _, name = secret.partition(":")
        return ns, name
    return tool, secret


# ---- credentials --------------------------------------------------------
def credential_set(req) -> Any:
    tool = (req.body.get("tool") or "").strip()
    secret = (req.body.get("secret") or "").strip()
    value = req.body.get("value")
    if not tool or not secret:
        return (400, {"error": "tool and secret are required"})
    if not value or not str(value).strip():
        return (400, {"error": "value is empty"})
    rtool, rsecret = _resolve_secret(tool, secret)
    res = runner.set_credential(rtool, rsecret, str(value))
    if res["ok"]:
        inventory.invalidate()
    # res["message"] is set-credential's own output ("stored: ... (N bytes)") -
    # it never contains the secret value.
    return {"ok": res["ok"], "message": res["message"], "tool": tool, "secret": secret}


def credential_delete(req) -> Any:
    tool = (req.body.get("tool") or "").strip()
    secret = (req.body.get("secret") or "").strip()
    if not tool or not secret:
        return (400, {"error": "tool and secret are required"})
    rtool, rsecret = _resolve_secret(tool, secret)
    res = runner.delete_credential(rtool, rsecret)
    if res["ok"]:
        inventory.invalidate()
    return {"ok": res["ok"], "message": res["message"]}


def credential_check(req) -> Any:
    tool = (req.q("tool") or "").strip()
    secret = (req.q("secret") or "").strip()
    if not tool or not secret:
        return (400, {"error": "tool and secret are required"})
    rtool, rsecret = _resolve_secret(tool, secret)
    return {"present": runner.check_credential(rtool, rsecret)}


# ---- bootstrap ----------------------------------------------------------
def bootstrap(req) -> Any:
    # Seeding the user-data folder is the orchestrator's job. Not every
    # distribution of this framework ships that agent, and a missing agent came
    # back as a bare 500 that read like the dashboard was broken.
    import registry
    try:
        registry.get_agent("orchestrator")
    except KeyError:
        return (501, {"error": "bootstrap is not available in this installation",
                      "detail": "the orchestrator agent, which seeds the user-data "
                                "folder, is not installed here. Credentials and "
                                "config can still be set from this page."})
    with_templates = bool(req.body.get("with_templates", True))
    argv = ["bootstrap"] + (["--with-templates"] if with_templates else [])
    res = runner.run_agent("orchestrator", argv, timeout=90)
    if res["ok"]:
        inventory.invalidate()
        return res["data"]
    return (500, {"error": "bootstrap failed", "detail": res["error"]})


# ---- config editor ------------------------------------------------------
def _config_path(component: str, name: str) -> Path:
    # config_dir sanitizes the component; name is constrained to a bare filename.
    safe_name = "".join(c for c in name if c.isalnum() or c in "._-")
    return userdata.config_dir(component) / f"{safe_name}.json"


def config_list(req) -> Any:
    """Every framework config template + whether the user's copy exists."""
    out = []
    for t in bootstraplib.find_templates():
        component = t["component"]
        name = Path(t["target"]).stem
        out.append({
            "component": component,
            "name": name,
            "template": t["template"],
            "exists": t["target_exists"],
            "has_schema": config_schemas.has_schema(component, name),
        })
    return {"configs": out}


def config_get(req) -> Any:
    component = (req.q("component") or "").strip()
    name = (req.q("name") or "").strip()
    if not component or not name:
        return (400, {"error": "component and name are required"})
    path = _config_path(component, name)
    data, err = None, None
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as e:
            err = f"existing file is not valid JSON: {e}"
    # the framework template, for reference / starting point
    tpl = None
    for t in bootstraplib.find_templates():
        if t["component"] == component and Path(t["target"]).stem == name:
            tpl_path = bootstraplib.FRAMEWORK_ROOT / t["template"]
            try:
                tpl = json.loads(tpl_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                tpl = None
            break
    return {"component": component, "name": name, "exists": path.exists(),
            "data": data, "template": tpl, "read_error": err,
            "has_schema": config_schemas.has_schema(component, name)}


def config_validate(req) -> Any:
    component = (req.body.get("component") or "").strip()
    name = (req.body.get("name") or "").strip()
    return config_schemas.validate(component, name, req.body.get("data"))


def config_set(req) -> Any:
    component = (req.body.get("component") or "").strip()
    name = (req.body.get("name") or "").strip()
    data = req.body.get("data")
    if not component or not name:
        return (400, {"error": "component and name are required"})
    verdict = config_schemas.validate(component, name, data)
    if not verdict["ok"]:
        return (400, {"error": "validation failed", "errors": verdict["errors"]})
    path = _config_path(component, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_bytes(text.encode("utf-8"))  # bytes+LF: no Windows CRLF flip
    inventory.invalidate()
    return {"ok": True, "path": str(path), "warnings": verdict["warnings"]}


# ---- web session capture ------------------------------------------------
def session_start(req) -> Any:
    name = (req.body.get("name") or "").strip()
    url = (req.body.get("url") or "").strip()
    if not name or not url:
        return (400, {"error": "name and url are required"})
    argv = ["run-tool.py", "web", "save-session", "--name", name, "--url", url]
    if req.body.get("channel"):
        argv += ["--channel", str(req.body["channel"])]
    if req.body.get("persistent"):
        argv += ["--persistent"]
    job = jobs.create("session", argv, stdin_signal=True)
    return job.snapshot()


def session_commit(req) -> Any:
    """The user has logged in; send the ENTER the save-session is blocking on and
    wait for it to persist and exit."""
    job = jobs.get((req.body.get("job_id") or "").strip())
    if job is None:
        return (404, {"error": "unknown job"})
    if not job.signal():
        return (409, {"error": "job is not awaiting a login signal",
                      "status": job.status})
    job.wait(90)
    inventory.invalidate()
    return job.snapshot()


# ---- OAuth --------------------------------------------------------------
def oauth_start(req) -> Any:
    tool = (req.body.get("tool") or "").strip()
    if not tool:
        return (400, {"error": "tool is required"})
    # google-*/linkedin expose auth-login; it opens a browser and self-completes
    # on the localhost redirect, so no stdin signal is needed.
    job = jobs.create("oauth", ["run-tool.py", tool, "auth-login"], stdin_signal=False)
    return job.snapshot()


def job_get(req) -> Any:
    job = jobs.get((req.q("id") or "").strip())
    if job is None:
        return (404, {"error": "unknown job"})
    if job.status in ("done", "failed"):
        inventory.invalidate()
    return job.snapshot()
