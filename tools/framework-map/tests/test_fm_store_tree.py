"""The user-data tree in the map must list what the resolvers actually create.

fm_builder._store_tree used to read the REAL folders off the local disk so a new
subfolder could never be omitted. That made a VERSIONED artifact depend on whose
machine built it. The list is canonical now, so this test carries the guarantee
the disk read used to: create a user-data root through tools/_lib/userdata and
assert the canonical list matches the directories that appear.

Add a resolver to userdata (or a folder to _CANON_FOLDERS) and this test tells
you the other half is missing, at build time rather than in someone's diff.
"""
from __future__ import annotations

import pytest

import fm_builder
import fm_strings

from tools._lib import userdata


def _make_every_userdata_dir(component: str = "probe") -> None:
    """Call every directory resolver userdata exposes, so each folder is created."""
    userdata.state_dir(component)
    userdata.config_dir(component)
    userdata.prompts_dir(component)
    userdata.sessions_dir()
    userdata.exports_dir()
    userdata.schedule_dir()
    userdata.store_db_path()          # parent only; the file itself is not created


def test_canonical_folders_match_what_userdata_creates(tmp_path, monkeypatch):
    monkeypatch.setenv("AAT_USERDATA_DIR", str(tmp_path / "ud"))
    monkeypatch.delenv("AAT_USER_ID", raising=False)
    monkeypatch.delenv("AAT_WORKSPACE_ID", raising=False)

    _make_every_userdata_dir()

    live = {p.name for p in userdata.base().iterdir() if p.is_dir()}
    assert live == set(fm_builder._CANON_FOLDERS), (
        "fm_builder._CANON_FOLDERS is out of step with tools/_lib/userdata: "
        f"only on disk={sorted(live - set(fm_builder._CANON_FOLDERS))}, "
        f"only in the list={sorted(set(fm_builder._CANON_FOLDERS) - live)}")


# The store panel is part of the architecture narrative, which not every
# distribution of the framework ships. Where its copy is absent there is nothing
# to assert about it, so these skip rather than fail.
requires_store_copy = pytest.mark.skipif(
    "sc1_h" not in fm_strings.S["en"],
    reason="this distribution does not ship the store panel copy")

@requires_store_copy
def test_every_canonical_folder_is_described_in_both_languages():
    """A folder with no description renders as a bare name with a blank column."""
    for lang in ("en", "ro"):
        S = fm_builder.fm_strings.S[lang]
        described = ({"config": S["tc_config"], "sessions": S["tc_sessions"],
                      "schedule": S["tc_schedule"]} | fm_builder._FOLDER_EXTRA[lang])
        missing = [f for f in fm_builder._CANON_FOLDERS if not described.get(f)]
        assert not missing, f"{lang}: folders with no description: {missing}"


@requires_store_copy
def test_store_tree_is_independent_of_the_local_user_data_folder(tmp_path, monkeypatch):
    """The whole point: same bytes on a machine with user data and on a clean one."""
    monkeypatch.setenv("AAT_USERDATA_DIR", str(tmp_path / "empty"))
    clean = fm_builder._store_tree("en")

    populated_root = tmp_path / "populated"
    monkeypatch.setenv("AAT_USERDATA_DIR", str(populated_root))
    _make_every_userdata_dir()
    (populated_root / "a-folder-someone-added-locally").mkdir()
    assert fm_builder._store_tree("en") == clean
