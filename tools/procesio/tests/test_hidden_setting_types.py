"""Hidden setting types (`ignore`, `auto`): the designer saves their template value and binds
no variable, so the builder must seed them the same way and never confuse one slot for another."""
from __future__ import annotations

from tools.procesio.dto.process import builder

STARTED = "d2831844-54a5-42e7-a101-119e21a03fe2"
CHILD_ID = "d2831844-54a5-42e7-a101-119e21a03fe3"
NULL = builder.NULL_GUID


def _template(settings):
    return {"configuration": [{"settings": settings}]}


def test_an_auto_setting_is_seeded_like_an_ignore_setting():
    tpl = _template([
        {"id": "s-ignore", "type": "ignore", "direction": 2, "value": "-1"},
        {"id": "s-auto", "type": "auto", "direction": 2, "value": NULL},
        {"id": "s-text", "type": "text", "direction": 1, "value": "x"},
    ])
    params = builder._ensure_engine_state_properties(tpl, [])
    assert {p["TabPropertyId"] for p in params} == {"s-ignore", "s-auto"}
    assert all(p["Variable"] == [] for p in params)


def test_an_auto_setting_counts_as_a_template_default_output():
    assert builder._is_template_default_output({"type": "auto", "direction": 1, "value": NULL})


def test_the_started_flow_slot_is_found_by_id_not_by_position():
    # A child-instance-id slot listed BEFORE the started-flow slot must not be taken for it.
    tpl = _template([
        {"id": CHILD_ID, "type": "ignore", "direction": 2, "value": NULL},
        {"id": STARTED, "type": "ignore", "direction": 2, "value": NULL},
        {"id": "flow", "type": "flow-list", "direction": 1, "value": None},
    ])
    out = builder._build_subprocess(tpl, {"target": "T"}, {}, {}, [0])
    assert out[0]["TabPropertyId"] == STARTED
