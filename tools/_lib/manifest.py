"""Tool and agent manifest loading + validation."""
from __future__ import annotations

import threading
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# libyaml's safe loader where PyYAML was built with it, the pure-Python one otherwise. Both are
# safe loaders and read a manifest into the same data; the C one is several times faster, which
# matters because a large manifest is read on every tool call (tests/test_manifest_loading.py
# holds the two to the same result for every manifest in the repo).
_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _parse_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_YAML_LOADER)  # noqa: S506 - a safe loader either way


# Parsed manifests of this process: path -> ((mtime_ns, size), manifest). A manifest is read
# again only when its file changed, so a long-lived process (the MCP server, the dashboard) pays
# for each one once instead of on every lookup. What comes back is the SHARED object: read it,
# never change it.
_LOADED: dict[str, tuple[tuple[int, int], Any]] = {}
_LOADED_LOCK = threading.Lock()


def clear_manifest_cache() -> None:
    """Forget every parsed manifest. For tests, and for a caller that rewrote one in place
    faster than the file's timestamp can show."""
    with _LOADED_LOCK:
        _LOADED.clear()


def _load_manifest(manifest_path: Path, model: type):
    """The manifest at `manifest_path` as `model`, from this process's memory while the file is
    unchanged. The lock is held while one is parsed, so callers that arrive together wait for
    that one parse instead of each doing their own."""
    stat = manifest_path.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    key = str(manifest_path)
    with _LOADED_LOCK:
        hit = _LOADED.get(key)
        if hit is not None and hit[0] == stamp:
            return hit[1]
        raw = _parse_yaml(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError(f"{manifest_path}: top-level YAML must be a mapping")
        manifest = model(**raw)
        manifest.path = manifest_path.parent
        _LOADED[key] = (stamp, manifest)
        return manifest


class ArgSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    name: str
    type: Literal["string", "integer", "number", "boolean", "array", "object"] = "string"
    required: bool = False
    description: str = ""
    default: Any = None
    # JSON Schema for an arg that carries a STRUCTURED payload (a config, a DTO). A
    # one-line `help=` can say an arg takes "a JSON object" but not what has to be in
    # it, so a caller that only has the manifest has to reverse-engineer the shape from
    # validation errors, one layer per attempt. Populate it from the schema the tool
    # already validates against, never a hand-written copy, so the two cannot drift.
    # Aliased: the manifest key stays `schema`, but a field literally named `schema`
    # shadows BaseModel.schema() and pydantic warns on every import.
    json_schema: dict | None = Field(default=None, alias="schema")
    # The flag may be given several times, one value each (argparse `action="append"`).
    # `type` cannot say this: an `array` argument is as often ONE flag that takes a JSON
    # list. A caller that holds a list of values has to know which of the two the tool
    # expects, or it sends the list as one value and the tool reads it as a single item.
    repeatable: bool = False


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
    - `optional`: only machines that USE this tool need it (a client product one
      team installs and another never does), so a missing one is a warning with
      its install pointer, never a blocker of the onboarding gate. Without it, a
      tool for one team makes the check fail on every other team's machine.
    """
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["binary", "browser", "driver", "service", "runtime"] = "binary"
    why: str = ""
    check: str = ""
    install: str = ""
    auto: bool = False
    optional: bool = False


# PROCESIO's built-in credential templates, by the name their `Type` carries, as the id Web-Api
# reports them (credentials_template.Gid read through Guid.ToByteArray - which is why the second
# group reads 0001 while the stored hex reads 0100). CUSTOM is deliberately absent: every custom
# template shares that Type, so a custom one must be named by its id.
PROCESIO_TEMPLATE_IDS = {
    "REST_API": "10101010-0001-0000-0000-aaaaaaaaaaaa",
    "SMTP": "20202020-0001-0000-0000-aaaaaaaaaaaa",
    "AI_OPENAI_COMPATIBLE": "27272727-0001-0000-0000-aaaaaaaaaaaa",
    "FTP": "30303030-0001-0000-0000-aaaaaaaaaaaa",
    "DB": "40404040-0001-0000-0000-aaaaaaaaaaaa",
    "REDIS": "80808080-0001-0000-0000-aaaaaaaaaaaa",
}


# Not a template: the PROCESIO API key the user generated for the AI assistant (AI assistant
# settings). A tool naming it acts on PROCESIO itself, with that user's permissions.
PROCESIO_API_KEY = "PROCESIO_API_KEY"


class ProcesioCredentialSpec(BaseModel):
    """Where this tool's secrets come from on the PROCESIO platform.

    During a PROCESIO turn the AAT MCP server reads them with the turn user's own API key, so a tool
    gets exactly the credentials that user can see. For a template, it asks Web-Api for the user's
    credentials of that template (api/aat/tool-credentials), each as `{be_id: value}`, and builds
    the tool's secrets from `map`. Web-Api knows nothing about AAT's secret names - the pair
    (template, be_id) is the whole contract.

    - `template`: where the secrets come from:
        * a built-in Type name - REST_API or AI_OPENAI_COMPATIBLE, the two a tool may read - or a
          template id. `map` says which field is which secret.
        * `PROCESIO_API_KEY` - the user's AI assistant API key itself, turned into secrets by
          `adapter`. For a tool that acts on PROCESIO.
    - `map`: this tool's secret name -> the be_id holding it (`Value`, `Password`, `UserName`,
      `URL`, ...). A `namespace:name` secret (shared, e.g. `google:oauth-token`) is mapped under
      that same name.
    - `hosts`: the hosts a credential's URL must be on for this tool to pick it, e.g.
      `api.github.com`, or `*.atlassian.net` for any subdomain. Empty: every credential of the
      template is a candidate. A REST API credential carries no notion of which service it is for,
      so without hosts a workspace's process credentials are all candidates too.
    - `adapter`: build the tool's secrets in code instead of by `map`. `procesio-profile` (for
      PROCESIO_API_KEY): the key becomes a procesio API-key profile.
    - `label`: how the service is named to the model and the user, e.g. in "create a REST API
      credential for GitHub"; defaults to the tool name.

    When several credentials match, the model picks one by name (run_tool's `credential`). Without
    this block a tool with secrets cannot get them inside a PROCESIO turn.
    """
    model_config = ConfigDict(extra="forbid")

    template: str
    map: dict[str, str] = Field(default_factory=dict)
    hosts: list[str] = Field(default_factory=list)
    adapter: Literal["procesio-profile"] | None = None
    label: str | None = None

    def is_api_key(self) -> bool:
        return self.template.strip().upper() == PROCESIO_API_KEY

    def template_id(self) -> str | None:
        """The template id Web-Api is asked for; None for PROCESIO_API_KEY."""
        if self.is_api_key():
            return None
        return PROCESIO_TEMPLATE_IDS.get(self.template.strip().upper(), self.template.strip().lower())


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
    procesio_credential: ProcesioCredentialSpec | None = None
    output_schema: str = ""
    examples: list[dict] = Field(default_factory=list)
    # path is filled by the loader; not part of the YAML
    path: Path | None = None

    @model_validator(mode="after")
    def _procesio_credential_is_consistent(self) -> "ToolManifest":
        spec = self.procesio_credential
        if spec is None:
            return self
        declared = {s.name for s in self.secrets}
        # A map entry for a secret the tool does not declare would fill a name nothing reads,
        # and the tool would fail later as "missing credential" with the mapping looking fine.
        unknown = sorted(set(spec.map) - declared)
        if unknown:
            raise ValueError(f"procesio_credential.map names undeclared secrets: {unknown}")
        if spec.is_api_key():
            if spec.adapter is None or spec.map or spec.hosts:
                raise ValueError("procesio_credential PROCESIO_API_KEY takes an adapter, and no map or hosts")
        elif spec.adapter is not None or not spec.map:
            raise ValueError("procesio_credential needs a map (and no adapter) for a PROCESIO template")
        return self

    def credential_template_id(self) -> str | None:
        """The PROCESIO template this tool's credential is read from; None without one."""
        return None if self.procesio_credential is None else self.procesio_credential.template_id()

    def credential_label(self) -> str:
        """How the service this tool needs a credential for is named to the model and the user."""
        spec = self.procesio_credential
        return (spec.label if spec is not None else None) or self.name

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
    return _load_manifest(manifest_path, ToolManifest)


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
    return _load_manifest(manifest_path, AgentManifest)


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

    Skills that opt into the governance discipline also carry `owner`,
    `last_verified`, `baseline_version`, `eval_suite`, and `source_policy`
    (the marker `check-skill-governance.py` scopes on). Imported/portable skills
    omit them and default; `extra="ignore"` keeps any other native key portable.
    """
    model_config = ConfigDict(extra="ignore")

    name: str
    description: str
    version: str = "0.1.0"
    tier: Literal["official", "template", "custom"] = "template"
    routing: RoutingSpec | None = None
    owner: str = ""
    last_verified: date | None = None
    baseline_version: str = ""
    eval_suite: str = ""
    source_policy: Literal["generated", "timestamped", "static"] | None = None
    # path is filled by the loader; not part of the frontmatter
    path: Path | None = None


def _split_frontmatter(text: str) -> dict:
    """Parse the leading `---`-delimited YAML frontmatter from a SKILL.md body."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md is missing its '---' YAML frontmatter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            raw = _parse_yaml("\n".join(lines[1:i]))
            if not isinstance(raw, dict):
                raise ValueError("SKILL.md frontmatter must be a YAML mapping")
            return raw
    raise ValueError("SKILL.md frontmatter is not terminated by a closing '---'")


def load_skill(skill_md_path: Path) -> SkillManifest:
    raw = _split_frontmatter(skill_md_path.read_text(encoding="utf-8"))
    m = SkillManifest(**raw)
    m.path = skill_md_path.parent
    return m
