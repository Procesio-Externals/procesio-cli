"""AAT-facing logic for the MCP bridge — pure, testable, no protocol code.

Exposes the live registry to a driver as a small generic surface and executes
capabilities by shelling to scripts/run-tool.py / run-agent.py with a Python LIST
argv (no shell), so structured args (including JSON objects) pass cleanly. This is
the fix for the bash-passthrough tax observed in the B0 spike: the model no longer
fights shell quote-escaping, and gets typed capability schemas instead of `--help`
spelunking.

Execution reuses dashboard.server.runner (the existing, tested subprocess bridge)
so there is ONE definition of "run a framework script and normalize its JSON".
"""
from __future__ import annotations

import contextvars
import difflib
import functools
import json
import os
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)  # sibling modules (turn_credentials) however bridge is imported

import metrics  # noqa: E402  (sibling module: runtime metrics, off unless a listener runs)
import runtime_log  # noqa: E402  (sibling module: the one writer of log lines)
import registry  # noqa: E402
import turn_credentials  # noqa: E402  (sibling module: Web-Api credential lookup per turn)
from tools._lib.manifest import PROCESIO_TEMPLATE_IDS  # noqa: E402
from tools._lib.skill_resources import read_text_resource, resource_index  # noqa: E402
from dashboard.server import runner  # noqa: E402  (shared shell-to-script bridge)
from tools._lib import accounting  # noqa: E402  (per-work-unit accounting seam, P0.0-05)
from tools._lib import httptrace  # noqa: E402  (the trace of a tool's HTTP requests)

# Per-request user id (multi-user web platform). Set by the aat-mcp HTTP server from a
# SERVER-ESTABLISHED header (the authenticated session), NEVER from model output. Read
# here to run the tool/agent subprocess as that user, so userdata + creds isolate
# per-user (userdata.base() -> <root>/<user>, file creds -> per-user namespace). Unset =
# single-user, exactly as before (local Claude Code unaffected).
_user_ctx: "contextvars.ContextVar" = contextvars.ContextVar("aat_user_id", default=None)


def set_user(uid: str | None):
    """Set the current request's user; returns a token for reset_user()."""
    return _user_ctx.set(uid or None)


def reset_user(token) -> None:
    _user_ctx.reset(token)


# Per-request WORKSPACE id (multi-tenant PROCESIO module, spec P0.0-01). Set alongside
# the user from the SERVER-ESTABLISHED session, never from model output. Threads
# AAT_WORKSPACE_ID into the tool/agent subprocess env so userdata + creds isolate per
# (workspace, user). Unset = single-workspace, exactly as before.
_workspace_ctx: "contextvars.ContextVar" = contextvars.ContextVar(
    "aat_workspace_id", default=None)


def set_workspace(ws: str | None):
    """Set the current request's workspace; returns a token for reset_workspace()."""
    return _workspace_ctx.set(ws or None)


def reset_workspace(token) -> None:
    _workspace_ctx.reset(token)


# Managed turn: this request belongs to a turn some OUTER runner already drives (the .NET planner's
# step loop, a scheduled job, ...). Set from a SERVER-ESTABLISHED header, never from model output.
#
# Why a mechanism and not a prompt line: the framework's own `orchestrator drive` is a second, full
# orchestration loop — it asks a SEPARATE configured llm provider for the next action and executes it,
# with its own run ledger, step cap and token budget. Started from inside a managed step you get two
# planners fighting, two run records, and a second model's spend. The step prompt says not to; the MCP
# tool description for run_agent says to route everything through the orchestrator; the model sees
# both. This settles it in code for the one action that actually starts a competing loop.
_managed_ctx: "contextvars.ContextVar" = contextvars.ContextVar("aat_managed_turn", default=False)

# "agent:action" pairs refused during a managed turn. Deliberately narrow: `drive` starts the
# competing loop, while `intake` / `route` / `record` are read-or-bookkeeping and stay allowed, so a
# managed turn keeps the doctrine available without being able to fork the control flow.
_DEFAULT_MANAGED_TURN_BLOCK = "orchestrator:drive"


def set_managed_turn(flag):
    """Mark this request as part of an externally-driven turn; returns a reset token."""
    return _managed_ctx.set(bool(flag))


def reset_managed_turn(token) -> None:
    _managed_ctx.reset(token)


def _managed_turn_block() -> set[tuple[str, str]]:
    raw = os.environ.get("AAT_MCP_MANAGED_TURN_BLOCK", _DEFAULT_MANAGED_TURN_BLOCK)
    out: set[tuple[str, str]] = set()
    for item in raw.split(","):
        name, _, action = item.strip().partition(":")
        if name and action:
            out.add((name.lower(), action.lower()))
    return out


def _managed_turn_refusal(agent: str, action: str | None) -> dict | None:
    """The refusal payload when a managed turn reaches for a competing driver, else None."""
    if not _managed_ctx.get():
        return None
    if (agent.lower(), (action or "").lower()) not in _managed_turn_block():
        return None
    metrics.refusal("managed_turn")
    log_refusal("managed_turn", agent, action,
                "the action starts a second orchestration loop inside a managed turn")
    return {"ok": False, "refused": {
        "agent": agent, "action": action, "reason": "managed_turn",
        "message": (f"'{agent} {action}' starts a second orchestration loop, and this turn is already "
                    f"one step of an externally-managed plan. Do the concrete increment yourself with "
                    f"run_tool / run_agent, then end your reply with the control line you were given."),
    }}


# Per-request TURN TOKEN (PROCESIO platform turns). Set by the HTTP server from the
# X-AAT-Turn-Token header the worker writes into that turn's opencode config - never from
# model output. Its only use here is asking Web-Api for credentials; it is never handed to
# a tool subprocess.
_turn_token_ctx: "contextvars.ContextVar" = contextvars.ContextVar("aat_turn_token", default=None)


def set_turn_token(token: str | None):
    """Set the current request's turn token; returns a token for reset_turn_token()."""
    return _turn_token_ctx.set(token or None)


def reset_turn_token(token) -> None:
    _turn_token_ctx.reset(token)


# Per-request MESSAGE ID of the turn. Set by the HTTP server from the X-AAT-Message-Id header the
# worker writes into that turn's opencode config - never from model output. It names the turn on
# this server's log lines and does nothing else: no decision, cache key or metric label reads it.
MESSAGE_ID_HEADER = "X-AAT-Message-Id"
_MESSAGE_ID = re.compile(r"[0-9A-Za-z-]{1,64}")
_NO_VALUE = "-"  # how a log line writes a value that is absent
_message_id_ctx: "contextvars.ContextVar" = contextvars.ContextVar("aat_message_id", default=None)


def first_message_id(*candidates) -> str | None:
    """The first of `candidates` that is a usable message id, or None.

    A request can name its turn in two places: the header the worker wrote, and the turn token.
    The caller passes both, in the order it prefers them. Each is checked on its own, so a header
    that is present and unusable does not hide the id the token holds."""
    for value in candidates:
        if isinstance(value, str) and _MESSAGE_ID.fullmatch(value) is not None:
            return value
    return None


def set_message_id(value: str | None):
    """Set the current request's message id; returns a token for reset_message_id().

    Only a short id of letters, digits and hyphens is kept. Anything else counts as absent, so
    what a header carries can never write a second field, or a second line, into the log."""
    return _message_id_ctx.set(first_message_id(value))


def reset_message_id(token) -> None:
    _message_id_ctx.reset(token)


def message_id() -> str:
    """The current request's message id as a log line writes it: the id, or `-` without one."""
    return _message_id_ctx.get() or _NO_VALUE


# --- the troubleshooting log ----------------------------------------------------------------------
#
# One line on stderr per finished call and per refusal, each naming the turn by its message id, so
# one search by that id shows what this server did for the turn. stderr, because in stdio mode
# stdout carries the JSON-RPC stream. A line holds ids, names, codes, counts and durations - never
# an argument, a result or a credential - and writing it never fails or changes the call.

_LOG_NAME_MAX = 80
_LOG_MESSAGE_MAX = 300
_LOG_MESSAGE_SCAN = 4000   # how much of an error message is looked at before it is cut
_BARE_VALUE = re.compile(r"[A-Za-z0-9_.:/@+-]+")
# What an error message may quote and a log line must not: a URL's query string, and the value
# of an Authorization header.
_QUERY_STRING = re.compile(r"(?<=\S)\?[^\s\"'<>]+")
_AUTH_VALUE = re.compile(r"\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
# Errors whose message quotes an argument of the call. The code says what happened; the text
# stays out of the log.
_ARGUMENT_ECHO_CODES = frozenset({"workspace_out_of_turn"})
# The runner's verdicts on a process that gave no error of its own. The runner builds their
# message from whatever the process wrote to stdout and stderr, and that output can hold what the
# tool read or was given: a record, a personal number, the URL of a webhook. The line says what
# happened in a sentence of its own instead; the exit code is beside it.
_RUNNER_VERDICTS = {
    "no_json": "the tool ended without a JSON answer",
    "nonzero_exit": "the tool ended with an error exit code and no error of its own",
    "timeout": "the tool did not end in time and was stopped",
}


def _one_line(text: str) -> str:
    """`text` on one line: every control or other unprintable character becomes a space, and
    runs of spaces become one."""
    return " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())


def _inside_quotes(text: str) -> str:
    """`text` as it can stand between two double quotes on a log line, with no escaping.

    A double quote would end the value early. A backslash would be read as the start of an
    escape: as the last character it turns the closing quote into part of the value, and what
    follows on the line - real fields, or text made to look like fields - is read as this one.
    The line uses no escapes at all, so both are replaced rather than escaped: `'` and `/`."""
    return text.replace('"', "'").replace("\\", "/")


def _is_the_tool_s_own_error(result: dict, error) -> bool:
    """True when `error` is the error object the tool itself wrote in its JSON answer.

    The runner hands that object on as it is, next to the answer it came from. Every other
    error of a result was built by the runner or by this server."""
    data = result.get("data")
    return isinstance(data, dict) and "error" in data and data["error"] == error


def _log_name(value) -> str:
    """A tool name, an action name or an error code as a log line writes it.

    All three can come from the model or from a tool's output, so they are free text: cut,
    put on one line, and quoted unless they are a plain word - a name with a space or an
    equals sign in it must not read as more fields. The raw name is kept rather than its
    registry name: a log line has no cardinality limit, and what was actually sent is what
    explains a failed call."""
    if value is None or value == "":
        return _NO_VALUE
    if not isinstance(value, str):
        return f'"<{type(value).__name__}>"'  # a name that is not text: its type says enough
    text = _one_line(value[:_LOG_NAME_MAX])
    if not text:
        return _NO_VALUE
    return text if _BARE_VALUE.fullmatch(text) else '"' + _inside_quotes(text) + '"'


def _log_text(value) -> str:
    """The start of an error message as a log line writes it inside quotes, or '' for none."""
    if not isinstance(value, str):
        return ""
    text = _QUERY_STRING.sub("", value[:_LOG_MESSAGE_SCAN])
    text = _AUTH_VALUE.sub(r"\1 [removed]", text)
    return _inside_quotes(_one_line(text)[:_LOG_MESSAGE_MAX])


def _field(value, limit: int = _LOG_NAME_MAX):
    """A name or a code as a JSON log line holds it: the same cut and the same single line as
    in the text line, without the quoting - JSON does its own. None for a value that is absent."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return f"<{type(value).__name__}>"
    return _one_line(value[:limit]) or None


def _log(line: str, fields: dict | None = None, level: str = runtime_log.INFO) -> None:
    """Write one log line about a call of a turn. `line` is the whole text line; `fields` are
    its values for the JSON format, where the message id is added to them."""
    runtime_log.write("aat-mcp", line, level=level, category=runtime_log.TURN,
                      fields={"MessageId": _message_id_ctx.get(), **(fields or {})})


def log_refusal(code: str, name, action, reason: str) -> None:
    """Write the line of one call that was answered without starting, or instead of, a tool or an
    agent. `reason` is a fixed sentence of the calling site, never built from the call's
    arguments. Never raises."""
    try:
        _log(f"refused msg={message_id()} tool={_log_name(name)} action={_log_name(action)} "
             f'code={_log_name(code)} reason="{reason}"',
             {"Event": "refused", "Tool": _field(name), "Action": _field(action), "Code": _field(code),
              "Reason": reason}, runtime_log.WARNING)
    except Exception:  # noqa: BLE001
        pass


def _log_call(kind: str, name, action, result, raised: str | None, seconds: float,
              http: "metrics.HttpSummary | None") -> None:
    """Write the line of one finished run_tool / run_agent call. Never raises.

    `raised` is the type name of the exception the call ended with, or None. Only the type is
    logged for an exception, because its text can quote the call's arguments. `http` is the
    summary of the call's HTTP trace, or None when the call had no trace."""
    try:
        ok = raised is None and isinstance(result, dict) and bool(result.get("ok", False))
        code = message = None
        if raised is not None:
            code, message = "exception", raised
        elif not ok and isinstance(result, dict):
            error, refused = result.get("error"), result.get("refused")
            if isinstance(error, dict):
                code, message = error.get("code"), error.get("message")
                if (isinstance(code, str) and code in _RUNNER_VERDICTS
                        and not _is_the_tool_s_own_error(result, error)):
                    message = _RUNNER_VERDICTS[code]
            elif isinstance(error, str):
                message = error
            elif isinstance(refused, dict):  # the bridge's own refusal carries a reason, not an error
                code = refused.get("reason")
        parts = [f"call msg={message_id()}", f"kind={kind}", f"tool={_log_name(name)}",
                 f"action={_log_name(action)}", f"outcome={'ok' if ok else 'error'}",
                 f"code={_log_name(code)}", f"seconds={seconds:.3f}"]
        fields = {"Event": "call", "Kind": kind, "Tool": _field(name), "Action": _field(action),
                  "Outcome": "ok" if ok else "error", "Code": _field(code), "Seconds": round(seconds, 3)}
        exit_code = result.get("returncode") if isinstance(result, dict) else None
        if isinstance(exit_code, int) and not isinstance(exit_code, bool):
            parts.append(f"exit={exit_code}")
            fields["ExitCode"] = exit_code
        if http is not None:
            parts.append(f"http={http.requests}")
            fields["HttpRequests"] = http.requests
            if http.slowest is not None:
                method, route, took, status = http.slowest
                parts.append(f'slowest="{method} {route} {took:.1f}s {status}"')
                fields.update(SlowestRequest=f"{method} {route}", SlowestRequestSeconds=round(took, 1),
                              SlowestRequestStatus=status)
            parts.append(f"unfinished={http.unfinished}")
            fields["UnfinishedRequests"] = http.unfinished
        if not ok and not (isinstance(code, str) and code in _ARGUMENT_ECHO_CODES):
            text = _log_text(message)
            if text:
                parts.append(f'message="{text}"')
                fields["Message"] = text
        _log(" ".join(parts), fields, runtime_log.INFO if ok else runtime_log.WARNING)
    except Exception:  # noqa: BLE001
        pass


def _user_env() -> dict | None:
    env: dict = {}
    uid = _user_ctx.get()
    if uid:
        env["AAT_USER_ID"] = str(uid)
    ws = _workspace_ctx.get()
    if ws:
        env["AAT_WORKSPACE_ID"] = str(ws)
    return env or None


def _secret_manifests(kind: str, name: str) -> list:
    """The manifests of the tools whose secrets this run can need: the tool itself, or every
    tool an agent drives - each only if it declares a secret. Unknown names yield nothing;
    the run then fails on its own terms, not here."""
    try:
        names = [name] if kind == "tool" else list(getattr(registry.get_agent(name), "tools", []) or [])
    except Exception:  # noqa: BLE001
        return []
    out = []
    for tool in names:
        try:
            manifest = registry.get_tool(tool)
        except Exception:  # noqa: BLE001
            continue
        if getattr(manifest, "secrets", None):
            out.append(manifest)
    return out


def _secrets_from_credential(manifest, values: dict[str, str],
                             secrets: dict[str, dict[str, str]]) -> str | None:
    """Fill `secrets` with what the manifest maps from one credential's fields ({be_id: value}).

    Returns a sentence for the model when the credential lacks a mapped field; None when every
    mapped secret was found."""
    missing = []
    for secret, be_id in manifest.procesio_credential.map.items():
        value = values.get(be_id)
        if not value:
            missing.append(be_id)
            continue
        # A shared `namespace:name` secret is read by creds.get(namespace, name).
        namespace, _, secret_name = secret.rpartition(":")
        secrets.setdefault(namespace or manifest.name, {})[secret_name] = value
    if missing:
        return (f"The PROCESIO credential chosen for {manifest.credential_label()} has no "
                f"{', '.join(missing)} value. Do not retry with it: the user has to fill it in, or "
                f"choose another credential.")
    return None


# The profile name the procesio tool sees on the platform. One per turn, built from the user's AI
# assistant API key; the tool resolves it as its default, exactly as it would a locally stored one.
_PROCESIO_PROFILE = "platform"


def _procesio_profile(manifest, key: "turn_credentials.ProcesioKey",
                      secrets: dict[str, dict[str, str]]) -> None:
    """The procesio tool does not read flat secrets: it reads a profile index, a default profile
    name and one JSON profile (tools/procesio/profiles.py). Build that from the user's API key,
    plus what only the platform knows: this turn's workspace and the Web-Api URL.

    An API-key profile never writes back (only user/password profiles cache a token), so the
    read-only per-turn secrets are enough - nothing of it reaches the disk."""
    profile = {"type": "apikey", "key": key.key, "value": key.value}
    workspace = key.workspace_id or _workspace_ctx.get()
    if workspace:
        profile["workspace_id"] = str(workspace)
    # The same Web-Api this server fetches credentials from; AAT_PROCESIO_WEB_BASE overrides it
    # when the tool must go through another address (a public gateway, say).
    web_base = os.environ.get("AAT_PROCESIO_WEB_BASE") or os.environ.get("AAT_WEBAPI_URL")
    if web_base:
        profile["web_base"] = web_base.rstrip("/")
    secrets[manifest.name] = {
        "credentials": json.dumps([{"name": _PROCESIO_PROFILE, "type": "apikey"}]),
        "default-profile": _PROCESIO_PROFILE,
        f"cred-{_PROCESIO_PROFILE}": json.dumps(profile),
    }


def _candidates(manifest, key: "turn_credentials.ProcesioKey",
                turn_token: str) -> "turn_credentials.ToolCredentials":
    """The user's credentials that could serve this tool: of its template, on one of its hosts."""
    spec = manifest.procesio_credential
    template_id = spec.template_id()
    if not spec.hosts:
        return turn_credentials.fetch_tool_credentials(key, template_id, None, turn_token)
    merged: dict[str, dict] = {}
    for host in spec.hosts:
        found = turn_credentials.fetch_tool_credentials(key, template_id, host, turn_token)
        if found.message:
            return found
        for item in found.items:
            merged.setdefault(item["id"], item)
    return turn_credentials.ToolCredentials(items=list(merged.values()))


def _choose(manifest, found: "turn_credentials.ToolCredentials",
            requested: str | None) -> tuple[dict | None, str | None]:
    """Pick the credential a tool runs with, or say why none was picked.

    One candidate is used as is - unless it is a REST API credential and the tool names no host:
    a REST API credential says nothing about which service it is for, so then even a single one
    could belong to anything else and is never sent unasked. Several: the model has to name one
    (`credential` on run_tool), after asking the user or trying them in turn."""
    if found.message:
        return None, found.message
    spec = manifest.procesio_credential
    label = manifest.credential_label()
    items = found.items
    names = ", ".join(f"'{c['name']}'" for c in items)
    if requested:
        wanted = requested.strip().lower()
        named = [c for c in items if c["name"].strip().lower() == wanted or c["id"].lower() == wanted]
        if len(named) == 1:
            return named[0], None
        return None, (f"No single PROCESIO credential named '{requested}' fits {label}. "
                      + (f"The ones that fit: {names}." if items else "None fits.")
                      + " Call this tool again with one of those names as credential.")
    if not items:
        kind = "REST API" if spec.template_id() == _REST_API_TEMPLATE_ID else spec.template
        where = f" whose URL is on {' or '.join(spec.hosts)}" if spec.hosts else ""
        return None, (f"The user has no PROCESIO {kind} credential{where} for {label}. Do not retry: "
                      f"the user has to create one in PROCESIO (Credentials) first.")
    if len(items) == 1 and (spec.hosts or spec.template_id() != _REST_API_TEMPLATE_ID):
        return items[0], None
    return None, (f"Several PROCESIO credentials could be used for {label}: {names}. Ask the user which "
                  f"one to use (or try them in turn), then call this tool again with credential='<name>'.")


_REST_API_TEMPLATE_ID = PROCESIO_TEMPLATE_IDS["REST_API"]


def _no_key_refusal(message: str) -> dict:
    """The answer to a call that needs PROCESIO credentials when the turn has no usable key. The
    tool is not started: without the key it can only fail, and a failing tool invites the model to
    try another one, each attempt costing a run of the turn."""
    return {"ok": False, "error": {
        "code": "procesio_key_unavailable",
        "message": (f"{message} No tool that uses PROCESIO credentials can run in this turn. Stop calling "
                    f"tools now: end your reply by telling the user what to fix.")}}


def _run_timeout() -> float:
    """How long one tool or agent call may run before it is stopped (AAT_TOOL_TIMEOUT_SECONDS,
    default 180). A process save validates and writes a whole flow, which outlives a minute."""
    try:
        return max(1.0, float(os.environ.get("AAT_TOOL_TIMEOUT_SECONDS", "180")))
    except ValueError:
        return 180.0


_PERSONAL_WORKSPACE = "00000000-0000-0000-0000-000000000000"


def _workspace_refusal(kind: str, name: str, args: dict | None,
                       action: str | None = None) -> dict | None:
    """A turn's API key belongs to the turn's workspace only, so a tool on that key that is told
    to act in ANOTHER workspace (--workspace-id) can only be refused by PROCESIO (403) - after a
    full tool start. Answer that here, at once, and say which workspace the turn is in. The
    turn's own workspace (or none given) passes. The personal workspace is Guid.Empty, which the
    request context holds as None."""
    if not isinstance(args, dict):
        return None
    asked = next((args[k] for k in ("workspace-id", "workspace_id", "workspaceId") if args.get(k)), None)
    if not asked:
        return None
    turn_ws = (_workspace_ctx.get() or _PERSONAL_WORKSPACE).lower()
    if str(asked).strip().lower() == turn_ws:
        return None
    if not any(m.procesio_credential is not None and m.procesio_credential.is_api_key()
               for m in _secret_manifests(kind, name)):
        return None
    where = "the user's personal workspace" if turn_ws == _PERSONAL_WORKSPACE else f"workspace {turn_ws}"
    metrics.refusal("workspace_out_of_turn")
    log_refusal("workspace_out_of_turn", name, action,
                "the call names a workspace other than the one of the turn")
    return {"ok": False, "error": {
        "code": "workspace_out_of_turn",
        "message": (f"This turn runs in {where}, and its PROCESIO API key is valid only there. Do not pass "
                    f"--workspace-id {asked}: call the tool without --workspace-id. Resources in other "
                    f"workspaces cannot be reached from this turn.")}}


# What a tool reports when PROCESIO rejected the key it was given (tools/procesio/errors.py).
_AUTH_FAILURE_CODES = {"auth_required", "permission_denied", "unauthorized", "forbidden"}


def _after_auth_failure(kind: str, name: str, turn_token: str, res: dict,
                        action: str | None = None) -> dict:
    """A tool that runs on the turn's API key gets the key itself, so only its result says the key
    was revoked mid-turn. On a 401/403 from such a tool, ask Web-Api once whether the key stands:
    if not, this answer and every later call of the turn say so and the model is told to stop."""
    err = res.get("error") if isinstance(res, dict) else None
    if res.get("ok", False) or not isinstance(err, dict) or err.get("code") not in _AUTH_FAILURE_CODES:
        return res
    if not any(m.procesio_credential is not None and m.procesio_credential.is_api_key()
               for m in _secret_manifests(kind, name)):
        return res
    # Calls started in parallel with the old key all come back refused: once one of them found the
    # key revoked, the rest read that from the turn's memory instead of asking Web-Api again.
    known = turn_credentials.fetch_key(turn_token)
    key = known if not known.key else turn_credentials.recheck_key(turn_token)
    if key.key:
        return res  # the key stands: a plain missing permission, the tool's own answer is right
    log_refusal("procesio_key_unavailable", name, action,
                "the PROCESIO API key of the turn stopped being valid after the tool ran")
    return _no_key_refusal(key.message or "The AI assistant's PROCESIO API key was revoked.")


def _turn_env(kind: str, name: str, turn_token: str, credential: str | None = None,
              action: str | None = None) -> dict | None:
    """Environment for a subprocess run inside a PROCESIO turn.

    The subprocess does NOT inherit the container's environment (runner is called with
    inherit_env=False): it gets a safe base plus exactly this. Credentials are read for THIS
    turn's user, for THESE tools only, and reach the tool through the env backend - so no shared
    secret, no other tool's secret, and not the turn token itself ever reach a tool. Isolation
    between turns is free: the process dies with its env.

    The turn token buys one thing: the user's AI assistant API key. Everything else is read with
    that key, so a tool gets exactly the credentials its user can see. turn_credentials keeps both
    in memory for the rest of the turn (see its module docstring), so a turn's many tool calls ask
    Web-Api once; nothing reaches the disk.

    Returns None when the turn has no usable PROCESIO key but this tool needs one: the caller
    answers with _no_key_refusal instead of starting it."""
    secrets: dict[str, dict[str, str]] = {}
    hints: list[str] = []
    key = None  # fetched once, and only when a tool needs PROCESIO credentials
    for manifest in _secret_manifests(kind, name):
        spec = manifest.procesio_credential
        if spec is None:
            hints.append(f"'{manifest.name}' cannot use PROCESIO credentials yet (its manifest declares no "
                         f"procesio_credential). Do not retry this tool.")
            continue
        if key is None:
            key = turn_credentials.fetch_key(turn_token)
        if not key.key:
            metrics.refusal("procesio_key_unavailable")  # the caller answers without starting the tool
            log_refusal("procesio_key_unavailable", name, action,
                        "the turn has no usable PROCESIO API key")
            return None
        if spec.is_api_key():
            _procesio_profile(manifest, key, secrets)
            continue
        chosen, problem = _choose(manifest, _candidates(manifest, key, turn_token), credential)
        if chosen is not None:
            problem = _secrets_from_credential(manifest, chosen["values"], secrets)
        if problem:
            hints.append(problem)

    env = dict(_user_env() or {})
    env["AAT_CREDS_BACKEND"] = "env"
    env["AAT_SECRETS_JSON"] = json.dumps(secrets)
    if hints:
        # creds.get() appends this to its "missing credential" error, so the model reads
        # WHY and what fixes it instead of rediscovering the tool (see creds.MISSING_HINT_ENV).
        env["AAT_CREDS_MISSING_HINT"] = " ".join(dict.fromkeys(hints))
    return env

# Tools that cannot run in a container (browser/profile, DB driver, media system libs).
# When AAT_HOST_RUNNER_URL is set, these (and agents that drive them) are executed on
# the HOST via the host-runner instead of in-container. Extend via AAT_HOST_ONLY_TOOLS.
_HOST_ONLY_TOOLS = {
    "sqlserver", "web",
    }


def _host_only_set() -> set[str]:
    extra = {t.strip() for t in os.environ.get("AAT_HOST_ONLY_TOOLS", "").split(",") if t.strip()}
    return _HOST_ONLY_TOOLS | extra


def _is_host_only(kind: str, name: str) -> bool:
    """A tool is host-only if listed or its manifest declares a web_session. An agent
    is host-only if any tool it drives is host-only."""
    hoset = _host_only_set()
    if kind == "tool":
        if name in hoset:
            return True
        try:
            return getattr(registry.get_tool(name), "web_session", None) is not None
        except Exception:  # noqa: BLE001
            return False
    try:
        drives = set(getattr(registry.get_agent(name), "tools", []) or [])
    except Exception:  # noqa: BLE001
        return False
    if drives & hoset:
        return True
    for t in drives:
        try:
            if getattr(registry.get_tool(t), "web_session", None) is not None:
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def _delegate(kind: str, name: str, action: str | None, args: dict | None) -> dict:
    """Run a host-only tool/agent on the host via the host-runner."""
    url = os.environ["AAT_HOST_RUNNER_URL"].rstrip("/") + "/run"
    token = os.environ.get("AAT_HOST_RUNNER_TOKEN", "")
    payload = json.dumps({"kind": kind, "name": name, "action": action,
                          "args": args or {}}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    uid = _user_ctx.get()
    if uid:
        headers["X-AAT-User"] = str(uid)  # host-only tools run as this user too
    ws = _workspace_ctx.get()
    if ws:
        headers["X-AAT-Workspace"] = str(ws)  # ...and in this workspace
    req = urllib.request.Request(url, data=payload, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=330) as resp:  # noqa: S310 (host-local)
            return json.loads(resp.read().decode("utf-8") or "null")
    except urllib.error.URLError as e:
        return {"ok": False, "error": {"code": "host_runner_unreachable",
                                       "message": f"host-only {kind} {name!r}: {e}"}}


def _compact(entry: dict, kind: str, full: bool = False) -> dict:
    """One capability line for the discovery listing. Default is trimmed to keep the
    session context small (a 113-entry listing at 240-char descriptions + examples is
    ~50KB that sits in context all session and pushes weaker-window models toward the
    context wall); pass full=True for the fuller line. Either way the complete
    action/arg schema is one `capabilities(name=...)` call away."""
    routing = entry.get("routing") or {}
    desc = entry.get("description") or ""
    out = {
        "kind": kind,
        "name": entry["name"],
        "description": desc[:240] if full else desc[:100],
        "primary_action": routing.get("primary_action", ""),
        "ready": bool(entry.get("ready", True)),
    }
    if full:
        out["example"] = routing.get("example", "")
    return out


def _args_schema(arglist) -> list[dict]:
    """One action's (or a flat tool's) argument list, normalized.

    `name` is the LITERAL flag spelling from the manifest - hyphenated, not
    snake_case. Returning it verbatim is what stops the caller guessing
    `workspace_id` when the flag is `--workspace-id`."""
    out = []
    for arg in (arglist or []):
        spec = {
            "name": arg["name"],
            "type": arg.get("type", "string"),
            "required": bool(arg.get("required", False)),
            "description": arg.get("description", ""),
        }
        # An arg that carries a structured payload publishes its schema. Without it the
        # caller knows the flag and not the contract, and reverse-engineers the shape
        # from validation errors - one layer per attempt, several turns per action.
        if arg.get("schema"):
            spec["schema"] = arg["schema"]
        out.append(spec)
    return out


def _full(entry: dict, kind: str) -> dict:
    """Full action + arg schema for one capability — the structured replacement for
    `--help`, so the driver never has to spelunk help text."""
    return {
        "kind": kind,
        "name": entry["name"],
        "description": entry.get("description", ""),
        "ready": bool(entry.get("ready", True)),
        "missing_secrets": entry.get("missing_secrets", []),
        "tools": entry.get("tools", []) if kind == "agent" else None,
        # Flat tools (e.g. hello-world) keep args at the top level, not under actions.
        "args": _args_schema(entry.get("args")) if not entry.get("actions") else [],
        "actions": [
            {
                "name": a["name"],
                "description": a.get("description", ""),
                "args": _args_schema(a.get("args")),
            }
            for a in entry.get("actions", [])
        ],
    }


_REG_CACHE: dict = {}
_REG_LOCK = threading.Lock()


def _registry_stamp() -> tuple:
    """What a registry scan is made from: every manifest's path, modification time and size,
    and the names hidden from this session. Equal stamps mean a new scan would read the same
    files. A few hundred `stat` calls, against parsing and re-reporting every manifest."""
    files = []
    for root, pattern in ((registry.TOOLS_DIR, "*/tool.yaml"), (registry.AGENTS_DIR, "*/agent.yaml"),
                          (registry.SKILLS_DIR, "*/SKILL.md")):
        for path in sorted(root.glob(pattern)):
            try:
                stat = path.stat()
            except OSError:
                continue
            files.append((str(path), stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(registry.hidden_tools())), tuple(files)


def _readiness_is_fixed() -> bool:
    """True when which secrets are present cannot change while this process runs.

    A scan also reports readiness (`missing_secrets`), and that part is not in the files: on a
    workstation someone stores a credential and the next listing has to show the tool ready. The
    env backend is the exception - it reads AAT_SECRETS_JSON once, when it is first used - and it
    is the one a container runs on."""
    return (os.environ.get("AAT_CREDS_BACKEND") or "").strip().lower() in ("env", "envjson", "env-json")


def _scan_registry():
    """The registry as (tools, agents, skills), scanned at most once per AAT_REGISTRY_TTL
    seconds (default 30; 0 = scan on every call).

    When that time is up the scan is repeated only if it could come out different: a manifest
    changed, or credentials can appear while the process runs (see _readiness_is_fixed). In a
    container neither happens, so the registry is scanned once and after that the cost of a call
    is the stamp. Callers that arrive while a scan runs wait for it instead of each starting
    their own: a scan is CPU work, and several at once only make every one of them slower."""
    ttl = float(os.environ.get("AAT_REGISTRY_TTL", "30") or 0)
    if ttl <= 0:
        return _scan_registry_now()
    hit = _REG_CACHE.get("data")
    if hit is not None and hit[1] > time.monotonic():
        return hit[0]
    with _REG_LOCK:
        hit = _REG_CACHE.get("data")
        if hit is not None and hit[1] > time.monotonic():
            return hit[0]  # another caller scanned while this one waited
        stamp = _registry_stamp()
        if hit is not None and len(hit) > 2 and hit[2] == stamp and _readiness_is_fixed():
            scanned = hit[0]
        else:
            scanned = _scan_registry_now()
        _REG_CACHE["data"] = (scanned, time.monotonic() + ttl, stamp)
        return scanned


def _scan_registry_now():
    tools = registry.list_tools()
    agents = registry.list_agents({t["name"]: t for t in tools})
    skills = registry.list_skills()
    if metrics.enabled():
        _index_metric_names(tools, agents)
    return tools, agents, skills


def warm_registry() -> threading.Thread:
    """Scan the registry in the background, so the first caller of a server that has just
    started waits for a scan already under way instead of starting it. Never raises: a scan
    that fails here is simply made again by the first call that needs it."""
    def scan() -> None:
        try:
            _scan_registry()
        except Exception as e:  # noqa: BLE001
            runtime_log.write("aat-mcp", f"registry warm-up failed ({type(e).__name__}); "
                              "the first call scans again", level=runtime_log.WARNING,
                              fields={"ExceptionType": type(e).__name__})

    thread = threading.Thread(target=scan, name="aat-registry-warm-up", daemon=True)
    thread.start()
    return thread


# --- targeted discovery ---------------------------------------------------
#
# Two halves of the same context problem, solved from different ends. `_compact`
# trims the NO-NAME listing, which sits in context all session. Everything below
# handles the WITH-NAME lookup: a big tool's full schema is unusable as a payload
# (procesio alone is ~369 KB / 379 actions), because the driver truncates it to a
# single-line file that neither `read` (offset/limit sees one line), `grep`
# (ripgrep refuses a >64 KB record) nor `bash` (gated) can open - so the model
# burns a turn and gets nothing. The three doors give it what it needs instead:
# ONE action's schema (~1-2 KB), a keyword SEARCH over actions, and - when it asks
# for the whole thing anyway - an automatic degrade to the action-name index.
# The degrade is the point: an instruction in the prompt can be (and was)
# ignored, code cannot.

_DEFAULT_MAX_BYTES = 40_000


def _max_bytes() -> int:
    """Size above which a full capability schema degrades to its action index."""
    try:
        return max(0, int(os.environ.get("AAT_CAPABILITIES_MAX_BYTES",
                                         _DEFAULT_MAX_BYTES)))
    except ValueError:
        return _DEFAULT_MAX_BYTES


def _find(name: str, kind: str | None = None) -> tuple[dict | None, str | None]:
    """Resolve one capability by name -> (entry, 'tool'|'agent'). Tools win ties,
    matching the historical lookup order."""
    tools, agents, _ = _scan_registry()
    if kind in (None, "tool"):
        for e in tools:
            if e.get("name") == name:
                return e, "tool"
    if kind in (None, "agent"):
        for e in agents:
            if e.get("name") == name:
                return e, "agent"
    return None, None


def _action_names(entry: dict) -> list[str]:
    return [a["name"] for a in (entry.get("actions") or [])]


def _norm_tokens(name: str) -> set[str]:
    """Action name -> comparable word set, singularized. `credential-list` and
    `list-credentials` must come out equal: word ORDER and PLURALS are what a
    model gets wrong, and plain edit distance scores both as far apart."""
    return {t[:-1] if t.endswith("s") and len(t) > 3 else t
            for t in name.lower().split("-") if t}


def _suggest(action: str, names: list[str], n: int = 8) -> list[str]:
    """Closest real action names for one the caller invented."""
    want = _norm_tokens(action)
    scored: list[tuple[float, str]] = []
    for candidate in names:
        have = _norm_tokens(candidate)
        overlap = len(want & have)
        ratio = difflib.SequenceMatcher(None, action.lower(), candidate.lower()).ratio()
        if not overlap and ratio < 0.5:
            continue
        score = ratio + 2.0 * overlap
        if have == want:  # same words, different order/plural - almost always it
            score += 10.0
        scored.append((score, candidate))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [c for _, c in scored[:n]]


def _one_action(entry: dict, kind: str, action: str) -> dict:
    """One action's full arg schema, plus the exact call shape to copy."""
    for a in entry.get("actions") or []:
        if a["name"] == action:
            runner_tool = "aat_run_tool" if kind == "tool" else "aat_run_agent"
            key = "tool" if kind == "tool" else "agent"
            action_out = {
                "name": a["name"],
                "description": a.get("description", ""),
                "args": _args_schema(a.get("args")),
            }
            # A worked example is worth more than the schema on its own: it settles the
            # shape AND the conventions the schema cannot express (how a param binds a
            # variable, which names are literal).
            if a.get("examples"):
                action_out["examples"] = a["examples"]
            if a.get("output_schema"):
                action_out["output_schema"] = a["output_schema"]
            return {"capability": {
                "kind": kind,
                "name": entry["name"],
                "action": action_out,
                "call": {runner_tool: {key: entry["name"], "action": a["name"],
                                       "args": "<flag name -> value>"}},
                "hint": ("Use each arg 'name' EXACTLY as spelled above (hyphens, "
                         "not underscores) - it is the literal flag."),
            }}
    names = _action_names(entry)
    return {"unknown_action": action, "of": entry["name"], "kind": kind,
            "action_count": len(names),
            "did_you_mean": _suggest(action, names) or names[:15],
            "hint": (f"{entry['name']} has no action {action!r}. Retry with one of "
                     f"did_you_mean, or call capabilities with "
                     f"search='<keywords>' to look one up.")}


def _degraded(entry: dict, kind: str, size: int, limit: int) -> dict:
    """The over-threshold answer: the action-name INDEX plus how to drill in.

    Names only (procesio: ~10 KB for 379 of them) instead of the full schema, so
    the caller still sees everything that exists and can then ask for the one
    action it needs."""
    names = _action_names(entry)
    body = {
        "kind": kind,
        "name": entry["name"],
        "description": entry.get("description", ""),
        "ready": bool(entry.get("ready", True)),
        "missing_secrets": entry.get("missing_secrets", []),
        "truncated": True,
        "reason": (f"full schema is {size} bytes, over the {limit}-byte limit; "
                   f"returning the action index instead"),
        "action_count": len(names),
        "hint": (f"Call capabilities with name='{entry['name']}' AND "
                 f"action='<one of actions>' for that action's arg schema, or "
                 f"search='<keywords>' to find the right action by keyword. Do "
                 f"NOT try to grep or read the full schema."),
    }
    # Insurance: if even the name index is over budget, drop it and leave search
    # as the only door rather than shipping another unusable payload.
    if len(json.dumps(names, ensure_ascii=False)) <= limit:
        body["actions"] = names
    else:
        body["hint"] = ("Too many actions to list. Call capabilities with "
                        f"name='{entry['name']}' and search='<keywords>'.")
    return {"capability": body}


_DESTRUCTIVE = {"delete", "remove", "destroy", "drop", "purge", "uninstall"}


def _search_actions(query: str, kind: str | None = None, name: str | None = None,
                    limit: int = 20) -> dict:
    """Keyword search over ACTIONS (name + description), scoped to one capability
    when `name` is given, otherwise across every tool and agent.

    AND semantics FIRST: an action matches when every token appears somewhere in
    '<capability>.<action> <description>'. Matches come back COMPACT (no arg schemas) -
    the caller then asks for the one it wants by action name.

    When AND finds nothing the search RELAXES instead of returning an empty list, and
    says which words it had to drop. A strict-AND miss is not "no such action", it is
    "one of your words is not the word we used", and an empty answer is read as the
    former: observed live, `search "procesio form create template"` returned 0 because
    no description contains "template" - so a run abandoned the curated `form-create`
    (which "procesio create form" finds instantly), fell back to the raw Swagger
    endpoint, tripped the irreversibility gate, and blocked at step 0. The words a
    caller guesses come from the target system's vocabulary, not ours, so one wrong
    guess must not hide the whole family."""
    tokens = [t for t in (query or "").lower().split() if t]
    if not tokens:
        raise KeyError("search requires at least one keyword")

    tools, agents, _ = _scan_registry()
    pools: list[tuple[list[dict], str]] = []
    if kind in (None, "tool"):
        pools.append((tools, "tool"))
    if kind in (None, "agent"):
        pools.append((agents, "agent"))

    # A token equal to the capability being searched carries NO information once the
    # search is already scoped to it - every one of that capability's actions contains it.
    # Left in, it lets a query whose real words all miss ("procesio zzzz qqqq") still
    # score 1 everywhere and hand back the entire catalog, which is worse than the empty
    # answer this function is trying to fix. Unscoped it stays: there, naming the tool IS
    # how you narrow.
    informative = [t for t in tokens if not (name and t == name.lower())]
    if not informative:
        informative = tokens

    # One pass, scoring every action by HOW MANY informative tokens it carries. The strict
    # answer is the full-count group; a relaxation is the next count down, i.e. the largest
    # subset of the query that matches anything - no subset enumeration needed.
    candidates: list[tuple[int, float, int, dict]] = []     # (hits, precision, score, match)
    for pool, pool_kind in pools:
        for entry in pool:
            if entry.get("error"):
                continue
            if name and entry.get("name") != name:
                continue
            for a in entry.get("actions") or []:
                action = a["name"]
                desc = a.get("description", "") or ""
                hay = f"{entry['name']}.{action} {desc}".lower()
                hit = [t for t in informative if t in hay]
                if not hit:
                    continue
                low = action.lower()
                score = sum(t in low for t in informative) * 10
                if low == query.strip().lower():
                    score += 100
                elif all(t in low for t in informative):
                    score += 50
                # How much of the action's NAME the query accounts for. Substring matching
                # makes "template" hit `delete-customurl-formtemplate-by-id` as loudly as
                # it hits `form-create`; counting the name's OWN segments breaks that tie
                # toward the action that is mostly what was asked for, rather than one that
                # merely contains it.
                segs = [s for s in low.replace("_", "-").split("-") if s]
                covered = sum(1 for s in segs if any(t in s or s in t for t in hit))
                precision = covered / len(segs) if segs else 0.0
                # A relaxed search answers a question the caller did not quite ask, so it
                # must not lead with a destructive action: "generate form" and "delete
                # form" match the same one word, and offering the deletion first is how a
                # near-miss becomes an incident. Only demoted when the caller did not ask
                # to destroy anything.
                if _DESTRUCTIVE & set(segs) and not (_DESTRUCTIVE & set(informative)):
                    precision -= 1.0
                candidates.append((len(hit), precision, score, {
                    "kind": pool_kind,
                    "name": entry["name"],
                    "action": action,
                    "description": desc[:200],
                }))

    if not candidates:
        return {
            "query": query, "count": 0, "total_matches": 0, "matches": [],
            "hint": ("No action mentions ANY of these words. This is conclusive for AAT's "
                     "own catalog - do not rephrase and retry with synonyms. If you are "
                     "looking for a building block INSIDE a target system (a node/step "
                     "type), it lives in that system, not here: list it with that tool's "
                     "own catalog action (for procesio, list-actions-catalog)."),
        }

    best = max(h for h, _, _, _ in candidates)
    group = [(p, s, m) for h, p, s, m in candidates if h == best]
    group.sort(key=lambda g: (-g[0], -g[1], g[2]["name"], g[2]["action"]))
    matches = [m for _, _, m in group[:limit]]

    # A relaxation that survived only on a CAPABILITY NAME found nothing: "procesio
    # form-validate" unscoped kept every procesio action alive on the word "procesio"
    # alone and answered with 405 rows, none of them about validating a form. The
    # scoped path strips that token up front; unscoped it cannot, because naming the
    # tool is how you narrow there - so the emptiness has to be recognised here, after
    # scoring. Saying "nothing in procesio mentions form-validate" is both true and
    # what the caller needs; a page of unrelated actions is neither.
    cap_names = {e["name"].lower() for pool, _ in pools for e in pool if e.get("name")}
    surviving = {t for t in informative
                 if any(t in f"{m['name']}.{m['action']} {m['description']}".lower()
                        for m in matches)}
    if best < len(informative) and surviving and surviving <= cap_names:
        missed = [t for t in informative if t not in surviving]
        where = ", ".join(sorted(surviving))
        return {
            "query": query, "count": 0, "total_matches": 0, "matches": [],
            "relaxed": True, "matched_terms": sorted(surviving), "dropped_terms": missed,
            "hint": (f"Nothing in {where} mentions {missed} - only the capability name "
                     f"itself matched, which every one of its actions carries. This is "
                     f"conclusive: do not rephrase with synonyms. If {missed} names a "
                     f"building block INSIDE the target system (a node/step/control "
                     f"type), it lives in that system, not in AAT's catalog - list it "
                     f"with that tool's own catalog action (for procesio, "
                     f"list-actions-catalog)."),
        }

    out = {
        "query": query,
        "count": len(matches),
        "total_matches": len(group),
        "matches": matches,
        "hint": ("Call capabilities with name=<name> and action=<action> for that "
                 "action's full arg schema before running it."),
    }
    if best < len(informative):
        # Name the dropped words explicitly. A "closest match" that does not say what was
        # ignored invites the caller to trust a result answering a different question.
        # Measured against the TOP match, not the whole page: different matches cover
        # different words, so a set-wide calculation reports "relaxed, dropped nothing",
        # which reads as a contradiction and tells the caller nothing about the action it
        # is actually about to read.
        top = matches[0]
        top_hay = f"{top['name']}.{top['action']} {top['description']}".lower()
        dropped = [t for t in informative if t not in top_hay]
        out["relaxed"] = True
        out["matched_terms"] = [t for t in informative if t not in dropped]
        out["dropped_terms"] = dropped
        out["hint"] = (
            f"No action matches ALL of {informative}; these match "
            f"{out['matched_terms']} (ignoring {dropped}) and are ordered closest-first. "
            f"A dropped word is usually the TARGET SYSTEM's vocabulary rather than AAT's. "
            f"Read the top one with capabilities name=<name> action=<action> before "
            f"rephrasing - rephrasing rarely helps here.")
        if len(group) > 3 * limit:
            out["hint"] = (
                f"Too vague: {len(group)} actions match only {out['matched_terms']} "
                f"(ignoring {dropped}), so this list is not an answer. Add a word that "
                f"names what you want DONE (create, edit, run, list) "
                + ("" if name else "and pass name=<capability> to scope it ")
                + "and search again.")
    return out


def action_help(name: str, action: str | None, kind: str | None = None) -> dict | None:
    """Compact 'what was I supposed to pass' for ONE call, used to enrich a failed
    run (server._run). Returns None when the capability is unknown.

    This is the cheapest fix in the chain: when a call fails with a bad flag or a
    bad action name, the framework already holds the right answer at that exact
    moment - it just never said it."""
    entry, found_kind = _find(name, kind)
    if entry is None:
        return None
    names = _action_names(entry)
    if names and action and action not in names:
        return {"of": entry["name"], "kind": found_kind, "unknown_action": action,
                "action_count": len(names),
                "did_you_mean": _suggest(action, names) or names[:15]}
    args = entry.get("args")
    if names:
        for a in entry.get("actions") or []:
            if a["name"] == action:
                args = a.get("args")
                break
        else:
            return None
    return {"of": entry["name"], "kind": found_kind, "action": action,
            "valid_args": [
                {"name": s["name"], "type": s["type"], "required": s["required"]}
                for s in _args_schema(args)
            ]}


def capabilities(kind: str | None = None, name: str | None = None,
                 action: str | None = None, search: str | None = None,
                 full: bool = False) -> dict:
    """Discover AAT capabilities, narrowest door first.

    - search              -> keyword search over actions (optionally within `name`)
    - name + action       -> that ONE action's arg schema
    - name                -> the full schema, or its action index if oversized
    - neither             -> the compact tool/agent/skill list (the router map),
                             trimmed unless `full` asks for the longer line
    """
    tools, agents, skills = _scan_registry()

    if search:
        return _search_actions(search, kind=kind, name=name)

    # An action without a capability name is still answerable: look it up across
    # everything rather than refusing on a technicality.
    if action and not name:
        return _search_actions(action, kind=kind)

    if name:
        entry, found_kind = _find(name, kind)
        if entry is None:
            raise KeyError(f"no tool or agent named {name!r}")
        if action:
            return _one_action(entry, found_kind, action)
        full = _full(entry, found_kind)
        limit = _max_bytes()
        size = len(json.dumps(full, ensure_ascii=False))
        if limit and size > limit and entry.get("actions"):
            return _degraded(entry, found_kind, size, limit)
        return {"capability": full}

    out: list[dict] = []
    if kind in (None, "tool"):
        out += [_compact(e, "tool", full) for e in tools if not e.get("error")]
    if kind in (None, "agent"):
        out += [_compact(e, "agent", full) for e in agents if not e.get("error")]
    if kind in (None, "skill"):
        out += [_compact(e, "skill", full) for e in skills
                if not e.get("error")]
    return {"count": len(out), "capabilities": out}


# What a metric may carry as its `tool` and `action` labels: {kind: {name: its declared actions}},
# as of the last registry scan. It is kept apart from _REG_CACHE because it has to answer without
# ever scanning: a label is looked up at the end of every call, and a scan there (seconds, on a
# cold cache) would be paid by the caller. Empty while metrics are off.
_METRIC_NAMES: dict[str, dict[str, frozenset]] = {}


def _index_metric_names(tools: list, agents: list) -> None:
    """Refresh _METRIC_NAMES from a registry scan. Never raises: a label is not worth a failed scan."""
    try:
        _METRIC_NAMES.update(
            tool={e["name"]: frozenset(_action_names(e)) for e in tools if e.get("name")},
            agent={e["name"]: frozenset(_action_names(e)) for e in agents if e.get("name")})
    except Exception:  # noqa: BLE001
        pass


def warm_metric_labels() -> threading.Thread:
    """Scan the registry once, in the background, so that calls carry their labels from the start
    instead of from the first `capabilities` call on. Until it ends a call is labelled `unknown`."""
    def scan() -> None:
        try:
            tools, agents, _ = _scan_registry()
            _index_metric_names(tools, agents)
        except Exception as e:  # noqa: BLE001
            runtime_log.write("aat-metrics", f"registry scan for the metric labels failed "
                              f"({type(e).__name__}); calls are labelled 'unknown' until the next scan",
                              level=runtime_log.WARNING, fields={"ExceptionType": type(e).__name__})

    thread = threading.Thread(target=scan, name="aat-metrics-labels", daemon=True)
    thread.start()
    return thread


def _metric_labels(kind: str, name, action) -> tuple[str, str]:
    """The (tool, action) label values of one call. Both arrive from the model, so a name is used
    only when the registry lists it, and an action only when that capability declares it."""
    actions = _METRIC_NAMES.get(kind, {}).get(name) if isinstance(name, str) else None
    if actions is None:
        return metrics.UNKNOWN, metrics.UNKNOWN
    if not action:
        return name, metrics.NONE
    return name, action if isinstance(action, str) and action in actions else metrics.UNKNOWN


# The file the current call's subprocess appends its HTTP requests to (tools/_lib/httptrace.py),
# or None: metrics are off, or the file could not be made. Set around each measured call.
_http_trace_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "aat_http_trace", default=None)
_HTTP_TRACE_DIR: list[str] = []
_HTTP_TRACE_DIR_LOCK = threading.Lock()


def _open_http_trace() -> str | None:
    """An empty file for one call's HTTP trace, or None. Never raises.

    A tool runs as a uid of its own (runner._run_isolated) and its private HOME is removed with
    it, so the file lives here instead: in a folder of this process that others can enter but
    not list, under a random name, writable by anyone who was given the name. What comes back in
    it is read as untrusted input (metrics.http_trace)."""
    try:
        with _HTTP_TRACE_DIR_LOCK:
            if not _HTTP_TRACE_DIR or not os.path.isdir(_HTTP_TRACE_DIR[0]):
                folder = tempfile.mkdtemp(prefix="aat-http-trace-")
                os.chmod(folder, 0o711)
                _HTTP_TRACE_DIR[:] = [folder]
            folder = _HTTP_TRACE_DIR[0]
        fd, path = tempfile.mkstemp(prefix="call-", dir=folder)
        os.close(fd)
        os.chmod(path, 0o666)
        return path
    except Exception:  # noqa: BLE001 - no trace is not a reason to fail a call
        return None


def _take_http_trace(path: str) -> str | None:
    """What the call wrote to its trace file, which is then removed. Never raises."""
    try:
        with open(path, "rb") as f:
            data = f.read(metrics.HTTP_TRACE_MAX_BYTES)
        return data.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return None
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _with_http_trace(env: dict | None) -> dict | None:
    """`env` plus the variable that tells the subprocess where to note its HTTP requests, when
    this call has a trace file. Unchanged otherwise."""
    path = _http_trace_ctx.get()
    if not path:
        return env
    return {**(env or {}), httptrace.ENV: path}


def _timed_out(result) -> bool:
    error = result.get("error") if isinstance(result, dict) else None
    return isinstance(error, dict) and error.get("code") == "timeout"


def _measured(kind: str):
    """Record every call of the wrapped run_tool / run_agent: one log line when it ends, and, in
    the runtime metrics, how long it took, whether it succeeded, that it is running, and the HTTP
    requests its subprocess noted. Changes nothing about the call - the arguments, the result and
    any exception pass through untouched. While metrics are off only the log line is written."""
    def wrap(fn):
        @functools.wraps(fn)
        def call(*args, **kwargs):
            # The first parameter is named after the kind (tool= / agent=), the second is action.
            name = args[0] if args else kwargs.get(kind)
            action = args[1] if len(args) > 1 else kwargs.get("action")
            result = raised = http = None
            # A clock of its own: the metrics clock is read exactly twice per call.
            started = time.perf_counter()
            try:
                if not metrics.enabled():
                    result = fn(*args, **kwargs)
                    return result
                trace = _open_http_trace()
                token = _http_trace_ctx.set(trace)
                seen = None
                try:
                    with metrics.tool_call(kind, lambda: _metric_labels(kind, name, action)) as seen:
                        result = seen.result = fn(*args, **kwargs)
                        return result
                finally:
                    _http_trace_ctx.reset(token)
                    if trace:
                        http = metrics.http_trace(
                            _take_http_trace(trace), kind, getattr(seen, "tool", metrics.UNKNOWN),
                            getattr(seen, "action", metrics.UNKNOWN), _timed_out(result),
                            msg=message_id())
            except BaseException as e:
                raised = type(e).__name__
                raise
            finally:
                _log_call(kind, name, action, result, raised, time.perf_counter() - started, http)
        return call
    return wrap


@_measured("tool")
def run_tool(tool: str, action: str | None, args: dict[str, Any] | None,
             credential: str | None = None) -> dict:
    """Execute a tool. args is a JSON object -> --flags via runner.flags_from
    (dict/list values are JSON-encoded into ONE argv element; no shell). Host-only
    tools are delegated to the host-runner when AAT_HOST_RUNNER_URL is set.

    credential: inside a PROCESIO turn, the name of the PROCESIO credential to use when several
    fit the tool (the previous call listed them). Ignored outside a turn."""
    # Wrap in a per-work-unit accounting span (no-op locally; the platform injects a
    # sink that acquires an EE slot + emits TrackAction - spec P0.0-05 / seam S2).
    with accounting.work_unit("tool", ws=_workspace_ctx.get(),
                              user=_user_ctx.get()) as wu:
        wu["tool"] = tool
        if action:
            wu["action"] = action
        if os.environ.get("AAT_HOST_RUNNER_URL") and _is_host_only("tool", tool):
            return _delegate("tool", tool, action, args)
        argv = ([action] if action else []) + runner.flags_from(args)
        turn_token = _turn_token_ctx.get()
        if turn_token:
            refusal = _workspace_refusal("tool", tool, args, action)
            if refusal is not None:
                return refusal
            env = _turn_env("tool", tool, turn_token, credential, action)
            if env is None:
                return _no_key_refusal(turn_credentials.fetch_key(turn_token).message)
            return _after_auth_failure("tool", tool, turn_token,
                                       runner.run_tool(tool, argv, env=_with_http_trace(env),
                                                       inherit_env=False,
                                                       timeout=_run_timeout()), action)
        return runner.run_tool(tool, argv, env=_with_http_trace(_user_env()), timeout=_run_timeout())


@_measured("agent")
def run_agent(agent: str, action: str | None, args: dict[str, Any] | None,
              credential: str | None = None) -> dict:
    refusal = _managed_turn_refusal(agent, action)
    if refusal is not None:
        return refusal
    with accounting.work_unit("agent", ws=_workspace_ctx.get(),
                              user=_user_ctx.get()) as wu:
        wu["agent"] = agent
        if action:
            wu["action"] = action
        if os.environ.get("AAT_HOST_RUNNER_URL") and _is_host_only("agent", agent):
            return _delegate("agent", agent, action, args)
        argv = ([action] if action else []) + runner.flags_from(args)
        turn_token = _turn_token_ctx.get()
        if turn_token:
            refusal = _workspace_refusal("agent", agent, args, action)
            if refusal is not None:
                return refusal
            env = _turn_env("agent", agent, turn_token, credential, action)
            if env is None:
                return _no_key_refusal(turn_credentials.fetch_key(turn_token).message)
            return _after_auth_failure("agent", agent, turn_token,
                                       runner.run_agent(agent, argv, env=_with_http_trace(env),
                                                        inherit_env=False,
                                                        timeout=_run_timeout()), action)
        return runner.run_agent(agent, argv, env=_with_http_trace(_user_env()), timeout=_run_timeout())


def get_skill(name: str) -> dict:
    """Return a skill's full markdown plus a metadata-only bundled-resource index
    (model-decided skill loading — the substitute for harness auto-trigger; see spec 04).
    A remote MCP client has no filesystem, so the index is how it discovers a skill's
    references/scripts/assets; fetch one on demand with get_skill_resource."""
    m = registry.get_skill(name)  # raises KeyError if unknown
    md = (m.path / "SKILL.md").read_text(encoding="utf-8")
    return {"name": m.name, "content": md, "resources": resource_index(m.path)}


def get_skill_resource(name: str, path: str) -> dict:
    """Return one safe UTF-8 resource below references/, scripts/, or assets/ of a skill.
    The path must come from get_skill's resource index; traversal, symlink escape, a
    non-text file and an oversized file are all rejected (see tools/_lib/skill_resources)."""
    m = registry.get_skill(name)  # raises KeyError if unknown
    return {"name": m.name, "resource": read_text_resource(m.path, path)}
