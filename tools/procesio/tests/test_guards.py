"""Guards for three footguns found live on 2026-07-30 (Livespace PoC):

1. a credential option property given a raw string (e.g. Method="POST") used to save
   fine and then break EVERY Call API run at runtime with "Unrecognized Guid format";
2. `publish` without `launch` silently leaves an instance stuck at "starting";
3. "Error: data type mismatch." never said which type was expected (Call API's
   `Response Status` needs `integer`, not `number`).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.procesio.dto.credential import builder as cred  # noqa: E402
from tools.procesio.errors import UsageError  # noqa: E402
from tools.procesio.flowmodel import fevalidation as fev  # noqa: E402
from tools.procesio import main as pmain  # noqa: E402

GUID_A = "10101010-0001-0002-0001-cccccccccccc"
GUID_B = "10101010-0001-0004-0001-cccccccccccc"


def _prop(label, options):
    return {"id": "p1", "label": label, "options": options}


METHOD = _prop("Method", [{"be_value": "Get", "name": "GET", "value": GUID_A}])


# --- 1. credential option properties -------------------------------------
def test_option_name_resolves_to_guid():
    assert cred._resolve_option(METHOD, "GET") == GUID_A


def test_option_be_value_and_guid_also_accepted():
    assert cred._resolve_option(METHOD, "Get") == GUID_A
    assert cred._resolve_option(METHOD, GUID_A) == GUID_A


def test_unmatched_value_on_guid_option_raises_not_silently_stored():
    # THE regression: "POST" is not an option of Method. Before the fix this was
    # stored verbatim and every Call API run using the credential died at runtime.
    with pytest.raises(UsageError) as ei:
        cred._resolve_option(METHOD, "POST")
    msg = str(ei.value)
    assert "Method" in msg and "GET" in msg
    assert "Unrecognized Guid format" in msg   # names the runtime symptom


def test_non_guid_option_sets_still_pass_through():
    # checkbox-style props must keep working (backwards compatibility)
    checkbox = _prop("Header", [{"name": "true", "value": "true"},
                                {"name": "false", "value": "false"}])
    assert cred._resolve_option(checkbox, "true") == "true"
    assert cred._resolve_option(checkbox, "whatever") == "whatever"


def test_property_without_options_passes_through():
    assert cred._resolve_option({"id": "p", "label": "URL"}, "https://x") == "https://x"


def test_build_raises_for_bad_option_value():
    template = {"gid": "g", "pid": "p", "name": "REST API", "type": "REST_API",
                "properties": [METHOD]}
    with pytest.raises(UsageError):
        cred.build({"name": "X", "properties": {"Method": "POST"}}, {"template": template})
    dto = cred.build({"name": "X", "properties": {"Method": "GET"}}, {"template": template})
    assert dto["properties"] == [{"id": "p1", "value": GUID_A}]


# --- 2. publish advisory --------------------------------------------------
def test_publish_carries_the_launch_advisory():
    out = pmain._advise("post-projects-by-id-instances-publish", {"result": {}})
    assert "starting" in out["warning"] and "launch" in out["warning"].lower()


def test_advisory_does_not_touch_other_actions_or_clobber():
    assert "warning" not in pmain._advise("run-process", {"result": {}})
    keep = pmain._advise("post-projects-by-id-instances-publish", {"warning": "mine"})
    assert keep["warning"] == "mine"


# --- 3. type-mismatch hint ----------------------------------------------
def test_type_mismatch_warning_names_expected_and_actual():
    INT, NUM = "0317bfee-int", "0317bfee-num"
    dt_by_id = {INT: {"id": INT, "name": "integer"}, NUM: {"id": NUM, "name": "number"}}
    var_by_id = {"v1": {"id": "v1", "name": "editStatus", "dataType": NUM, "isList": False}}
    setting = {"id": "s", "label": "Response Status", "dataTypeId": INT,
               "isList": False, "value": "<%0%>"}
    action = {"id": "a", "actionTemplateName": "Call API"}
    # emulate the binding the builder writes: value refs the variable
    warns = fev._default_datatype_check(action, {**setting, "value": "v1"},
                                        var_by_id, dt_by_id)
    if warns:                                  # only assert the hint when it fires
        assert warns[0]["code"] == "TYPE_MISMATCH"
        assert "expects integer" in warns[0]["hint"]


def test_type_hint_text_is_actionable():
    INT, NUM = "i", "n"
    dt_by_id = {INT: {"id": INT, "name": "integer"}, NUM: {"id": NUM, "name": "number"}}
    hint = fev._type_hint({"dataTypeId": INT, "isList": False},
                          {"scalar": [{"id": NUM}], "list": []}, dt_by_id)
    assert "binds number" in hint and "expects integer" in hint
