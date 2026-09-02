"""Store a credential in this machine's OS credential store.

Which store that is follows the platform: Windows Credential Manager, the macOS
login Keychain, or the Linux desktop keyring (GNOME Keyring / KWallet). On a
headless machine, where no OS keyring exists, set AAT_CREDS_BACKEND=encrypted-file
(passphrase in AAT_SECRETS_PASSPHRASE) and this script writes there instead. The
identity is the same everywhere: agents-and-tools:<tool>:<secret>.

Secrets are prompted via getpass — never echoed, never written to disk in plaintext.

Usage:
  python scripts/set-credential.py <tool> <secret>          # set or overwrite
  python scripts/set-credential.py <tool> <secret> --delete # remove
  python scripts/set-credential.py <tool> <secret> --check  # just check presence

Examples:
  python scripts/set-credential.py ryver api-token
  python scripts/set-credential.py ryver api-token --delete
"""
from __future__ import annotations

import sys
from pathlib import Path

# Auto-switch to the project's .venv Python if we were launched with a different one.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
# .venv layout is per-OS: Scripts/python.exe on Windows, bin/python everywhere
# else. Hardcoding the Windows path made this a silent no-op on macOS/Linux,
# where the script then ran on whatever interpreter happened to invoke it.
_VENV_PY = (_PROJECT_ROOT / ".venv" / "Scripts" / "python.exe" if sys.platform == "win32"
            else _PROJECT_ROOT / ".venv" / "bin" / "python")
if _VENV_PY.exists() and Path(sys.executable).resolve() != _VENV_PY.resolve():
    import subprocess
    sys.exit(subprocess.run([str(_VENV_PY), __file__, *sys.argv[1:]]).returncode)

import argparse  # noqa: E402
import getpass  # noqa: E402

sys.path.insert(0, str(_PROJECT_ROOT))

from tools._lib import creds  # noqa: E402


def main() -> int:
    p = argparse.ArgumentParser(
        description="Store a credential in this machine's OS credential store "
                    "(Windows Credential Manager / macOS Keychain / Linux keyring).",
        epilog="Target name in the store: agents-and-tools:<tool>:<secret>",
    )
    p.add_argument("tool", help="Tool name (matches name in tool.yaml)")
    p.add_argument("secret", help="Secret name (matches a secrets[].name entry)")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--delete", action="store_true", help="Delete instead of set")
    g.add_argument("--check", action="store_true", help="Check presence; don't prompt")
    g.add_argument("--from-file", help="Read the value from this file (full content, trimmed)")
    g.add_argument("--stdin", action="store_true", help="Read the value from stdin (until EOF)")
    args = p.parse_args()

    target = f"agents-and-tools:{args.tool} / {args.secret}"

    if args.check:
        present = creds.has(args.tool, args.secret)
        print(f"{target}: {'present' if present else 'missing'}")
        return 0 if present else 1

    if args.delete:
        if not creds.has(args.tool, args.secret):
            print(f"not found: {target}")
            return 1
        creds.delete(args.tool, args.secret)
        print(f"deleted: {target}")
        return 0

    if creds.has(args.tool, args.secret):
        # Skip the interactive overwrite prompt when reading non-interactively.
        if not (args.from_file or args.stdin):
            answer = input(f"{target} already exists. Overwrite? [y/N] ").strip().lower()
            if answer != "y":
                print("cancelled.")
                return 0

    interactive = not (args.from_file or args.stdin)
    if args.from_file:
        # utf-8-sig strips a BOM that Notepad/editors may prepend.
        raw = Path(args.from_file).read_text(encoding="utf-8-sig")
        if not raw.strip():
            print(f"file is empty: {args.from_file}", file=sys.stderr)
            return 1
    elif args.stdin:
        raw = sys.stdin.read()
        if not raw.strip():
            print("stdin is empty, aborting.", file=sys.stderr)
            return 1
    else:
        raw = getpass.getpass(f"Enter value for {target}: ")
        if not raw:
            print("empty value, aborting.", file=sys.stderr)
            return 1

    # Clean pasted/typed input: drop surrounding whitespace and any non-printable
    # control characters (e.g. a stray \x16 from a terminal paste).
    value = "".join(c for c in raw if c.isprintable()).strip()
    had_control = any((ord(c) < 32 or ord(c) == 127) for c in raw.strip())

    if had_control:
        print("warning: removed non-printable characters from the pasted value "
              "(terminal paste corruption). Verify it stored correctly.",
              file=sys.stderr)
    # A 1-3 char "secret" is almost always a truncated paste (a known issue with
    # getpass + paste on Windows terminals). Refuse and point to the safe path.
    if len(value) < 4 and interactive:
        print(f"refusing: got only {len(value)} usable char(s) — this looks like a "
              "truncated paste (getpass mangles pasted secrets on some terminals).\n"
              "Save the secret to a file and use --from-file instead:\n"
              f"  python scripts/set-credential.py {args.tool} {args.secret} "
              "--from-file <path>", file=sys.stderr)
        return 1

    creds.set_secret(args.tool, args.secret, value)
    print(f"stored: {target} ({len(value)} bytes) in the "
          f"{getattr(creds._b(), 'name', 'default')} credential store")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
