"""Admin actions (admin role): pipeline/provider/compilation config, the
knowledge base (prompts, spec_modules, examples, validation_rules, clarification),
the compiler self-test, users, and issue cases.

The knowledge actions are how you improve the BUILDER ITSELF — editing the prompt
templates, connector spec modules, and few-shot examples changes how every future
build generates code. That is the deepest feedback loop after a PROCESIO test.
"""
from __future__ import annotations

import argparse

from actiondef import ActionDef
from errors import UsageError
from handlers.common import add_pagination, load_text_or_file, parse_json

_CONFIG_KINDS = ("pipeline", "providers", "compilation", "maintenance")
_MODULE_TYPES = ("prompt", "spec_module", "example", "validation_rule", "clarification")


# -- config ------------------------------------------------------------------

def get_config(client, args) -> dict:
    if args.which not in _CONFIG_KINDS:
        raise UsageError(f"--which must be one of {', '.join(_CONFIG_KINDS)}")
    suffix = "/config/maintenance" if args.which == "maintenance" else f"/config/{args.which}"
    return client.get(f"/admin{suffix}")


def update_config(client, args) -> dict:
    if args.which not in _CONFIG_KINDS:
        raise UsageError(f"--which must be one of {', '.join(_CONFIG_KINDS)}")
    raw = load_text_or_file(args.data, args.data_file, what="data")
    if raw is None:
        raise UsageError("provide --data (JSON) or --data-file")
    body = parse_json(raw, what="data", expect=dict)
    suffix = "/config/maintenance" if args.which == "maintenance" else f"/config/{args.which}"
    return client.put(f"/admin{suffix}", body)


def reload_config(client, args) -> dict:
    return client.post("/admin/config/reload")


# -- knowledge ---------------------------------------------------------------

def knowledge_list(client, args) -> dict:
    _check_module_type(args.module_type)
    return {"module_type": args.module_type,
            "modules": client.get(f"/admin/knowledge/{args.module_type}")}


def knowledge_get(client, args) -> dict:
    _check_module_type(args.module_type)
    return client.get(f"/admin/knowledge/{args.module_type}/{args.name}")


def knowledge_create(client, args) -> dict:
    _check_module_type(args.module_type)
    content = load_text_or_file(args.content, args.content_file, what="content")
    if content is None:
        raise UsageError("provide --content or --content-file")
    return client.post(f"/admin/knowledge/{args.module_type}",
                       {"name": args.name, "content": content})


def knowledge_update(client, args) -> dict:
    _check_module_type(args.module_type)
    content = load_text_or_file(args.content, args.content_file, what="content")
    if content is None:
        raise UsageError("provide --content or --content-file")
    return client.put(f"/admin/knowledge/{args.module_type}/{args.name}",
                      {"content": content})


def knowledge_delete(client, args) -> dict:
    _check_module_type(args.module_type)
    return client.delete(f"/admin/knowledge/{args.module_type}/{args.name}")


def _check_module_type(mt: str) -> None:
    if mt not in _MODULE_TYPES:
        raise UsageError(f"--module-type must be one of {', '.join(_MODULE_TYPES)}")


# -- selftest / users / issues ----------------------------------------------

def build_selftest(client, args) -> dict:
    """POST /admin/build-selftest — end-to-end compiler health (trivial 2-file C#)."""
    return client.post("/admin/build-selftest")


def list_users(client, args) -> dict:
    return {"users": client.get("/admin/users")}


def list_issues(client, args) -> dict:
    params = {"page": args.page, "per_page": args.per_page}
    for f in ("stage", "severity", "status", "build_id", "error_category", "search"):
        v = getattr(args, f)
        if v:
            params[f] = v
    return client.get("/admin/issues", params)


def get_issue(client, args) -> dict:
    return client.get(f"/admin/issues/{args.id}")


# -- argparse ----------------------------------------------------------------

def _get_config_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--which", required=True,
                   help="pipeline | providers | compilation | maintenance")


def _update_config_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--which", required=True,
                   help="pipeline | providers | compilation | maintenance")
    p.add_argument("--data", help="Config payload as JSON (inline)")
    p.add_argument("--data-file", dest="data_file", help="Read JSON payload from path")


def _knowledge_list_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--module-type", dest="module_type", required=True,
                   help=f"one of {', '.join(_MODULE_TYPES)}")


def _knowledge_get_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--module-type", dest="module_type", required=True,
                   help=f"one of {', '.join(_MODULE_TYPES)}")
    p.add_argument("--name", required=True, help="Module name, e.g. clarify.md")


def _knowledge_write_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--module-type", dest="module_type", required=True,
                   help=f"one of {', '.join(_MODULE_TYPES)}")
    p.add_argument("--name", required=True, help="Module name, e.g. clarify.md")
    p.add_argument("--content", help="Module content (inline)")
    p.add_argument("--content-file", dest="content_file",
                   help="Read module content from path")


def _list_issues_args(p: argparse.ArgumentParser) -> None:
    add_pagination(p)
    p.add_argument("--stage", help="Pipeline stage filter")
    p.add_argument("--severity", help="Severity filter")
    p.add_argument("--status", help="Status filter")
    p.add_argument("--build-id", dest="build_id", help="Filter by build")
    p.add_argument("--error-category", dest="error_category", help="Error category filter")
    p.add_argument("--search", help="Free-text search")


def _get_issue_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--id", required=True, help="Issue case id")


ACTIONS: dict[str, ActionDef] = {
    "get-config": ActionDef(get_config, _get_config_args,
                            description="Read a config block (pipeline/providers/...)."),
    "update-config": ActionDef(update_config, _update_config_args,
                               description="Update a config block from JSON."),
    "reload-config": ActionDef(reload_config,
                               description="Reload all YAML config + knowledge cache."),
    "knowledge-list": ActionDef(knowledge_list, _knowledge_list_args,
                                description="List knowledge modules of a type."),
    "knowledge-get": ActionDef(knowledge_get, _knowledge_get_args,
                               description="Get one knowledge module's content."),
    "knowledge-create": ActionDef(knowledge_create, _knowledge_write_args,
                                  description="Create a new knowledge module."),
    "knowledge-update": ActionDef(knowledge_update, _knowledge_write_args,
                                  description="Update an existing knowledge module."),
    "knowledge-delete": ActionDef(knowledge_delete, _knowledge_get_args,
                                  description="Delete a knowledge module."),
    "build-selftest": ActionDef(build_selftest,
                                description="Compiler health self-test (trivial C#)."),
    "list-users": ActionDef(list_users, description="List all users (admin)."),
    "list-issues": ActionDef(list_issues, _list_issues_args,
                             description="List issue cases (failures), filterable."),
    "get-issue": ActionDef(get_issue, _get_issue_args,
                           description="Full issue-case detail incl. snapshots."),
}
