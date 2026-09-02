"""Reversibility classification - the shared definition of "irreversible".

The decision policy turns on exactly one axis: reversible, act; irreversible, stop
and ask a human. This is a MODULE rather than a rule in a prompt because a rule in
a prompt is something a model can talk itself past. Here it is evaluated BEFORE the
model is asked anything, so an irreversible action cannot be auto-decided even when
the prompt is wrong.

Deliberately conservative. A hit means "treat as irreversible" and escalate or
refuse. A false positive costs one escalation; a false negative costs real-world
blast radius, and the caller reporting on itself is not a reliable witness. The
asymmetry is the reason to lean.

KNOW WHAT THIS IS. It matches VERBS, in English, in the action name and argv. An
action whose name carries no listed verb is reported reversible, so silence here is
absence of evidence and not a safety guarantee. Treat it as a guard rail that stops
the obvious mistakes, never as a sandbox: it does not inspect what a call will
actually do, and it does not read any language but English. Extending the verb list
is the intended way to close a gap you find.

One definition, one place. The verb list started inside a single agent's driver
loop; it lives here so that every caller shares it and no two of them can drift
into different ideas of what "irreversible" means.
"""
from __future__ import annotations

import re

# Verbs / action fragments that name an irreversible, real-world side effect.
# Matched against a tool/agent name, its action verb (argv[0]), and every argv
# token. Kept as a flat tuple on purpose: greppable, testable, no clever grouping.
IRREVERSIBLE_VERBS: tuple[str, ...] = (
    "send", "delete", "remove", "purge", "drop", "pay", "purchase", "buy",
    "charge", "transfer", "post", "publish", "ban", "kick", "issue-invoice",
    "wire", "refund", "archive", "revoke", "deactivate", "wipe",
)

# The four blast-radius classes worth naming: data loss, money out, message sent,
# someone else's production. Used to explain WHY something escalated, in terms a
# person recognises rather than an invented taxonomy.
_CLASS_OF_VERB: dict[str, str] = {
    "send": "message-sent", "post": "message-sent", "publish": "message-sent",
    "issue-invoice": "money-out", "pay": "money-out", "purchase": "money-out",
    "buy": "money-out", "charge": "money-out", "transfer": "money-out",
    "wire": "money-out", "refund": "money-out",
    "delete": "data-loss", "remove": "data-loss", "purge": "data-loss",
    "drop": "data-loss", "wipe": "data-loss", "archive": "data-loss",
    "ban": "third-party-state", "kick": "third-party-state",
    "revoke": "third-party-state", "deactivate": "third-party-state",
}


def _probe_hit(probe: str) -> str | None:
    """Return the irreversible verb matched in one string, or None.

    Word-ish match so `send` hits "send" and "send-message" but not "sender" or
    "resend-guard". Hyphen/underscore/space are all treated as token separators
    because tool actions are kebab-case and argv tokens are not.
    """
    probe = probe.lower()
    for verb in IRREVERSIBLE_VERBS:
        if probe == verb:
            return verb
        if re.search(rf"(^|[-_ ]){re.escape(verb)}([-_ ]|$)", probe):
            return verb
    return None


def match(name: str, argv: list[str] | None = None) -> str | None:
    """Return the matched irreversible verb for an action, or None.

    Checks the tool/agent name, the action verb (argv[0]), and every argv token.
    This is the function drive.py's `_looks_irreversible` becomes.
    """
    argv = list(argv or [])
    probes = [str(name)] + [str(tok) for tok in argv]
    for probe in probes:
        hit = _probe_hit(probe)
        if hit:
            return hit
    return None


def classify(name: str, argv: list[str] | None = None) -> dict:
    """Classify an action's reversibility.

    Returns:
        {"reversible": bool, "verb": str|None, "blast_class": str|None,
         "reason": str}

    `blast_class` is one of money-out, message-sent, data-loss or
    third-party-state, and None when the action is reversible.
    """
    verb = match(name, argv)
    if verb is None:
        return {"reversible": True, "verb": None, "blast_class": None,
                "reason": "no irreversible verb in action name or argv"}
    blast = _CLASS_OF_VERB.get(verb, "irreversible")
    return {"reversible": False, "verb": verb, "blast_class": blast,
            "reason": f"action matches irreversible verb {verb!r} ({blast})"}


def classify_text(text: str) -> dict:
    """Classify a free-text question / proposed action.

    The deputy is asked questions in prose ("should I send the reminder?"), not
    argv. Same verb list, tokenised over the text. Conservative by construction:
    any irreversible verb anywhere in the text trips the gate, because the cost of
    a needless escalation is one WhatsApp line and the cost of a miss is real.
    """
    for token in re.split(r"[^\w-]+", str(text).lower()):
        if not token:
            continue
        hit = _probe_hit(token)
        if hit:
            blast = _CLASS_OF_VERB.get(hit, "irreversible")
            return {"reversible": False, "verb": hit, "blast_class": blast,
                    "reason": f"text names irreversible verb {hit!r} ({blast})"}
    return {"reversible": True, "verb": None, "blast_class": None,
            "reason": "no irreversible verb in text"}


# ---------------------------------------------------------------------------
# Autonomy levels (spec P0.0-07). The binary gate above is generalized to four
# graded levels WITHOUT weakening it: today's behaviour (reversible runs;
# irreversible needs approval) is exactly L1, the default. Still code-authoritative
# and evaluated before the model is asked - a model cannot self-escalate.
# ---------------------------------------------------------------------------

LEVELS: tuple[str, ...] = ("L0", "L1", "L2", "L3")
_LEVEL_RANK = {lvl: i for i, lvl in enumerate(LEVELS)}

# Verbs that are PURE READS (no side effect). L0 allows ONLY these. Conservative by
# construction: anything whose primary verb is not clearly a read is refused at L0.
READ_VERBS: tuple[str, ...] = (
    "get", "list", "read", "search", "find", "show", "view", "fetch", "status",
    "describe", "inspect", "check", "count", "lookup", "resolve", "recall", "query",
    "probe", "catalog", "help", "guidance", "checklist", "summary", "stats",
)

# role -> the maximum autonomy that role may run or grant (spec P0.0-07 / D14).
_ROLE_MAX: dict[str, str | None] = {
    "none": None, "read": "L0", "update": "L1", "write": "L2", "admin": "L3",
}


def _read_hit(probe: str) -> str | None:
    probe = probe.lower()
    for verb in READ_VERBS:
        if probe == verb or re.search(rf"(^|[-_ ]){re.escape(verb)}([-_ ]|$)", probe):
            return verb
    return None


def is_read_only(name: str, argv: list[str] | None = None) -> bool:
    """True iff the action has no irreversible verb AND its primary verb (argv[0], else
    the action name) is a known read verb. Used to gate L0 (read-only)."""
    argv = list(argv or [])
    if match(name, argv) is not None:
        return False
    primary = str(argv[0]) if argv else str(name)
    return _read_hit(primary) is not None


def _in_scope(name: str, argv: list[str], scopes: set, verb: str | None) -> bool:
    """L2: is this irreversible action inside the caller-provided allow-list? Matches on
    the tool/agent name, ``name:action``, the action verb, or the irreversible verb."""
    if not scopes:
        return False
    action = str(argv[0]) if argv else ""
    cands = {str(name), (f"{name}:{action}" if action else str(name)), action, verb or ""}
    return bool(cands & set(scopes))


def decide(name: str, argv: list[str] | None = None, *, level: str = "L1",
           scopes=None) -> dict:
    """Graded autonomy decision, built on ``classify()``. Returns:
        {allow, needs_confirmation, level, reason, verb, blast_class}
      - allow=False              -> blocked outright (L0 mutation).
      - allow, needs_confirmation=False -> runs directly.
      - allow, needs_confirmation=True  -> runs only via the human-approval path.
    """
    argv = list(argv or [])
    cls = classify(name, argv)
    lvl = level if level in _LEVEL_RANK else "L1"
    rank = _LEVEL_RANK[lvl]

    if rank == 0:  # L0 read-only
        ro = is_read_only(name, argv)
        return {"allow": ro, "needs_confirmation": False, "level": "L0",
                "reason": ("read-only action permitted at L0" if ro
                           else "L0 is read-only; this action may cause a side effect"),
                "verb": cls["verb"], "blast_class": cls["blast_class"]}

    if cls["reversible"]:  # L1/L2/L3: reversible always runs
        return {"allow": True, "needs_confirmation": False, "level": lvl,
                "reason": "reversible action", "verb": None, "blast_class": None}

    if rank == 1:  # L1 ask
        return {"allow": True, "needs_confirmation": True, "level": "L1",
                "reason": f"L1: irreversible ({cls['blast_class']}) needs approval",
                "verb": cls["verb"], "blast_class": cls["blast_class"]}

    if rank == 2:  # L2 bounded
        if _in_scope(name, argv, set(scopes or []), cls["verb"]):
            return {"allow": True, "needs_confirmation": False, "level": "L2",
                    "reason": "L2: irreversible action within authorized scope",
                    "verb": cls["verb"], "blast_class": cls["blast_class"]}
        return {"allow": True, "needs_confirmation": True, "level": "L2",
                "reason": "L2: irreversible action outside scope needs approval",
                "verb": cls["verb"], "blast_class": cls["blast_class"]}

    # L3 full - irreversible allowed, still classified for the record.
    return {"allow": True, "needs_confirmation": False, "level": "L3",
            "reason": "L3: full autonomy (irreversible action logged)",
            "verb": cls["verb"], "blast_class": cls["blast_class"]}


def max_level_for_role(role: str | None) -> str | None:
    """The maximum autonomy level a role may run/grant. ``None`` = no AAT access."""
    return _ROLE_MAX.get(str(role or "").strip().lower())


def clamp(requested: str, role: str | None = None, ws_cap: str | None = None) -> str | None:
    """Effective level = min(requested, role-max, workspace-cap). A caller may always
    choose LOWER than their max. Returns ``None`` iff the role has no AAT access.
    ``role``/``ws_cap`` unset = not clamped (local single-user), so default is unchanged."""
    levels = [requested if requested in _LEVEL_RANK else "L1"]
    if role is not None:
        role_max = max_level_for_role(role)
        if role_max is None:
            return None
        levels.append(role_max)
    if ws_cap in _LEVEL_RANK:
        levels.append(ws_cap)
    return min(levels, key=lambda lvl: _LEVEL_RANK[lvl])
