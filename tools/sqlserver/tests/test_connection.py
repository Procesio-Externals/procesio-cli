"""ODBC driver selection for the `sqlserver` tool.

Needs no live DB and no ODBC driver: `installed_drivers` is the seam, so every
machine layout can be simulated.
"""
from __future__ import annotations

from tools.sqlserver import connection


# --------------------------------------------------------------------------
# Driver selection: pick what is installed, not a fixed name.
#
# The default was hardcoded to "ODBC Driver 18 for SQL Server". On a machine
# carrying only Driver 17 - which includes the box these tests run on - every
# profile created without an explicit --driver failed at CONNECT time with a
# driver error, which reads like a credential problem and sends you hunting in
# the wrong place.
# --------------------------------------------------------------------------


def test_picks_17_when_18_is_absent(monkeypatch):
    monkeypatch.setattr(connection, "installed_drivers",
                        lambda: ["SQL Server", "ODBC Driver 17 for SQL Server"])
    assert connection.best_available_driver() == "ODBC Driver 17 for SQL Server"


def test_prefers_the_newest_installed(monkeypatch):
    monkeypatch.setattr(connection, "installed_drivers", lambda: [
        "ODBC Driver 17 for SQL Server", "ODBC Driver 18 for SQL Server",
        "SQL Server Native Client 11.0",
    ])
    assert connection.best_available_driver() == "ODBC Driver 18 for SQL Server"


def test_a_driver_newer_than_this_list_still_wins(monkeypatch):
    """The preference tuple must not cap the machine at what it knew in 2026."""
    monkeypatch.setattr(connection, "installed_drivers",
                        lambda: ["ODBC Driver 19 for SQL Server"])
    assert connection.best_available_driver() == "ODBC Driver 19 for SQL Server"


def test_falls_back_to_a_real_name_when_nothing_is_enumerable(monkeypatch):
    """Better a driver the user can go install than an empty Driver={}."""
    monkeypatch.setattr(connection, "installed_drivers", lambda: [])
    assert connection.best_available_driver() == connection.DEFAULT_DRIVER


def test_installed_drivers_never_raises_without_pyodbc(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_pyodbc(name, *a, **k):
        if name == "pyodbc":
            raise ImportError("not installed")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", no_pyodbc)
    assert connection.installed_drivers() == []


def test_an_explicit_profile_driver_still_wins(monkeypatch):
    monkeypatch.setattr(connection, "installed_drivers",
                        lambda: ["ODBC Driver 18 for SQL Server"])
    dsn = connection.build_dsn(
        {"server": "s", "driver": "ODBC Driver 17 for SQL Server"}, password=None)
    assert "Driver={ODBC Driver 17 for SQL Server}" in dsn


def test_a_profile_without_a_driver_uses_what_is_installed(monkeypatch):
    monkeypatch.setattr(connection, "installed_drivers",
                        lambda: ["ODBC Driver 17 for SQL Server"])
    dsn = connection.build_dsn({"server": "s"}, password=None)
    assert "Driver={ODBC Driver 17 for SQL Server}" in dsn
