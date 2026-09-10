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
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import registry  # noqa: E402
from dashboard.server import runner  # noqa: E402  (shared shell-to-script bridge)
from tools._lib import accounting  # noqa: E402  (per-work-unit accounting seam, P0.0-05)

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
    return {"ok": False, "refused": {
        "agent": agent, "action": action, "reason": "managed_turn",
        "message": (f"'{agent} {action}' starts a second orchestration loop, and this turn is already "
                    f"one step of an externally-managed plan. Do the concrete increment yourself with "
                    f"run_tool / run_agent, then end your reply with the control line you were given."),
    }}


def _user_env() -> dict | None:
    env: dict = {}
    uid = _user_ctx.get()
    if uid:
        env["AAT_USER_ID"] = str(uid)
    ws = _workspace_ctx.get()
    if ws:
        env["AAT_WORKSPACE_ID"] = str(ws)
    return env or None

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


def _scan_registry():
    """Cache the registry scan (parse ~74 manifests + per-secret presence checks) for a
    short TTL. In a running container the registry is static and the model calls
    capabilities several times per loop; without this each call re-parses every manifest
    and re-checks every secret. AAT_REGISTRY_TTL seconds (0 = off)."""
    ttl = float(os.environ.get("AAT_REGISTRY_TTL", "30") or 0)
    if ttl > 0:
        hit = _REG_CACHE.get("data")
        if hit is not None and hit[1] > time.monotonic():
            return hit[0]
    tools = registry.list_tools()
    agents = registry.list_agents({t["name"]: t for t in tools})
    skills = registry.list_skills()
    if ttl > 0:
        _REG_CACHE["data"] = ((tools, agents, skills), time.monotonic() + ttl)
    return tools, agents, skills


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


def run_tool(tool: str, action: str | None, args: dict[str, Any] | None) -> dict:
    """Execute a tool. args is a JSON object -> --flags via runner.flags_from
    (dict/list values are JSON-encoded into ONE argv element; no shell). Host-only
    tools are delegated to the host-runner when AAT_HOST_RUNNER_URL is set."""
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
        return runner.run_tool(tool, argv, env=_user_env())


def run_agent(agent: str, action: str | None, args: dict[str, Any] | None) -> dict:
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
        return runner.run_agent(agent, argv, env=_user_env())


def get_skill(name: str) -> dict:
    """Return a skill's full markdown (model-decided skill loading — the substitute
    for harness auto-trigger; see spec 04)."""
    m = registry.get_skill(name)  # raises KeyError if unknown
    md = (m.path / "SKILL.md").read_text(encoding="utf-8")
    return {"name": name, "content": md}
