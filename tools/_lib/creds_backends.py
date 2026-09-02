"""Pluggable credential backends, selected by the ``AAT_CREDS_BACKEND`` env var.

The framework's canonical secret identity is ``agents-and-tools:<tool>:<secret>``.
Every backend resolves the same ``(tool, secret)`` pair; only WHERE it reads from
changes. With ``AAT_CREDS_BACKEND`` unset the OS-native store is chosen for the
platform (see ``default_backend_name``), so no user on any of the three desktops has
to configure anything, and a Windows session behaves exactly as it always did.

  windows          - Windows Credential Manager via keyring (default on win32)
  macos            - macOS login Keychain via keyring (default on darwin)
  linux            - GNOME Keyring / KWallet over D-Bus via keyring (default elsewhere)
  encrypted-file   - one passphrase-encrypted file (``AAT_SECRETS_FILE``); the store
                     for a HEADLESS machine, where no OS keyring exists
  env              - a single JSON blob in ``AAT_SECRETS_JSON`` = {tool:{secret:val}}
  file             - a directory (``AAT_SECRETS_DIR``) of ``<tool>__<secret>`` files
                     and/or a ``secrets.json`` (k8s Secret / mounted-file friendly)
  bridge           - HTTP GET to a loopback host service wrapping the host's Cred Mgr
                     (a container on the laptop reads host secrets; nothing copied)
  procesio         - HTTP GET to a PROCESIO credential resolver, scoped to the active
                     (workspace, user); the multi-tenant platform backend (spec P0.0-08)

The four OWNED stores (windows / macos / linux / encrypted-file) are read/write, so
``set-credential.py`` works on every OS. The four BORROWED ones (env / file / bridge /
procesio) are READ-ONLY: those secrets are managed by a host or cluster and must never
be written from inside a container.

Every OS backend imports ``keyring`` lazily, inside the selected backend only, so this
module imports cleanly on a platform whose keyring backend is unavailable - which is
what lets a Linux container import the framework without a session bus.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Protocol


class Backend(Protocol):
    def get_optional(self, tool: str, secret: str) -> str | None: ...
    def set(self, tool: str, secret: str, value: str) -> None: ...
    def delete(self, tool: str, secret: str) -> None: ...


class _ReadOnly:
    """Mixin: writes raise, so a container never pretends to own the secret store."""

    name = "read-only"

    def set(self, tool: str, secret: str, value: str) -> None:
        raise RuntimeError(
            f"credential backend {self.name!r} is read-only; manage secrets on the "
            f"host/cluster, not from here")

    def delete(self, tool: str, secret: str) -> None:
        raise RuntimeError(
            f"credential backend {self.name!r} is read-only; manage secrets on the "
            f"host/cluster, not from here")


class WindowsBackend:
    """Windows Credential Manager via keyring. Service = agents-and-tools:<tool>."""

    name = "windows"
    NAMESPACE = "agents-and-tools"

    def __init__(self) -> None:
        import keyring  # lazy: only when this backend is selected
        backend = keyring.get_keyring()
        tname = type(backend).__name__
        if "WinVault" not in tname and "Windows" not in tname:
            try:
                from keyring.backends.Windows import WinVaultKeyring
                keyring.set_keyring(WinVaultKeyring())
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(
                    f"keyring backend is {tname}, not Windows Credential Manager. "
                    f"The 'windows' creds backend requires Windows. ({e})") from e
        self._kr = keyring

    def _svc(self, tool: str) -> str:
        return f"{self.NAMESPACE}:{tool}"

    def get_optional(self, tool: str, secret: str) -> str | None:
        return self._kr.get_password(self._svc(tool), secret)

    def set(self, tool: str, secret: str, value: str) -> None:
        self._kr.set_password(self._svc(tool), secret, value)

    def delete(self, tool: str, secret: str) -> None:
        try:
            self._kr.delete_password(self._svc(tool), secret)
        except self._kr.errors.PasswordDeleteError:
            pass


class MacKeychainBackend:
    """macOS login Keychain via keyring. Service = agents-and-tools:<tool>.

    The macOS peer of WindowsBackend: same NAMESPACE and (tool, secret) identity, so a
    Mac user's secrets live in the login Keychain exactly where a Windows user's live in
    Credential Manager. Read/write (set-credential.py works). keyring's macOS backend is
    imported lazily so this module still imports cleanly off-Mac."""

    name = "macos"
    NAMESPACE = "agents-and-tools"

    def __init__(self) -> None:
        # Use a DIRECT macOS backend instance. Do NOT call keyring.get_keyring()
        # / set_keyring(): those trigger keyring's backend auto-detection, which
        # evaluates the built-in Windows backend's `priority` classproperty — and
        # that raises "Requires Windows and pywin32" on macOS. Talking to the
        # macOS.Keyring instance directly sidesteps auto-detection entirely.
        try:
            from keyring.backends import macOS as _macos
            from keyring import errors as _errors
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"macOS Keychain keyring backend unavailable ({e}); "
                f"the 'macos' creds backend requires macOS.") from e
        self._kc = _macos.Keyring()
        self._errors = _errors

    def _svc(self, tool: str) -> str:
        return f"{self.NAMESPACE}:{tool}"

    def get_optional(self, tool: str, secret: str) -> str | None:
        return self._kc.get_password(self._svc(tool), secret)

    def set(self, tool: str, secret: str, value: str) -> None:
        self._kc.set_password(self._svc(tool), secret, value)

    def delete(self, tool: str, secret: str) -> None:
        try:
            self._kc.delete_password(self._svc(tool), secret)
        except self._errors.PasswordDeleteError:
            pass


class LinuxSecretServiceBackend:
    """Linux desktop secret store via keyring. Service = agents-and-tools:<tool>.

    The Linux peer of WindowsBackend / MacKeychainBackend: same NAMESPACE and
    ``(tool, secret)`` identity, so a Linux user's secrets live in GNOME Keyring or
    KWallet exactly where a Windows user's live in Credential Manager. Read/write, so
    ``set-credential.py`` works.

    Like the macOS backend, this talks to a DIRECT backend instance and never calls
    ``keyring.get_keyring()`` / ``set_keyring()``: auto-detection evaluates the built-in
    Windows backend's ``priority`` classproperty, which raises off-Windows.

    Availability is probed through each backend's ``priority`` classproperty, which is
    keyring's own "can I run here" contract - it raises when the D-Bus Secret Service
    (or KWallet) is not reachable. That is the normal case on a HEADLESS server: there
    is no session bus, so no OS keyring exists to talk to. The error then names the
    backends that do work without a desktop session rather than leaving the caller with
    a D-Bus traceback."""

    name = "linux"
    NAMESPACE = "agents-and-tools"

    # (module path, class name) in preference order. SecretService covers GNOME /
    # freedesktop.org (the default on most distros); kwallet covers KDE.
    _CANDIDATES = (
        ("keyring.backends.SecretService", "Keyring"),
        ("keyring.backends.kwallet", "DBusKeyring"),
    )

    def __init__(self) -> None:
        try:
            from keyring import errors as _errors
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"keyring is not installed ({e})") from e
        self._errors = _errors

        import importlib

        attempts: list[str] = []
        for mod_path, cls_name in self._CANDIDATES:
            try:
                cls = getattr(importlib.import_module(mod_path), cls_name)
                cls.priority  # noqa: B018 - keyring's own availability probe; raises when unusable
                self._kr = cls()
                self.backend_name = f"{mod_path}.{cls_name}"
                return
            except Exception as e:  # noqa: BLE001 - try the next candidate
                attempts.append(f"{mod_path}.{cls_name}: {e}")
        raise RuntimeError(
            "no Linux OS keyring is reachable (tried " + "; ".join(attempts) + "). "
            "On a headless machine there is no session keyring: set "
            "AAT_CREDS_BACKEND=encrypted-file (read/write, passphrase in "
            "AAT_SECRETS_PASSPHRASE), or =file / =env for secrets managed by the "
            "host or cluster.")

    def _svc(self, tool: str) -> str:
        return f"{self.NAMESPACE}:{tool}"

    def get_optional(self, tool: str, secret: str) -> str | None:
        return self._kr.get_password(self._svc(tool), secret)

    def set(self, tool: str, secret: str, value: str) -> None:
        self._kr.set_password(self._svc(tool), secret, value)

    def delete(self, tool: str, secret: str) -> None:
        try:
            self._kr.delete_password(self._svc(tool), secret)
        except self._errors.PasswordDeleteError:
            pass


class EncryptedFileBackend:
    """A single passphrase-encrypted file, for a machine with no OS keyring.

    The headless-Linux (and container-with-state) peer of the three OS stores: same
    ``(tool, secret)`` identity, READ/WRITE, so ``set-credential.py`` works where
    GNOME Keyring and KWallet do not exist. Distinct from ``file`` / ``env``, which are
    read-only views of secrets some host or cluster already manages.

    Storage: one JSON envelope at ``AAT_SECRETS_FILE``
    (default ``~/.config/agents-and-tools/secrets.enc``) holding a per-file scrypt salt
    and a Fernet token over ``{tool: {secret: value}}``. The file is written 0600 and
    replaced atomically, so a crash mid-write cannot leave a half-written store that
    reads as an empty one.

    The passphrase comes from ``AAT_SECRETS_PASSPHRASE``, or an interactive prompt ONLY
    when stdin is a TTY. An agent runs with stdin closed, so prompting there would hang
    forever instead of failing; the error says which variable to set."""

    name = "encrypted-file"
    VERSION = 1
    SCRYPT_N = 2 ** 15
    SCRYPT_R = 8
    SCRYPT_P = 1

    def __init__(self) -> None:
        self._path = Path(
            os.environ.get("AAT_SECRETS_FILE")
            or Path.home() / ".config" / "agents-and-tools" / "secrets.enc")
        self._cache: dict | None = None

    # --- crypto ----------------------------------------------------------

    @staticmethod
    def _passphrase() -> str:
        pw = os.environ.get("AAT_SECRETS_PASSPHRASE")
        if pw:
            return pw
        if sys.stdin is not None and sys.stdin.isatty():
            import getpass
            pw = getpass.getpass("AAT secrets passphrase: ")
            if pw:
                return pw
        raise RuntimeError(
            "no passphrase for the encrypted-file credential store: set "
            "AAT_SECRETS_PASSPHRASE (a non-interactive run cannot be prompted)")

    def _fernet(self, salt: bytes):
        try:
            from cryptography.fernet import Fernet
            from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(
                f"the encrypted-file credential backend needs the 'cryptography' "
                f"package ({e}); install it or use AAT_CREDS_BACKEND=file/env") from e
        import base64
        key = Scrypt(salt=salt, length=32, n=self.SCRYPT_N, r=self.SCRYPT_R,
                     p=self.SCRYPT_P).derive(self._passphrase().encode("utf-8"))
        return Fernet(base64.urlsafe_b64encode(key))

    # --- store -----------------------------------------------------------

    def _load(self) -> dict:
        if self._cache is not None:
            return self._cache
        if not self._path.exists():
            self._cache = {}
            return self._cache
        import base64
        try:
            env = json.loads(self._path.read_text(encoding="utf-8"))
        except ValueError as e:
            raise RuntimeError(f"{self._path} is not a valid secret store: {e}") from e
        if int(env.get("version", 0)) != self.VERSION:
            raise RuntimeError(
                f"{self._path}: unsupported store version {env.get('version')!r}")
        f = self._fernet(base64.b64decode(env["salt"]))
        try:
            plain = f.decrypt(env["data"].encode("ascii"))
        except Exception as e:  # noqa: BLE001 - InvalidToken and friends
            raise RuntimeError(
                f"cannot decrypt {self._path}: wrong passphrase, or the file was "
                f"written with a different one ({type(e).__name__})") from e
        self._cache = json.loads(plain.decode("utf-8"))
        return self._cache

    def _save(self, data: dict) -> None:
        import base64
        salt = os.urandom(16)  # fresh salt per write: never reuse a KDF salt
        blob = self._fernet(salt).encrypt(
            json.dumps(data, ensure_ascii=False).encode("utf-8"))
        env = {"version": self.VERSION, "kdf": "scrypt",
               "n": self.SCRYPT_N, "r": self.SCRYPT_R, "p": self.SCRYPT_P,
               "salt": base64.b64encode(salt).decode("ascii"),
               "data": blob.decode("ascii")}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(env), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)  # no-op semantics on Windows; correct on POSIX
        except OSError:
            pass
        os.replace(tmp, self._path)  # atomic: a crash never leaves a partial store
        self._cache = data

    # --- Backend protocol -------------------------------------------------

    def get_optional(self, tool: str, secret: str) -> str | None:
        v = (self._load().get(tool) or {}).get(secret)
        return str(v) if v is not None else None

    def set(self, tool: str, secret: str, value: str) -> None:
        data = dict(self._load())
        data[tool] = {**(data.get(tool) or {}), secret: value}
        self._save(data)

    def delete(self, tool: str, secret: str) -> None:
        data = dict(self._load())
        bucket = dict(data.get(tool) or {})
        if bucket.pop(secret, None) is None:
            return
        if bucket:
            data[tool] = bucket
        else:
            data.pop(tool, None)
        self._save(data)


class EnvJsonBackend(_ReadOnly):
    """Secrets from one JSON blob in AAT_SECRETS_JSON = {"tool": {"secret": "val"}}.
    Simplest for docker-compose (pass a single env var)."""

    name = "env"

    def __init__(self) -> None:
        raw = (os.environ.get("AAT_SECRETS_JSON") or "").strip()
        try:
            self._data = json.loads(raw) if raw else {}
        except ValueError as e:
            raise RuntimeError(f"AAT_SECRETS_JSON is not valid JSON: {e}") from e

    def get_optional(self, tool: str, secret: str) -> str | None:
        v = (self._data.get(tool) or {}).get(secret)
        return str(v) if v is not None else None


class FileSecretBackend(_ReadOnly):
    """Secrets from a directory (AAT_SECRETS_DIR, default /run/secrets/aat) of
    ``<tool>__<secret>`` files (k8s Secret mounts each key as a file) and/or a
    ``secrets.json`` in the same dir.

    Multi-user: when AAT_USER_ID is set, a per-user subdir ``<dir>/<user>/`` is searched
    FIRST, then the shared dir — so each user's mounted Secret isolates their
    credentials (spec 08). Unset = single shared dir, exactly as before."""

    name = "file"

    def __init__(self) -> None:
        self._dir = Path(os.environ.get("AAT_SECRETS_DIR") or "/run/secrets/aat")

    @staticmethod
    def _safe(v: str) -> str | None:
        s = re.sub(r"[^0-9A-Za-z._-]+", "-", (v or "").strip()).strip("-._")
        return s if s and s not in (".", "..") else None

    def _dirs(self) -> list[Path]:
        """Search order, most specific first, mirroring userdata's ``(ws, user)``
        layout (spec P0.0-01): ``ws/<ws>/<user>`` -> ``<user>`` -> ``ws/<ws>`` ->
        shared. Unset AAT_WORKSPACE_ID/AAT_USER_ID falls straight through to the shared
        dir, exactly the historical behaviour."""
        dirs: list[Path] = []
        ws = self._safe(os.environ.get("AAT_WORKSPACE_ID") or "")
        uid = self._safe(os.environ.get("AAT_USER_ID") or "")
        if ws and uid:
            dirs.append(self._dir / "ws" / ws / uid)  # per-(ws,user), highest priority
        if uid:
            dirs.append(self._dir / uid)              # per-user
        if ws:
            dirs.append(self._dir / "ws" / ws)        # per-workspace (shared in WS)
        dirs.append(self._dir)                          # shared fallback
        return dirs

    def get_optional(self, tool: str, secret: str) -> str | None:
        for d in self._dirs():
            f = d / f"{tool}__{secret}"
            if f.exists():
                return f.read_text(encoding="utf-8").strip() or None
            jf = d / "secrets.json"
            if jf.exists():
                try:
                    v = (json.loads(jf.read_text(encoding="utf-8")).get(tool) or {}).get(secret)
                except ValueError:
                    v = None
                if v is not None:
                    return str(v)
        return None


class BridgeBackend(_ReadOnly):
    """HTTP GET to a loopback host service that wraps Windows Credential Manager.
    Lets a container on the laptop read host secrets without copying them (infra I1).
    AAT_CREDS_BRIDGE_URL (default http://host.docker.internal:8903) + a bearer token
    in AAT_CREDS_BRIDGE_TOKEN."""

    name = "bridge"

    def __init__(self) -> None:
        self._url = (os.environ.get("AAT_CREDS_BRIDGE_URL")
                     or "http://host.docker.internal:8903").rstrip("/")
        self._token = os.environ.get("AAT_CREDS_BRIDGE_TOKEN", "")
        # In-container cache. The container's readiness scan checks every secret over
        # the network and the model calls capabilities repeatedly; secrets don't change
        # mid-session, so cache with a short TTL (AAT_CREDS_BRIDGE_TTL seconds, 0 = off).
        # The value stays in memory only - already fetched on use.
        self._cache: dict = {}
        self._ttl = float(os.environ.get("AAT_CREDS_BRIDGE_TTL", "60") or 0)

    def get_optional(self, tool: str, secret: str) -> str | None:
        if self._ttl > 0:
            hit = self._cache.get((tool, secret))
            if hit is not None and hit[1] > time.monotonic():
                return hit[0]
        val = self._fetch(tool, secret)
        if self._ttl > 0:
            self._cache[(tool, secret)] = (val, time.monotonic() + self._ttl)
        return val

    def _fetch(self, tool: str, secret: str) -> str | None:
        req = urllib.request.Request(
            f"{self._url}/secret/{tool}/{secret}",
            headers={"Authorization": f"Bearer {self._token}"} if self._token else {})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 (loopback)
                body = resp.read().decode("utf-8").strip()
                return body or None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        except urllib.error.URLError:
            return None


class ProcesioBackend(_ReadOnly):
    """Resolve a secret from the PROCESIO credential store for the active
    ``(workspace, user)`` (spec P0.0-08). Structurally identical to ``BridgeBackend``:
    a read-only, TTL-cached HTTP GET to a resolver endpoint. The endpoint maps AAT's
    ``(tool, secret)`` identity to a PROCESIO ``CREDENTIALS`` row in the caller's
    workspace and returns the decrypted value; nothing is written from a worker.

    Config: ``AAT_PROCESIO_CREDS_URL`` (resolver base), ``AAT_PROCESIO_CREDS_TOKEN``
    (bearer), ``AAT_CREDS_PROCESIO_TTL`` (cache seconds, default 60). The active
    ``(workspace, user)`` are sent as ``X-AAT-Workspace`` / ``X-AAT-User`` headers
    (server-established env, item P0.0-01), so the endpoint scopes the lookup - incl.
    the personal-workspace ``(WS=Empty, User)`` case. Import-safe on any OS."""

    name = "procesio"

    def __init__(self) -> None:
        self._url = (os.environ.get("AAT_PROCESIO_CREDS_URL")
                     or "http://localhost:8904").rstrip("/")
        self._token = os.environ.get("AAT_PROCESIO_CREDS_TOKEN", "")
        self._cache: dict = {}
        self._ttl = float(os.environ.get("AAT_CREDS_PROCESIO_TTL", "60") or 0)

    def _headers(self) -> dict:
        h = {}
        if self._token:
            h["Authorization"] = f"Bearer {self._token}"
        ws = (os.environ.get("AAT_WORKSPACE_ID") or "").strip()
        uid = (os.environ.get("AAT_USER_ID") or "").strip()
        if ws:
            h["X-AAT-Workspace"] = ws
        if uid:
            h["X-AAT-User"] = uid
        return h

    def get_optional(self, tool: str, secret: str) -> str | None:
        # Cache key includes (ws,user) so a pooled worker serving many tenants never
        # returns one tenant's secret to another.
        ck = (os.environ.get("AAT_WORKSPACE_ID", ""), os.environ.get("AAT_USER_ID", ""),
              tool, secret)
        if self._ttl > 0:
            hit = self._cache.get(ck)
            if hit is not None and hit[1] > time.monotonic():
                return hit[0]
        val = self._fetch(tool, secret)
        if self._ttl > 0:
            self._cache[ck] = (val, time.monotonic() + self._ttl)
        return val

    def _fetch(self, tool: str, secret: str) -> str | None:
        req = urllib.request.Request(
            f"{self._url}/credential/{tool}/{secret}", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                body = resp.read().decode("utf-8").strip()
                return body or None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise
        except urllib.error.URLError:
            return None


_ALIASES = {
    "windows": "windows", "winvault": "windows", "win32": "windows",
    "macos": "macos", "mac": "macos", "keychain": "macos", "osx": "macos", "darwin": "macos",
    "linux": "linux", "secretservice": "linux", "secret-service": "linux",
    "kwallet": "linux", "gnome-keyring": "linux",
    "encrypted-file": "encrypted-file", "encryptedfile": "encrypted-file",
    "encrypted": "encrypted-file",
    "env": "env", "envjson": "env", "env-json": "env",
    "file": "file", "file-secret": "file", "filesecret": "file",
    "bridge": "bridge",
    "procesio": "procesio",
}
_CTORS = {"windows": WindowsBackend, "macos": MacKeychainBackend,
          "linux": LinuxSecretServiceBackend, "encrypted-file": EncryptedFileBackend,
          "env": EnvJsonBackend, "file": FileSecretBackend, "bridge": BridgeBackend,
          "procesio": ProcesioBackend}

# Every backend name a caller may pass, in one place, so the factory's error message
# cannot drift from what the factory actually accepts (it used to be a hand-kept
# literal that already omitted 'macos').
KNOWN = tuple(sorted(_CTORS))


def default_backend_name() -> str:
    """The backend used when AAT_CREDS_BACKEND is unset: the OS-native secret store.

    macOS -> login Keychain; Windows (incl. Claude Code) -> Credential Manager;
    everything else -> the Linux desktop keyring. A function, not a module constant,
    so a test can exercise the mapping for a platform it is not running on."""
    return {"darwin": "macos", "win32": "windows"}.get(sys.platform, "linux")


def make(name: str | None) -> Backend:
    requested = (name or "").strip().lower() or default_backend_name()
    key = _ALIASES.get(requested)
    if key is None:
        raise ValueError(
            f"unknown AAT_CREDS_BACKEND {name!r}; use one of: " + ", ".join(KNOWN))
    return _CTORS[key]()  # type: ignore[return-value]
