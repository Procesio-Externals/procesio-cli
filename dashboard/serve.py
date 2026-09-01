"""Launch the framework setup & health dashboard.

    python dashboard/serve.py [--port 8765] [--host 127.0.0.1] [--no-browser]

Binds to loopback only, mints a one-time access token, prints the URL, and opens
the browser. Stdlib http.server (ThreadingHTTPServer) - no web framework, no
install step, so a colleague who has only cloned the repo can run it immediately.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Force keyring's Windows backend explicitly. keyring's default backend
# AUTO-DETECTION probes several backends and blocks when the process has no
# interactive console (as a server launched from a preview manager, a service,
# or a detached shell does) - which would hang the very first credential read.
# Naming the backend skips detection entirely and still uses the real Windows
# Credential Manager. Subprocesses (run-tool / set-credential) inherit this env.
os.environ.setdefault("PYTHON_KEYRING_BACKEND", "keyring.backends.Windows.WinVaultKeyring")

# Auto-switch to the project's .venv Python (keyring/pydantic/yaml live there).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_VENV_PY = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

sys.path.insert(0, str(_PROJECT_ROOT))

import argparse  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import webbrowser  # noqa: E402
from http.server import ThreadingHTTPServer  # noqa: E402

from dashboard.server import security  # noqa: E402
from dashboard.server.handler import Handler  # noqa: E402


def _free_port(host: str, preferred: int) -> int:
    """Use the preferred port if free, else let the OS pick one."""
    for candidate in (preferred, 0):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, candidate))
            port = s.getsockname()[1]
            s.close()
            return port
        except OSError:
            continue
    raise SystemExit("could not bind a local port")


def main() -> int:
    p = argparse.ArgumentParser(description="Framework setup & health dashboard.")
    p.add_argument("--host", default="127.0.0.1",
                   help="Bind address (loopback only; do not expose).")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true",
                   help="Do not auto-open the browser.")
    args = p.parse_args()

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"refusing to bind non-loopback host {args.host!r}: this dashboard "
              "stores credentials and is single-user, local-only.", file=sys.stderr)
        return 2

    port = _free_port(args.host, args.port)
    url = f"http://{args.host}:{port}/?token={security.token()}"

    httpd = ThreadingHTTPServer((args.host, port), Handler)
    httpd.daemon_threads = True

    print("=" * 68)
    print(" Agents & Tools - Setup & Health Dashboard")
    print("=" * 68)
    print(f" Open:  {url}")
    print(" Bound to loopback only. The token gates the API; keep the URL private.")
    print(" Press Ctrl+C to stop.")
    print("=" * 68)

    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
