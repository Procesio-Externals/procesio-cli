"""Named connection-profile store shared by the `sqlserver` and `mysql` tools.

Split storage, by design (see CLAUDE.md Hard rule 1 — no secrets in files):

  * NON-SECRET config (profile name, server/host, port, database, username,
    driver, TLS flags, timeouts) lives in a ``profiles.json`` file INSIDE the
    tool directory. It never contains a password.
  * The PASSWORD lives ONLY in Windows Credential Manager, under the target
    ``agents-and-tools:<tool>:<profile-name>`` — i.e. the secret name IS the
    profile name. Read at runtime via ``tools._lib.creds.get(tool, profile)``.

So a profile named ``default`` on the ``sqlserver`` tool keeps its host/db/etc.
in ``tools/sqlserver/profiles.json`` and its password under the credential
target ``agents-and-tools:sqlserver:default``. Set it with:

    python scripts/set-credential.py sqlserver default

This module is a thin, dependency-light wrapper (only stdlib + creds). It does
not import any DB driver, so it stays unit-testable and import-safe.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools._lib import creds


class ProfileError(Exception):
    """Bad profile usage (unknown name, duplicate, missing field). -> invalid_argument."""


class AuthRequiredError(Exception):
    """A profile exists but its password is not in Credential Manager. -> auth_required."""


class ProfileStore:
    """Reads/writes the per-tool ``profiles.json`` and resolves passwords.

    Parameters
    ----------
    tool : str
        The tool name (``"sqlserver"`` or ``"mysql"``). Used as the Credential
        Manager namespace AND must match the manifest ``name``.
    path : Path
        Absolute path to this tool's ``profiles.json``.
    """

    def __init__(self, tool: str, path: Path):
        self.tool = tool
        self.path = Path(path)

    # -- raw file I/O -------------------------------------------------------

    def _read(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    # -- CRUD ---------------------------------------------------------------

    def names(self) -> list[str]:
        return sorted(self._read().keys())

    def exists(self, name: str) -> bool:
        return name in self._read()

    def get(self, name: str) -> dict:
        """Return one profile's NON-SECRET config dict (raises if unknown)."""
        data = self._read()
        if name not in data:
            known = ", ".join(sorted(data)) or "(none)"
            raise ProfileError(
                f"no profile named '{name}'. Known: {known}. "
                f"Add one with: run-tool {self.tool} add-profile --name {name} ..."
            )
        blob = dict(data[name])
        blob["name"] = name
        return blob

    def add(self, name: str, config: dict[str, Any], *, overwrite: bool = False) -> dict:
        """Store a NON-SECRET profile config. Strips any password-like field."""
        if not name:
            raise ProfileError("profile --name is required")
        data = self._read()
        if name in data and not overwrite:
            raise ProfileError(
                f"profile '{name}' already exists. Pass --overwrite to replace it."
            )
        clean = {
            k: v for k, v in config.items()
            if v is not None and k not in ("name", "password", "pwd", "pass")
        }
        data[name] = clean
        self._write(data)
        view = dict(clean)
        view["name"] = name
        view["has_password"] = creds.has(self.tool, name)
        return view

    def remove(self, name: str) -> None:
        data = self._read()
        if name not in data:
            raise ProfileError(f"no profile named '{name}'")
        del data[name]
        self._write(data)

    # -- password (Credential Manager only) ---------------------------------

    def password(self, name: str) -> str:
        """Fetch the profile password from Credential Manager.

        Raises ``AuthRequiredError`` (mapped to ``auth_required``) when absent,
        pointing the user at ``scripts/set-credential.py``.
        """
        pw = creds.get_optional(self.tool, name)
        if pw is None:
            raise AuthRequiredError(
                f"no password stored for profile '{name}'. Store it with:\n"
                f"    python scripts/set-credential.py {self.tool} {name}\n"
                f"(saved to Windows Credential Manager target "
                f"agents-and-tools:{self.tool}:{name})"
            )
        return pw

    # -- public, password-free views ---------------------------------------

    def public_view(self, name: str) -> dict:
        """A profile dict safe to return/log: no password, presence flagged."""
        blob = self.get(name)
        blob["has_password"] = creds.has(self.tool, name)
        return blob

    def list_public(self) -> list[dict]:
        return [self.public_view(n) for n in self.names()]
