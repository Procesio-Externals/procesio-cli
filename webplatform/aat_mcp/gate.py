"""Reversibility gate for the MCP bridge - code-authoritative, pre-execution.

Reuses the ONE shared definition of "irreversible" (agents/_lib/reversibility) that
already guards `orchestrator drive` and the `deputy`, so the web platform cannot
drift into a second policy. The gate decides which execution PATH an action takes:

  reversible  -> runs on `run_tool` / `run_agent`
  irreversible -> refused there; must go through `run_tool_confirmed` /
                  `run_agent_confirmed`, which opencode marks `ask` so a HUMAN
                  approves the click. A model cannot forge that approval, and it
                  cannot bypass by choosing the plain tool - the plain tool refuses
                  and names the confirmed path. That is the gate being code, not a
                  prompt (reversibility.py:1-8).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agents._lib import reversibility  # noqa: E402


def classify(name: str, action: str | None) -> dict:
    """Classify on the tool/agent NAME + the ACTION verb (send-message,
    delete-messages, issue-invoice, post-message). Deliberately NOT on arg values -
    a subject line "please send me..." must not trip the gate; the verb lives in the
    action name for every AAT side effect. Returns reversibility.classify()'s dict:
    {reversible, verb, blast_class, reason}."""
    argv = [action] if action else []
    return reversibility.classify(name, argv)


def deny_irreversible_env() -> bool:
    """Headless/autonomous fail-safe. When AAT_MCP_DENY_IRREVERSIBLE is set, even the
    *_confirmed tools refuse irreversible actions - there is no human in the seat to
    approve. Default (unset) = interactive: opencode's `ask` on the confirmed tools
    is the human gate."""
    return os.environ.get("AAT_MCP_DENY_IRREVERSIBLE", "").strip().lower() in (
        "1", "true", "yes", "on")


def decide(name: str, action: str | None, *, level: str = "L1", scopes=None,
           role: str | None = None, ws_cap: str | None = None) -> dict:
    """Graded autonomy decision for the MCP layer (spec P0.0-07). Clamps the requested
    level by the caller's role and any workspace cap, then applies the code-authoritative
    reversibility gate at the effective level. The `AAT_MCP_DENY_IRREVERSIBLE` fail-safe
    still hard-denies anything that would need human approval.

    Default (level='L1', no role/cap) reproduces the binary gate exactly: reversible
    runs, irreversible needs approval - so existing callers are unaffected."""
    argv = [action] if action else []
    if role is not None or ws_cap is not None:
        eff = reversibility.clamp(level, role=role, ws_cap=ws_cap)
    else:
        eff = level
    if eff is None:
        return {"allow": False, "needs_confirmation": False, "level": None,
                "reason": "role has no AAT access", "verb": None, "blast_class": None}
    d = reversibility.decide(name, argv, level=eff, scopes=scopes)
    if d.get("needs_confirmation") and deny_irreversible_env():
        return {**d, "allow": False, "needs_confirmation": False,
                "reason": "AAT_MCP_DENY_IRREVERSIBLE: " + d["reason"]}
    return d
