"""Which form-code-key a call uses: one per PROCESIO installation.

A form's "Switch to code" CSS and JavaScript (`Data.code`) is AES-encrypted with a
passphrase the installation's web app holds. The platform team confirmed (2026-10-01)
that there is one key per INSTALLATION: identical on every workspace of it, and not
guaranteed to match on another. In this tool an installation is an environment
(environments.py), so the key is stored per environment:

    agents-and-tools:procesio:form-code-key@<environment>    e.g. form-code-key@Internal-QA

The bare `form-code-key` predates that and keeps working for the DEFAULT environment,
the same rule an unbound credential profile follows (environments.resolve). It is never
used for any other environment: a blob encrypted with another installation's key is one
that installation's renderer cannot open, and the form goes blank
(FORM-DEV-GUIDE/08-PITFALLS.md). A missing key is an error naming the exact secret to
store, never a silent fallback.
"""
from __future__ import annotations

from tools.procesio.errors import UsageError

TOOL = "procesio"
LEGACY = "form-code-key"


def secret_name(env_name: str) -> str:
    """The Credential Manager secret holding `env_name`'s key."""
    return f"{LEGACY}@{env_name}"


def key_for(env_name: str | None) -> str:
    """The form-code-key for `env_name` (None means the default environment)."""
    from tools._lib import creds  # lazy: avoid the keyring import unless needed
    from tools.procesio import environments

    default = environments.get_default()
    env = (environments.canonical_name(env_name) or env_name) if env_name else default
    key = creds.get_optional(TOOL, secret_name(env))
    if key:
        return key
    if env == default:
        key = creds.get_optional(TOOL, LEGACY)
        if key:
            return key
    other = (f" The bare {LEGACY} is the default environment's key ({default}) and is "
             f"never used for another installation." if env != default else "")
    raise UsageError(
        f"no form-code-key stored for environment {env}: the AES passphrase that "
        f"installation uses for a form's Data.code. Store it with: python "
        f"scripts/set-credential.py {TOOL} {secret_name(env)}.{other}")
