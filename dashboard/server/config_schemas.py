"""Per-config validation for the config editor.

Two layers:
  1. A precise JSON Schema for configs where structure matters - notably
     llm/providers.json, which gates every LLM-backed feature. jsonschema
     (already a framework dependency) does the heavy lifting.
  2. A generic pass for every config: it must be a JSON object, and any value
     still holding a template PLACEHOLDER (YOUR-..., REPLACE_ME, <...>) is
     flagged so a half-filled config never reads as ready.

Returns {ok, errors, warnings}. `ok` is False only on a hard schema/JSON error;
leftover placeholders are warnings (the user may be mid-edit).
"""
from __future__ import annotations

import re
from typing import Any

try:
    import jsonschema
except Exception:  # noqa: BLE001 - degrade to generic checks if absent
    jsonschema = None

_PLACEHOLDER = re.compile(r"YOUR[-_ ]|REPLACE|CHANGE[-_ ]?ME|<[^>]+>|xxxxx", re.I)

# component/name (without .json) -> JSON Schema
_SCHEMAS: dict[str, dict] = {
    "llm/providers": {
        "type": "object",
        "required": ["providers"],
        "properties": {
            "comment": {"type": "string"},
            "default": {"type": "string"},
            "providers": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": {
                    "type": "object",
                    "required": ["adapter"],
                    "properties": {
                        "adapter": {"enum": ["openai_compat", "claude_api", "codex_cli"]},
                        "base_url": {"type": "string"},
                        "model": {"type": "string"},
                        "auth_style": {"enum": ["bearer", "api-key", "none"]},
                    },
                },
            },
        },
    },
}


def _walk_placeholders(node: Any, path: str, out: list[str]) -> None:
    if isinstance(node, str):
        if _PLACEHOLDER.search(node):
            out.append(f"{path or '(root)'}: still a placeholder ({node!r})")
    elif isinstance(node, dict):
        for k, v in node.items():
            _walk_placeholders(v, f"{path}.{k}" if path else k, out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_placeholders(v, f"{path}[{i}]", out)


def validate(component: str, name: str, data: Any) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(data, dict):
        return {"ok": False, "errors": ["top-level value must be a JSON object"],
                "warnings": []}

    schema = _SCHEMAS.get(f"{component}/{name}")
    if schema is not None and jsonschema is not None:
        validator = jsonschema.Draft7Validator(schema)
        for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
            loc = ".".join(str(p) for p in err.path) or "(root)"
            errors.append(f"{loc}: {err.message}")
        # cross-field: `default` must name an existing provider
        if component == "llm" and name == "providers":
            default = data.get("default")
            provs = data.get("providers") or {}
            if default and default not in provs:
                errors.append(f"default: {default!r} is not one of the providers "
                              f"({', '.join(provs) or 'none'})")

    _walk_placeholders(data, "", warnings)
    return {"ok": not errors, "errors": errors, "warnings": warnings}


def has_schema(component: str, name: str) -> bool:
    return f"{component}/{name}" in _SCHEMAS
