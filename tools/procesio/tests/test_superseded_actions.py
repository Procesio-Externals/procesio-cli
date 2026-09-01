"""The process builder must BLOCK frozen/superseded action version pins (e.g.
"Call API v3") and point at the live/latest action, unless --force pins one
intentionally. Guards against silently building on an old action generation.
"""
from __future__ import annotations

import itertools

import pytest

from tools.procesio.dto.process import builder as pb
from tools.procesio.errors import UsageError


def _ctx(force: bool = False):
    counter = itertools.count(1)
    ctx = {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}"}
    if force:
        ctx["_force"] = True
    return ctx


def _cfg(action: str):
    return {"title": "t", "variables": [{"name": "q", "type": "string"}],
            "actions": [{"id": "c", "action": action,
                         "params": {"Verb": "3ab385bd-f8ae-b641-9176-e7db886aec01"}}]}


@pytest.mark.parametrize("action", ["Call API v1", "Call API v2", "Call API v3"])
def test_superseded_call_api_is_blocked(action):
    with pytest.raises(UsageError, match="superseded"):
        pb.build(_cfg(action), _ctx())


def test_block_message_names_the_latest_action():
    with pytest.raises(UsageError, match=r"Call API"):
        pb.build(_cfg("Call API v3"), _ctx())


def test_force_allows_pinning_the_old_version():
    # --force (ctx["_force"]) is the escape hatch for an intentional pin.
    dto = pb.build(_cfg("Call API v3"), _ctx(force=True))
    assert dto["Actions"], "forced build should proceed past the superseded guard"


def test_latest_call_api_builds_cleanly():
    dto = pb.build(_cfg("Call API"), _ctx())
    assert any((a.get("ActionTemplateName") or "").strip() == "Call API" for a in dto["Actions"])


def test_execute_query_v2_is_blocked():
    # Guard fires before catalog resolution, so it applies even to versioned SQL pins.
    with pytest.raises(UsageError, match="Execute Query"):
        pb.build({"title": "t", "actions": [{"id": "e", "action": "Execute Query V2"}]}, _ctx())
