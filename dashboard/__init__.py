"""Framework setup & health dashboard.

A local, single-user web console for onboarding: see every tool, agent, skill,
and the context/state store; see exactly what each is missing; and perform every
setup action (store credentials, fill config, capture logins, verify) from the UI
instead of the terminal or a chat with Claude.

Not a JSON-in/JSON-out tool (it is a long-running local server), so it lives here
as its own framework component beside scripts/, tools/, agents/, skills/. It
carries ZERO user data: all state stays under context-state-knowledge/ resolved
through tools/_lib/userdata.py, keeping the wipe-safe boundary intact.

LLM-agnostic: any model work (functional tests, context inspection, the setup
copilot) goes through the `llm` tool, which is provider-neutral. The dashboard
never calls Claude or any hardcoded provider.

Launch:  python dashboard/serve.py
"""
