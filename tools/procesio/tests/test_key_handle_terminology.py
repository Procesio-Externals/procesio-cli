"""Regression coverage for PROCESIO's API-key field terminology."""
from __future__ import annotations

from tools.procesio import main, profiles
from tools.procesio.handlers import profile_admin


class _TTY:
    @staticmethod
    def isatty() -> bool:
        return True


def test_add_credential_prompts_for_key_handle_then_value(store, monkeypatch):
    prompts: list[str] = []
    answers = iter(("alpha-entry", "omega-entry"))

    monkeypatch.setattr(profile_admin.sys, "stdin", _TTY())

    def fake_getpass(prompt: str) -> str:
        prompts.append(prompt)
        return next(answers)

    monkeypatch.setattr(profile_admin.getpass, "getpass", fake_getpass)

    out = main.dispatch(
        "add-credential",
        [
            "--name", "workspace-key",
            "--type", "apikey",
            "--workspace-id", "workspace-id",
        ],
    )

    assert prompts == [
        "PROCESIO Key Handle: ",
        "PROCESIO API key value (shown once): ",
    ]
    stored = profiles.get_profile("workspace-key")
    assert stored["key"] == "alpha-entry"
    assert stored["value"] == "omega-entry"
    assert out["profile"]["has_key"] is True
    assert out["profile"]["has_value"] is True
    assert "alpha-entry" not in str(out)
    assert "omega-entry" not in str(out)
