from __future__ import annotations

from pathlib import Path

import pytest

from agents.procesio import knowledge


def test_topics_present():
    assert set(knowledge.topics()) == {
        "playbook", "best-practices", "visual-organization", "datastore",
        "scheduling", "environments", "reliability", "boundary"}


def test_each_topic_loads_real_content():
    for t in knowledge.topics():
        doc = knowledge.load(t)
        assert doc["content"].strip(), f"{t} empty"
        assert Path(doc["source"]).exists()
        assert doc["topic"] == t


def test_load_all_returns_every_topic():
    assert {d["topic"] for d in knowledge.load_all()} == set(knowledge.topics())


def test_unknown_topic_raises():
    with pytest.raises(KeyError):
        knowledge.load("nope")
