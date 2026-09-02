"""Tool and agent manifest loading + validation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ArgSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    type: Literal["string", "integer", "number", "boolean", "array", "object"] = "string"
    required: bool = False
    description: str = ""
    default: Any = None


class SecretSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    optional: bool = False
    """True when the tool works without this secret and only one branch of it
    needs the value. Such a secret must not count against readiness: showing a
    fully working tool as red teaches people to ignore the colour, and the next
    genuinely missing credential reads the same as this one. The dashboard and
    `list-tools` still surface it, as an optional extra rather than a blocker."""


class RoutingSpec(BaseModel):
    """Optional request-routing hint, consumed by scripts/build-router.py to
    build the Capability Router in CLAUDE.md. Lets a tool declare, in its own
    manifest (the source of truth), the natural-language asks that should map to
    it and the action to reach for first. When absent, the router falls back to
    the tool description and a heuristic primary action."""
    model_config = ConfigDict(extra="forbid")

    triggers: list[str] = Field(default_factory=list)
    primary_action: str = ""
    example: str = ""


class HealthcheckSpec(BaseModel):
    """Optional live-credential probe, consumed by the dashboard's validation
    layer (and any 'is this actually connected' check). Declares a cheap,
    read-only, side-effect-free call whose success proves the stored credential
    is currently authorized - not merely present in Credential Manager.

    - `action`: the action name to invoke on a dispatch tool. Empty for a flat
      tool (the tool is run with no action positional).
    - `args`: arg-name -> value, forwarded as `--name value` to the tool.
    - `label`: optional human label for what the probe does (e.g. 'list 1 user').

    When absent, the dashboard falls back to the tool's own `auth-status` action
    (a soft convention), then to presence-only. MUST be read-only: it runs
    unattended on every dashboard load."""
    model_config = ConfigDict(extra="forbid")

    action: str = ""
    args: dict[str, Any] = Field(default_factory=dict)
    label: str = ""


class WebSessionSpec(BaseModel):
    """Declares that a tool works by driving a saved browser login (the `web`
    tool's session) rather than an API credential. Lets the dashboard show a
    per-tool 'Connect login' button prefilled with the right name/URL, and count
    a missing session as 'needs setup' - so a colleague never has to guess a
    session name or login URL.

    - `name`: the session name the tool opens (matches `web save-session --name`).
    - `login_url`: the URL to open for the human to log in.
    - `persistent`: capture a persistent profile (IndexedDB-auth sites, e.g.
      WhatsApp) instead of a storageState snapshot.
    - `channel`: a real browser channel ('chrome'/'msedge'), e.g. for Google-SSO.
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    login_url: str = ""
    persistent: bool = False
    channel: str = ""
    label: str = ""


class RequirementSpec(BaseModel):
    """Something that must exist ON THE MACHINE - not a Python dependency.

    `uv sync` installs the venv; it does not install a browser engine, a database
    driver or a codec. Those were previously discovered one incident at a time and
    then hard-coded into the onboarding brief from memory, which is exactly how a
    fresh install ends up looking healthy and failing at the user's first real
    call: `list-tools` reports ready, the test suite passes, and the browser tools
    die on their first action because the Playwright binary was never downloaded.

    Declaring them makes the gap machine-checkable
    (`python scripts/check-requirements.py`) instead of remembered.

    - `name`: short id, e.g. `playwright-chromium`, `ffmpeg`, `odbc-sqlserver`.
    - `kind`: what sort of thing it is (drives how it's presented, not logic).
    - `why`: what breaks without it - written for the person reading the failure.
    - `check`: a cheap shell command that exits 0 when the thing is present.
    - `install`: how to get it (a winget id, a documented command).
    - `auto`: the tool installs it itself on first use, so a missing one is a
      warning rather than a blocker (ffmpeg does this via tools/_lib/ffmpeg.py).
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["binary", "browser", "driver", "service", "runtime"] = "binary"
    why: str = ""
    check: str = ""
    install: str = ""
    auto: bool = False


class ActionSpec(BaseModel):
    """One action of a multi-action (dispatch) tool.

    Action-based tools take the action name as the first positional arg;
    each action has its own arg set. Flat tools use `args` at the top level.
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    args: list[ArgSpec] = Field(default_factory=list)
    output_schema: str = ""
    examples: list[dict] = Field(default_factory=list)


class ToolManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    version: str = "0.1.0"
    runtime: Literal["python"] = "python"
    entrypoint: str = "main.py"
    # Catalog tier for the multi-tenant PROCESIO module (spec P0.0-06 / D11):
    #   official  - platform-owned, shared, users can't change (IsProcesio)
    #   template  - a shipped default every workspace starts from, copy-on-write
    #   custom    - workspace-authored
    # Default 'template': a shipped tool is a default a workspace may fork. Ignored
    # entirely by the local single-tenant runtime, so it changes nothing locally.
    tier: Literal["official", "template", "custom"] = "template"
    args: list[ArgSpec] = Field(default_factory=list)
    actions: list[ActionSpec] = Field(default_factory=list)
    secrets: list[SecretSpec] = Field(default_factory=list)
    routing: RoutingSpec | None = None
    healthcheck: HealthcheckSpec | None = None
    web_session: WebSessionSpec | None = None
    requires: list[RequirementSpec] = Field(default_factory=list)
    output_schema: str = ""
    examples: list[dict] = Field(default_factory=list)
    # path is filled by the loader; not part of the YAML
    path: Path | None = None

    def is_action_based(self) -> bool:
        return len(self.actions) > 0

    def action_names(self) -> list[str]:
        return [a.name for a in self.actions]

    def get_action(self, name: str) -> ActionSpec | None:
        for a in self.actions:
            if a.name == name:
                return a
        return None


def load_tool(manifest_path: Path) -> ToolManifest:
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{manifest_path}: top-level YAML must be a mapping")
    m = ToolManifest(**raw)
    m.path = manifest_path.parent
    return m


class AgentManifest(BaseModel):
    """Manifest for a registered agent.

    An agent is invoked exactly like an action-dispatch tool (action name as the
    first positional arg, JSON in / JSON out, secrets via Credential Manager), so
    it shares ToolManifest's shape. It additionally declares `tools`: the names of
    registered tools it orchestrates. The runtime resolves those via the registry,
    never a hardcoded list.
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    version: str = "0.1.0"
    runtime: Literal["python"] = "python"
    entrypoint: str = "main.py"
    # Catalog tier (spec P0.0-06 / D11); see ToolManifest.tier. Default 'template'.
    tier: Literal["official", "template", "custom"] = "template"
    tools: list[str] = Field(default_factory=list)
    args: list[ArgSpec] = Field(default_factory=list)
    actions: list[ActionSpec] = Field(default_factory=list)
    secrets: list[SecretSpec] = Field(default_factory=list)
    routing: RoutingSpec | None = None
    healthcheck: HealthcheckSpec | None = None
    output_schema: str = ""
    examples: list[dict] = Field(default_factory=list)
    # path is filled by the loader; not part of the YAML
    path: Path | None = None

    def is_action_based(self) -> bool:
        return len(self.actions) > 0

    def action_names(self) -> list[str]:
        return [a.name for a in self.actions]

    def get_action(self, name: str) -> ActionSpec | None:
        for a in self.actions:
            if a.name == name:
                return a
        return None


def load_agent(manifest_path: Path) -> AgentManifest:
    raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{manifest_path}: top-level YAML must be a mapping")
    m = AgentManifest(**raw)
    m.path = manifest_path.parent
    return m


class SkillManifest(BaseModel):
    """Manifest for a registered skill.

    A skill is instruction/reference content (not an executable), so its native
    `SKILL.md` YAML frontmatter IS its manifest — no separate file, no duplicated
    metadata. The frontmatter always carries `name` + `description`; it may also
    carry native keys we don't model (`license`, `allowed-tools`, etc.), so unlike
    tool/agent manifests this is lenient (`extra="ignore"`) — skills are imported
    artifacts we keep portable, not author from scratch.

    An optional `routing:` block lets a skill curate its Capability-Router line,
    exactly like a tool. When absent, the router falls back to the description.
    """
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str
    version: str = "0.1.0"
    routing: RoutingSpec | None = None
    # path is filled by the loader; not part of the frontmatter
    path: Path | None = None


def _split_frontmatter(text: str) -> dict:
    """Parse the leading `---`-delimited YAML frontmatter from a SKILL.md body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md is missing its '---' YAML frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            raw = yaml.safe_load("\n".join(lines[1:i]))
            if not isinstance(raw, dict):
                raise ValueError("SKILL.md frontmatter must be a YAML mapping")
            return raw
    raise ValueError("SKILL.md frontmatter is not terminated by a closing '---'")


def load_skill(skill_md_path: Path) -> SkillManifest:
    raw = _split_frontmatter(skill_md_path.read_text(encoding="utf-8"))
    m = SkillManifest(**raw)
    m.path = skill_md_path.parent
    return m
