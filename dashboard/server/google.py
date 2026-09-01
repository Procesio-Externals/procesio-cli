"""Google multi-account (profile) management for the dashboard.

The 8 Google tools share one OAuth credential set under the `google:` namespace
and support MULTIPLE accounts, each keyed by an arbitrary lowercase LABEL
(`default`, `personal`, `work`, ...) - NOT by email. Only `google-mail` (and
`google-contacts`) expose the `--account` surface + `auth-accounts`, and the token
they write is shared by every Google tool, so we drive ALL account operations
through `google-mail`.

  list   -> google-mail auth-accounts        (+ best-effort email via get-profile)
  add /
  re-auth-> google-mail auth-login --account  (BLOCKS on browser consent -> a job)
  remove -> google-mail auth-logout --account (fast)

The OAuth CLIENT (google:oauth-client) is a precondition the user provisions as a
normal credential (the card's client-key row); we only manage the per-account
tokens here.
"""
from __future__ import annotations

import re
from typing import Any

from . import inventory, jobs, runner

_DRIVER = "google-mail"
_LABEL_RE = re.compile(r"^[a-z0-9._-]+$")


def _valid_label(label: str) -> bool:
    return bool(_LABEL_RE.match(label))


def _account_args(action_argv: list[str], label: str) -> list[str]:
    """--account goes AFTER the action (a global flag stripped by the tool)."""
    argv = list(action_argv)
    if label:
        argv += ["--account", label]
    return argv


def accounts(req) -> Any:
    """List connected Google profiles - fast (labels only, no network). The email
    for each is fetched lazily by the UI via /api/google/email so the list appears
    instantly instead of blocking on a get-profile call per account."""
    r = runner.run_tool(_DRIVER, ["auth-accounts"], timeout=30)
    if not r["ok"]:
        # Most common cause: the OAuth client isn't stored yet.
        st = runner.run_tool(_DRIVER, ["auth-status"], timeout=20)
        has_client = bool(st["ok"] and (st["data"] or {}).get("has_client"))
        return {"ok": False, "has_client": has_client,
                "accounts": [], "error": r["error"]}
    data = r["data"] or {}
    active = data.get("active")
    out = [{"account": a.get("account"), "has_token": bool(a.get("has_token")),
            "active": a.get("account") == active}
           for a in data.get("accounts", [])]
    return {"ok": True, "active": active, "accounts": out}


def email(req) -> Any:
    """Resolve one account's email address (a live get-profile call). Lazy, so a
    slow or failing account never blocks the account list."""
    label = (req.q("account") or "").strip().lower()
    if not label or not _valid_label(label):
        return (400, {"error": "invalid account"})
    pr = runner.run_tool(_DRIVER, ["get-profile", "--account", label], timeout=25)
    if pr["ok"] and isinstance(pr["data"], dict):
        return {"account": label,
                "email": pr["data"].get("emailAddress") or pr["data"].get("email")}
    return {"account": label, "email": None,
            "error": (pr.get("error") or {}).get("message")}


def login(req) -> Any:
    """Add a new profile or re-authorize an existing one (same command). Runs as a
    job because auth-login opens a browser and blocks until the user consents."""
    label = (req.body.get("account") or "default").strip().lower()
    if not _valid_label(label):
        return (400, {"error": "invalid label",
                      "message": "Use a short label like 'personal' or 'work' "
                                 "(lowercase letters, digits, . _ - ). Not an email."})
    argv = ["run-tool.py", _DRIVER] + _account_args(["auth-login"],
                                                    "" if label == "default" else label)
    job = jobs.create("google-oauth", argv, stdin_signal=False)
    snap = job.snapshot()
    snap["account"] = label
    return snap


def remove(req) -> Any:
    """Remove ONE profile's token (leaves the shared oauth-client intact)."""
    label = (req.body.get("account") or "").strip().lower()
    if not label:
        return (400, {"error": "account label is required"})
    if not _valid_label(label):
        return (400, {"error": "invalid label"})
    argv = _account_args(["auth-logout"], "" if label == "default" else label)
    r = runner.run_tool(_DRIVER, argv, timeout=30)
    if r["ok"]:
        inventory.invalidate()
        return {"ok": True, "account": label, "data": r["data"]}
    return {"ok": False, "account": label, "error": r["error"]}
