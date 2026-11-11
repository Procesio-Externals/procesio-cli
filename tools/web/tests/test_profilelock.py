"""One browser per persistent profile: the lock that keeps a second Chromium off
a profile another process has open (two at once wipe the stored login)."""
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from tools.web.driver import PlaywrightDriver
from tools.web.errors import BrowserError
from tools.web.profilelock import ProfileLock, lock_path

ROOT = Path(__file__).resolve().parents[3]


def test_lock_file_sits_beside_the_profile(tmp_path):
    prof = tmp_path / "whatsapp.profile"
    assert lock_path(str(prof)) == str(tmp_path / "whatsapp.profile.aat-lock")
    assert lock_path(str(prof) + "\\") == str(tmp_path / "whatsapp.profile.aat-lock")


def test_second_opener_waits_then_fails_while_first_holds(tmp_path):
    prof = str(tmp_path / "p.profile")
    first = ProfileLock(prof, wait_s=0).acquire()
    try:
        t0 = time.monotonic()
        with pytest.raises(BrowserError, match="in use by another process"):
            ProfileLock(prof, wait_s=0.6).acquire()
        assert time.monotonic() - t0 >= 0.5
    finally:
        first.release()
    ProfileLock(prof, wait_s=0).acquire().release()


def test_release_lets_a_waiting_opener_in(tmp_path):
    prof = str(tmp_path / "p.profile")
    first = ProfileLock(prof, wait_s=0).acquire()
    first.release()
    first.release()  # idempotent
    second = ProfileLock(prof, wait_s=0).acquire()
    second.release()


def test_lock_holds_across_processes(tmp_path):
    prof = str(tmp_path / "p.profile")
    holder = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {str(ROOT)!r})
        from tools.web.profilelock import ProfileLock
        lk = ProfileLock({prof!r}, wait_s=0).acquire()
        print("locked", flush=True)
        time.sleep(30)
    """)
    proc = subprocess.Popen([sys.executable, "-c", holder], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "locked"
        with pytest.raises(BrowserError):
            ProfileLock(prof, wait_s=0.5).acquire()
    finally:
        proc.kill()
        proc.wait()
    # The OS drops the lock with the dead process.
    ProfileLock(prof, wait_s=5).acquire().release()


def test_driver_close_releases_the_profile_lock(tmp_path):
    prof = str(tmp_path / "p.profile")
    d = PlaywrightDriver(user_data_dir=prof)
    d._profile_lock = ProfileLock(prof, wait_s=0).acquire()
    d.close()
    assert d._profile_lock is None
    ProfileLock(prof, wait_s=0).acquire().release()


def test_wait_comes_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("AAT_PROFILE_LOCK_WAIT_S", "7")
    assert ProfileLock(str(tmp_path / "p.profile")).wait_s == 7.0
    monkeypatch.setenv("AAT_PROFILE_LOCK_WAIT_S", "junk")
    assert ProfileLock(str(tmp_path / "p.profile")).wait_s == 180.0


def test_headed_marker_forces_offscreen_headed_for_that_profile(tmp_path):
    prof = tmp_path / "w.profile"
    assert PlaywrightDriver(user_data_dir=str(prof))._headless is True
    (tmp_path / "w.profile.headed").write_text("")
    d = PlaywrightDriver(user_data_dir=str(prof))
    assert d._headless is False
    assert "--window-position=-32000,-32000" in d._extra_args
    # Other profiles and non-profile sessions are untouched.
    assert PlaywrightDriver(user_data_dir=str(tmp_path / "other.profile"))._headless is True
    assert PlaywrightDriver()._headless is True
