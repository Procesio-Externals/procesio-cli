"""Core of the DTO sub-tool pipeline (see DTO-SUBTOOLS-NOTE.md).

    config --[validate vs config.schema.json]--> --[build: merge onto golden
    template]--> DTO --[optional validate@source oracle]--> --[create | edit]-->
    id --[re-GET]--> result

A `Component` bundles the pieces for one resource type. `build` is PURE
(config + ctx -> DTO, no I/O). Transport is declared as simple endpoint specs for
the common case; a component overrides `create` / `edit` / `validate` with a
callable (receiving the live client) only when it needs multi-step logic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from tools.procesio.errors import UsageError


@dataclass
class Component:
    name: str
    description: str
    dir: Path
    build: Callable[[dict, dict], Any]          # (config, ctx) -> DTO   (PURE, no I/O)
    create_endpoint: tuple                       # (method, path) for the default create
    get_path: str                                # GET template, "{id}" placeholder
    extract_id: Callable[[Any, Any], Any]        # (create_response, dto) -> id
    prepare_ctx: Callable[[Any, dict], dict] | None = None   # (client, config) -> ctx (impure)
    create: Callable[[Any, Any, dict], Any] | None = None    # override (client, dto, ctx) -> resp
    edit: Callable[[Any, Any, dict, dict], Any] | None = None  # (client, id, config, ctx) -> resp
    validate: Callable[[Any, Any, dict], Any] | None = None  # oracle (client, dto, ctx) -> resp|None
    save_gate: Callable[[Any, Any, dict], Any] | None = None  # pre-save gate (client, dto, ctx) -> report; raises on block
    edit_ctx: Callable[[Any, Any, dict, dict], dict] | None = None  # (client, id, config, ctx) -> ctx enriched from the LIVE resource

    @property
    def schema_path(self) -> Path:
        return self.dir / "config.schema.json"

    @property
    def template_path(self) -> Path:
        return self.dir / "template.dto.json"

    def load_schema(self) -> dict:
        return json.loads(self.schema_path.read_text(encoding="utf-8"))

    def load_template(self) -> Any:
        return json.loads(self.template_path.read_text(encoding="utf-8"))


def validate_config(component: Component, config: Any) -> None:
    """Validate `config` against the component JSON Schema, listing every
    violation (fail-fast — the design note's reliability anchor)."""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(component.load_schema())
    errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))
    if errors:
        msgs = []
        for e in errors[:25]:
            loc = "/".join(str(p) for p in e.path) or "(root)"
            msgs.append(f"{loc}: {e.message}")
        raise UsageError(
            f"config does not satisfy the {component.name} schema:\n  - "
            + "\n  - ".join(msgs)
        )


# -- orchestration (used by the handler) ---------------------------------------

def prepare(component: Component, client, config: dict) -> dict:
    return component.prepare_ctx(client, config) if component.prepare_ctx else {}


def build_dto(component: Component, config: dict, ctx: dict) -> Any:
    validate_config(component, config)
    return component.build(config, ctx)


def build_edit_dto(component: Component, client, resource_id, config: dict, ctx: dict) -> Any:
    """The DTO an EDIT would write — the same one `component.edit` builds, not a create's.

    An edit's preview has to be built through the component's own `edit_ctx`, which is what carries
    over everything the live resource already owns. For a process that is the VARIABLE IDS (reused
    by name) and the canvas positions: a variable is referenced by GUID from outside the process, so
    "do the ids survive?" is the question a dry-run exists to answer, and building the preview from
    the config alone answers it wrongly. A live resource that cannot be read falls back to a plain
    build rather than refusing to preview at all.
    """
    if component.edit_ctx:
        try:
            ctx = component.edit_ctx(client, resource_id, config, ctx)
        except Exception:  # noqa: BLE001 - unreadable live resource -> preview what we can
            pass
    return build_dto(component, config, ctx)


def run_create(component: Component, client, dto: Any, ctx: dict) -> Any:
    if component.create:
        return component.create(client, dto, ctx)
    method, path = component.create_endpoint
    return client.request(method, path, body=dto)


def run_validate(component: Component, client, dto: Any, ctx: dict) -> Any:
    return component.validate(client, dto, ctx) if component.validate else None


def run_get(component: Component, client, resource_id: Any, ctx: dict) -> Any:
    return client.get(component.get_path.format(id=resource_id))
