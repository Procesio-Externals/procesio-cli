"""A declared tool surface: what every server that publishes one has in common.

A declaration is a YAML file that lists named tools, each mapped to one registered action,
with the arguments it exposes. Two servers publish one: chat_server.py for a general chat
client and platform_server.py for the PROCESIO assistant. They differ in which tools they
list, to whom, and what they do when a call fails. Turning a declaration into the tool
list a client receives, mapping a caller's arguments back to flags, and holding a result
to a size are the same for both, and that is all this module does.

Pure: the same declaration in gives the same output, and nothing here runs a tool. It
imports no server, and neither bridge nor gate, so a change to one surface cannot reach
the other through it.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml


def load(path: Path) -> dict:
    """Parse one declaration file."""
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def exposed_name(arg: dict) -> str:
    """The name a caller uses. CLI flags are kebab-case; a model reaches for
    snake_case and gets it wrong the other way round, so the mapping is explicit
    rather than left to whoever is calling."""
    return arg.get("expose") or arg["flag"].replace("-", "_")


def arg_schema(arg: dict) -> dict:
    """One argument as a JSON Schema property.

    `type` and `description` always. A list says what its items are, and a declaration
    may narrow a value with `enum` or give a whole `schema` for a structured argument:
    a client checks a call against these before it sends it, so each one is a wrong call
    that never has to be made."""
    out = {"type": arg.get("type", "string"), "description": arg.get("description", "")}
    if out["type"] == "array":
        out["items"] = {"type": arg.get("items", "string")}
    if arg.get("enum"):
        out["enum"] = list(arg["enum"])
    if isinstance(arg.get("schema"), dict):
        out = {**arg["schema"], "description": out["description"] or arg["schema"].get("description", "")}
    return out


def build_tools(surface: dict) -> list[dict]:
    """Turn the declaration into the exact `tools/list` payload.

    Pure: same declaration in, same bytes out. That is what lets a snapshot test
    treat a published contract as reviewable in a diff."""
    common = surface.get("common_args") or {}
    tools = []
    for spec in surface["tools"]:
        props: dict = {}
        required: list[str] = []
        for arg in spec.get("args") or []:
            props[exposed_name(arg)] = arg_schema(arg)
            if arg.get("required"):
                required.append(exposed_name(arg))
        for key in spec.get("common") or []:
            props[key] = arg_schema(dict(common[key]))

        read_only = bool(spec["read_only"])
        title = spec["title"]
        schema: dict = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        tools.append({
            "name": spec["name"],
            "title": title,
            "description": " ".join(spec["description"].split()),
            "inputSchema": schema,
            "annotations": {
                "title": title,
                "readOnlyHint": read_only,
                "destructiveHint": False,   # every declared action is reversible; enforced in CI
                "idempotentHint": read_only,
                "openWorldHint": True,      # all of these reach the PROCESIO platform
            },
        })
    return tools


def flags_by_exposed_name(surface: dict, spec: dict) -> dict:
    """{the name a caller uses: the flag it stands for}, for one declared tool."""
    out = {exposed_name(a): a["flag"] for a in (spec.get("args") or [])}
    for key in spec.get("common") or []:
        out[key] = (surface["common_args"][key])["flag"]
    return out


def narrowing_hint(spec: dict) -> str:
    """Name the arguments this particular tool offers for asking a smaller question.
    A generic 'response too large' tells a model nothing it can act on."""
    names = [exposed_name(a) for a in (spec.get("args") or [])]
    useful = [n for n in names if n in ("search", "page", "page_size", "actions", "node",
                                        "family", "topic", "compact")]
    if useful:
        return f"Ask a narrower question using: {', '.join(useful)}."
    return "Request a single item by id instead of a listing."


def cap(payload: dict, spec: dict, default_limit: int) -> dict:
    """Hold a result to the declared size. A tool result lands directly in a model's
    context, so an unbounded one spends context that the task needed."""
    limit = int(spec.get("max_response_bytes") or default_limit)
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) <= limit:
        return payload
    return {
        "truncated": True,
        "bytes": len(text),
        "max_response_bytes": limit,
        "hint": f"The result was {len(text)} bytes, over the {limit}-byte cap for this "
                f"surface, so it is not returned in full. {narrowing_hint(spec)}",
        "preview": text[:2000],
    }
