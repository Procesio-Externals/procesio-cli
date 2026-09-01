"""Session path resolution, name validation (no traversal), and the
read/write/list/delete lifecycle - all against an isolated temp dir."""
from __future__ import annotations

import json

import pytest

from tools.web import sessions
from tools.web.errors import SessionError, UsageError


@pytest.mark.parametrize("bad", [
    "../escape", "a/b", "a\\b", "", ".hidden", "with space",
    "x" * 65, "/abs", "..",
])
def test_invalid_names_rejected(bad):
    with pytest.raises(UsageError):
        sessions.validate_name(bad)


@pytest.mark.parametrize("good", ["linkedin", "whats-app", "site_1", "a", "A.B-c_2"])
def test_valid_names_accepted(good):
    assert sessions.validate_name(good) == good


def test_session_path_is_inside_sessions_dir(isolated_sessions):
    p = sessions.session_path("linkedin")
    assert p.parent == isolated_sessions
    assert p.name == "linkedin.json"


def test_write_load_roundtrip(isolated_sessions):
    state = {"cookies": [{"name": "sid", "value": "v"}], "origins": []}
    sessions.write_state("acme", state)
    assert sessions.exists("acme")
    assert sessions.load_state("acme") == state


def test_require_missing_raises_session_error(isolated_sessions):
    with pytest.raises(SessionError):
        sessions.require("ghost")


def test_load_corrupt_raises_session_error(isolated_sessions):
    p = sessions.session_path("broken")
    p.write_text("{ not json", encoding="utf-8")
    with pytest.raises(SessionError):
        sessions.load_state("broken")


def test_delete_reports_removed_then_missing(isolated_sessions):
    sessions.write_state("temp", {"cookies": []})
    out = sessions.delete("temp", confirm=True)
    assert out["deleted"] is True and out["removed"] == ["state"]
    again = sessions.delete("temp", confirm=True)
    assert again["deleted"] is False and again["existed"] is False


def _seed_persistent(name):
    """A persistent session as save-session leaves it: profile dir + sidecar."""
    sessions.write_state(name, {"cookies": []})
    prof = sessions.profile_dir(name)
    (prof / "Default").mkdir(parents=True)
    (prof / "Default" / "Cookies").write_text("x", encoding="utf-8")
    sessions.write_cookies(name, [{"name": "sid", "value": "abc"}])
    return prof


def test_delete_removes_profile_and_cookie_sidecar(isolated_sessions):
    """The live bug: delete only unlinked <name>.json, leaving a stale profile
    that open_session then silently reused."""
    prof = _seed_persistent("goog")
    out = sessions.delete("goog", confirm=True)
    assert out["deleted"] is True
    assert sorted(out["removed"]) == ["cookies", "profile", "state"]
    assert not prof.exists()
    assert not sessions.cookies_exist("goog")
    assert not sessions.exists("goog")
    assert sessions.present_artifacts("goog") == []


def test_delete_without_confirm_previews_and_removes_nothing(isolated_sessions):
    """Deleting a session destroys a login only a human can re-establish, so an
    unconfirmed call must be a pure preview."""
    prof = _seed_persistent("goog")
    out = sessions.delete("goog")
    assert out["deleted"] is False
    assert out["confirmation_required"] is True
    assert sorted(out["would_remove"]) == ["cookies", "profile", "state"]
    assert out["removed"] == []
    # nothing touched
    assert prof.exists() and sessions.cookies_exist("goog") and sessions.exists("goog")


def test_delete_missing_session_needs_no_confirmation(isolated_sessions):
    out = sessions.delete("nope")
    assert out["existed"] is False and out["deleted"] is False
    assert "confirmation_required" not in out


def test_delete_reports_artifacts_it_could_not_remove(isolated_sessions, monkeypatch):
    """A locked profile (browser still open) must be reported, not silently
    counted as deleted."""
    _seed_persistent("goog")

    def boom(path):
        raise OSError("profile is in use")
    monkeypatch.setattr(sessions.shutil, "rmtree", boom)

    out = sessions.delete("goog", confirm=True)
    assert out["deleted"] is False              # not a success
    assert "profile" in out["failed"]
    assert sessions.profile_exists("goog")      # still there
    assert sorted(out["removed"]) == ["cookies", "state"]


def test_list_all_metadata_only(isolated_sessions):
    sessions.write_state("one", {"cookies": []})
    sessions.write_state("two", {"cookies": [{"name": "x", "value": "y"}]})
    items = sessions.list_all()
    names = [i["name"] for i in items]
    assert names == ["one", "two"]  # sorted
    for i in items:
        assert set(i) == {"name", "bytes", "modified", "persistent"}  # no contents leaked
        assert i["bytes"] > 0
        assert i["persistent"] is False


def test_list_all_includes_persistent_profiles(isolated_sessions):
    sessions.write_state("jsonsess", {"cookies": []})
    prof = sessions.profile_dir("profsess")
    prof.mkdir()
    (prof / "Default").write_text("x", encoding="utf-8")  # make it non-empty
    items = {i["name"]: i for i in sessions.list_all()}
    assert items["jsonsess"]["persistent"] is False
    assert items["profsess"]["persistent"] is True


def test_list_all_does_not_read_contents(isolated_sessions):
    # Even a file with secret-looking content only surfaces metadata.
    secret = {"cookies": [{"name": "auth", "value": "SUPERSECRET"}]}
    sessions.write_state("s", secret)
    dumped = json.dumps(sessions.list_all())
    assert "SUPERSECRET" not in dumped
