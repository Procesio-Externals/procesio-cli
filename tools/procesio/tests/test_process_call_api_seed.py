"""Process builder: Call API run-time-mandatory properties are seeded (verb guid + empty Request Parameters)."""
from __future__ import annotations

import itertools

from tools.procesio.dto.process import builder as pb


def _ctx():
    counter = itertools.count(1)
    return {"new_id": lambda: f"00000000-0000-0000-0000-{next(counter):012d}"}


def _call_api_params(verb="GET", with_req=False):
    params = {"Verb": verb, "Endpoint": "/zen", "Time Out": 30}
    if with_req:
        params["Request Parameters"] = {"body": {"type": "RAW", "value": {"BINARY": "", "FORM_DATA": [],
                                                                            "RAW": {"format": "json", "value": "{}"},
                                                                            "X_WWW_FORM_URLENCODED": []}},
                                        "headers": [], "queryParams": []}
    cfg = {"title": "t", "actions": [{"id": "c", "action": "Call API", "name": "c", "params": params}]}
    dto = pb.build(cfg, _ctx())
    node = [a for a in dto["Actions"] if a["ActionName"] == "c"][0]
    return {str(p["TabPropertyId"])[-12:]: p for p in node["Parameters"]}


def test_verb_word_resolves_to_platform_guid():
    for word, guid in pb._CALL_API_VERB_GUIDS.items():
        assert _call_api_params(word)["8420f7790001"]["Value"] == guid
    assert _call_api_params("post")["8420f7790001"]["Value"] == pb._CALL_API_VERB_GUIDS["POST"]


def test_verb_guid_passes_through():
    guid = pb._CALL_API_VERB_GUIDS["DELETE"]
    assert _call_api_params(guid)["8420f7790001"]["Value"] == guid


def test_missing_request_parameters_is_seeded_empty():
    p = _call_api_params()["8420f7790003"]
    assert p["Variable"] == []
    assert p["Value"]["body"]["type"] == "RAW" and p["Value"]["headers"] == [] and p["Value"]["queryParams"] == []


def test_bound_request_parameters_are_kept():
    p = _call_api_params(with_req=True)["8420f7790003"]
    assert p["Value"]["body"]["value"]["RAW"]["value"] == "{}"
