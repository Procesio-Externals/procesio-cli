"""The writer lock of a live process: one read-change-save at a time.

Two writers that run together both read the same version of the process, and the second
save discards the first change while both report success.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.procesio import errors
from tools.procesio.handlers import editlock


REPO = Path(__file__).resolve().parents[3]

# A writer in a process of its own: it takes the lock, says so, and holds it until it is told
# to go on. What it is given as a temp folder and as a lock folder is its environment's.
WRITER = """
import sys
from tools.procesio.handlers import editlock
with editlock.process_lock(sys.argv[1], wait=0) as held:
    print("held" if held else "not held", flush=True)
    sys.stdin.readline()
"""


@pytest.fixture(autouse=True)
def own_folder(monkeypatch, tmp_path):
    monkeypatch.setattr(editlock.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.delenv(editlock.LOCK_DIR_ENV, raising=False)


@pytest.fixture
def other_writer(tmp_path):
    """Start a writer in another process with a temp folder of its OWN, as a server that
    isolates tool calls gives each call. Returns a function (process id, lock folder or None)."""
    started = []

    def start(process_id, lock_folder):
        temp = tmp_path / f"temp-of-writer-{len(started)}"
        temp.mkdir()
        env = {k: v for k, v in os.environ.items() if k != editlock.LOCK_DIR_ENV}
        env.update(TMPDIR=str(temp), TEMP=str(temp), TMP=str(temp), PYTHONPATH=str(REPO))
        if lock_folder is not None:
            env[editlock.LOCK_DIR_ENV] = str(lock_folder)
        writer = subprocess.Popen([sys.executable, "-c", WRITER, process_id], cwd=str(REPO), env=env,
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        started.append(writer)
        assert writer.stdout.readline().strip() == "held"
        return writer, temp

    yield start
    for writer in started:
        if writer.poll() is None:
            writer.stdin.write("\n")
            writer.stdin.flush()
            writer.wait(10)


def test_the_lock_exists_while_the_body_runs_and_is_gone_after():
    path = editlock.lock_path("p1")
    with editlock.process_lock("p1") as held:
        assert held is True and path.exists()
    assert not path.exists()


def test_the_lock_is_released_when_the_body_raises():
    with pytest.raises(RuntimeError):
        with editlock.process_lock("p1"):
            raise RuntimeError("the edit failed")
    assert not editlock.lock_path("p1").exists()


def test_a_second_writer_waits_for_the_first_to_finish():
    order = []
    first_inside = threading.Event()

    def first():
        with editlock.process_lock("p1"):
            first_inside.set()
            time.sleep(0.2)
            order.append("first done")

    def second():
        first_inside.wait(5)
        with editlock.process_lock("p1", poll=0.01):
            order.append("second in")

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert order == ["first done", "second in"]


def test_writers_of_different_processes_do_not_wait_for_each_other():
    with editlock.process_lock("p1"):
        with editlock.process_lock("p2", wait=0) as held:
            assert held is True


def test_a_writer_that_waits_too_long_is_told_the_process_is_busy():
    with editlock.process_lock("p1"):
        with pytest.raises(errors.ProcessBusy) as err:
            with editlock.process_lock("p1", wait=0.05, poll=0.01):
                pass
    assert "repeat it" in str(err.value)
    assert errors.classify(err.value)[0] == "process_busy"
    assert errors.classify(err.value)[3] == 1


def test_a_lock_left_by_a_stopped_writer_is_taken_over():
    path = editlock.lock_path("p1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("999999")
    old = time.time() - editlock.STALE_SECONDS - 5
    os.utime(path, (old, old))
    with editlock.process_lock("p1", wait=0) as held:
        assert held is True


def test_a_fresh_lock_is_not_taken_over():
    path = editlock.lock_path("p1")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("1")
    with pytest.raises(errors.ProcessBusy):
        with editlock.process_lock("p1", wait=0):
            pass
    assert path.exists()      # the other writer's lock is left alone


def test_an_edit_still_runs_when_the_lock_folder_cannot_be_made(monkeypatch, tmp_path):
    """Nothing here may stop an edit that could have run."""
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    monkeypatch.setattr(editlock, "lock_path", lambda pid: blocker / "sub" / "p.lock")
    with editlock.process_lock("p1") as held:
        assert held is False


# --- two writers that do not share a temp folder -------------------------------------------
#
# A server that isolates tool calls gives each call its own temp folder. A lock kept in the
# temp folder is then a file that only its own writer can see.

def test_two_writers_with_different_temp_folders_exclude_each_other_through_the_shared_folder(
        other_writer, monkeypatch, tmp_path):
    shared = tmp_path / "shared-locks"
    writer, its_temp = other_writer("p1", shared)
    monkeypatch.setenv(editlock.LOCK_DIR_ENV, str(shared))   # this writer's temp folder is tmp_path

    assert editlock.lock_path("p1").parent == shared / editlock.FOLDER
    assert editlock.lock_path("p1").exists()                  # the other writer's lock, seen from here
    assert not (its_temp / editlock.FOLDER).exists() and not (tmp_path / editlock.FOLDER).exists()
    with pytest.raises(errors.ProcessBusy):
        with editlock.process_lock("p1", wait=0.2, poll=0.02):
            pass

    writer.stdin.write("\n")
    writer.stdin.flush()
    writer.wait(10)
    with editlock.process_lock("p1", wait=2, poll=0.02) as held:
        assert held is True


def test_without_the_shared_folder_two_temp_folders_are_two_locks(other_writer, tmp_path):
    """Why the setting exists: both writers hold "the" lock of the same process at once."""
    _, its_temp = other_writer("p1", None)

    with editlock.process_lock("p1", wait=0) as held:
        assert held is True
        assert (its_temp / editlock.FOLDER).is_dir() and (tmp_path / editlock.FOLDER).is_dir()


def test_the_shared_folder_is_made_by_the_first_writer_that_needs_it(monkeypatch, tmp_path):
    monkeypatch.setenv(editlock.LOCK_DIR_ENV, str(tmp_path / "not" / "there" / "yet"))
    with editlock.process_lock("p1") as held:
        assert held is True and editlock.lock_path("p1").exists()


def test_the_lock_folder_is_read_at_every_call(monkeypatch, tmp_path):
    """One process can serve calls that were given different environments."""
    assert editlock.lock_root() == tmp_path
    monkeypatch.setenv(editlock.LOCK_DIR_ENV, str(tmp_path / "a"))
    assert editlock.lock_root() == tmp_path / "a"
    monkeypatch.setenv(editlock.LOCK_DIR_ENV, "   ")
    assert editlock.lock_root() == tmp_path


def test_one_process_has_one_lock_however_its_id_is_written():
    assert editlock.lock_path("ABC-1 ") == editlock.lock_path("abc-1")
    assert editlock.lock_path("abc-1") != editlock.lock_path("abc-2")


def test_an_id_cannot_name_a_file_outside_the_lock_folder(tmp_path):
    path = editlock.lock_path("../../etc/passwd")
    assert path.parent == tmp_path / editlock.FOLDER
    assert "/" not in path.name and ".." not in path.name


def test_a_serialized_handler_holds_the_lock_of_its_process():
    seen = {}

    def handler(client, args):
        seen["locked"] = editlock.lock_path(args.id).exists()
        return {"ok": True}

    run = editlock.serialized(handler)
    assert run(None, SimpleNamespace(id="p1")) == {"ok": True}
    assert seen["locked"] is True and not editlock.lock_path("p1").exists()
    assert run.__wrapped__ is handler


def test_an_edit_that_ran_without_the_lock_says_so_in_its_result(monkeypatch, tmp_path):
    blocker = tmp_path / "a-file"
    blocker.write_text("x")
    run = editlock.serialized(lambda client, args: {"put": True})

    assert "unserialized" not in run(None, SimpleNamespace(id="p1"))
    monkeypatch.setenv(editlock.LOCK_DIR_ENV, str(blocker))      # a file where the folder should be
    result = run(None, SimpleNamespace(id="p1"))
    assert result["put"] is True
    assert editlock.LOCK_DIR_ENV in result["unserialized"] and "overwrite" in result["unserialized"]


def test_a_serialized_handler_without_an_id_runs_as_it_is():
    run = editlock.serialized(lambda client, args: "ran")
    assert run(None, SimpleNamespace(id=None)) == "ran"
    assert run(None, SimpleNamespace()) == "ran"
