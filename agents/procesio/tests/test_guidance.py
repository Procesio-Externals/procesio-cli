from __future__ import annotations

from pathlib import Path

import pytest

from agents.procesio import knowledge


def test_topics_present():
    assert set(knowledge.topics()) == {
        "playbook", "best-practices", "visual-organization", "datastore",
        "scheduling", "environments", "reliability", "boundary",
        "forms", "forms-anatomy", "forms-code", "forms-dom", "forms-interaction",
        "forms-motion", "forms-process", "forms-deploy", "forms-pitfalls"}


def test_each_topic_loads_real_content():
    for t in knowledge.topics():
        doc = knowledge.load(t)
        assert doc["content"].strip(), f"{t} empty"
        assert Path(doc["source"]).exists()
        assert doc["topic"] == t


def test_all_excludes_the_form_chapters_but_keeps_their_index():
    """`topic=all` is a payload a run carries forward under a character budget. The
    form guide is ~100 KB across nine files; folding it in would evict the process
    guidance most callers asked for. The index is small and advertises the rest."""
    served = {d["topic"] for d in knowledge.load_all()}
    assert "forms" in served
    assert not [t for t in served if t.startswith("forms-")]
    assert sum(len(d["content"]) for d in knowledge.load_all()) < 100_000


def test_the_form_chapters_are_reachable_one_at_a_time():
    for t in ("forms-anatomy", "forms-process", "forms-pitfalls"):
        assert knowledge.load(t)["content"].strip()


def test_the_form_index_names_the_chapters_a_caller_must_ask_for():
    """The index is the only form topic in `all`, so it has to be the map: a caller
    that lands there must learn the sub-topics exist without a second guess."""
    body = knowledge.load("forms")["content"]
    for chapter in ("ANATOMY", "PROCESS-INTEGRATION", "PITFALLS"):
        assert chapter in body


def test_the_process_integration_chapter_carries_the_map_row_contract():
    """This is the fact the gap actually cost: a RUN_PROCESS map row's two sides are
    objects with DIFFERENT shapes, and the form side's path is a four-GUID chain, not
    a readable pseudo-path. If this ever stops being served, the guide is not doing
    the one job it was registered for."""
    body = knowledge.load("forms-process")["content"]
    assert "inputMap" in body and "outputMap" in body
    assert "11223344-5566-7788-99aa-aabbccddeeff" in body       # the FIELDS_NS constant
    assert "isList" in body                                      # the row object shape


def test_unknown_topic_raises():
    with pytest.raises(KeyError):
        knowledge.load("nope")
