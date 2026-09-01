# Security policy

## Report a vulnerability

Don't open a public issue for a security problem.

Use GitHub's private reporting instead. Go to the **Security** tab, then
**Report a vulnerability**. The report stays private between you and the
maintainers until a fix ships.

Tell us what you found, how to reproduce it, and what an attacker gains. A
proof of concept helps, but don't test against a system you don't own.

We acknowledge a report within five working days.

## Credentials in an issue or a pull request

If you post a credential by accident, treat it as compromised. Rotate it first,
then tell us so we can purge it from the repository history.

Take particular care with `.procesio` export files. A platform export serializes
Call API credentials inline, so it's a secret even when it looks like a
configuration file.

## Supported versions

The `main` branch is the supported version. Fixes ship there first.
