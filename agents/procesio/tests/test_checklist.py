from __future__ import annotations

from agents.procesio import checklist as cl


def test_all_steps_have_required_keys():
    keys = {"id", "phase", "title", "how", "tool", "automatable", "citation"}
    for s in cl.STEPS:
        assert keys <= set(s), f"{s.get('id')} missing {keys - set(s)}"
        assert s["phase"] in cl.PHASES


def test_phase_filter():
    val = cl.steps(phase="validate")
    assert val and all(s["phase"] == "validate" for s in val)


def test_automatable_only_is_subset():
    auto = cl.steps(automatable_only=True)
    assert auto and all(s["automatable"] for s in auto)
    assert len(auto) < len(cl.STEPS)  # there are genuine manual steps too


def test_manual_steps_are_the_non_automatable_ones():
    manual = cl.manual_steps()
    assert manual and all(not s["automatable"] for s in manual)
    # the real-browser form check must be in the manual set - it cannot be automated
    assert "form-behavior" in {s["id"] for s in manual}
