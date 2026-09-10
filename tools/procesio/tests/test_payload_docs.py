"""A structured argument must publish the contract the tool actually enforces.

`--config` carries the whole resource definition, but argparse can only give it a
one-line `help=`, so the manifest described it as "a JSON object" and a caller holding
only the manifest had to reverse-engineer the shape from validation errors - one layer
per attempt, several turns per resource. The fix publishes the component's own schema
and a working fixture, which means two things can now fall out of step, and these tests
are what stop them:

  * the published schema vs the file `validate_config` enforces - a schema edit that
    is not regenerated would advertise a contract the tool no longer applies;
  * the published example vs that schema - an example that does not validate is worse
    than none, because it is the part a caller copies.
"""
from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from tools._lib.manifest import load_tool
from tools.procesio import main
from tools.procesio.dto import registry as dto_registry
from pathlib import Path


def _manifest():
    return load_tool(Path(main.__file__).resolve().parent / "tool.yaml")


def _config_actions():
    """Every action whose real contract is a structured `--config`."""
    m = _manifest()
    return [a for a in m.actions if any(g.name == "config" for g in a.args)]


def test_there_are_config_driven_actions_to_check():
    """Guards the guard: if the discovery below ever returns nothing, the tests that
    follow would pass vacuously."""
    assert len(_config_actions()) >= 12


@pytest.mark.parametrize("component", sorted(dto_registry.all_components()))
def test_each_component_publishes_its_schema_and_an_example(component):
    m = _manifest()
    for verb in ("create", "edit"):
        spec = m.get_action(f"{component}-{verb}")
        assert spec is not None, f"{component}-{verb} missing from the manifest"
        config_arg = next((g for g in spec.args if g.name == "config"), None)
        assert config_arg is not None, f"{component}-{verb} has no --config"
        assert config_arg.json_schema, (
            f"{component}-{verb} --config publishes no schema; regenerate the manifest")
        assert spec.examples, f"{component}-{verb} publishes no example"


@pytest.mark.parametrize("component", sorted(dto_registry.all_components()))
def test_published_schema_matches_the_file_the_tool_enforces(component):
    """The manifest is generated and committed; the schema on disk is read at every
    validate. Only this comparison keeps a schema edit from silently publishing a stale
    contract until someone happens to regenerate."""
    comp = dto_registry.all_components()[component]
    if not comp.schema_path.exists():
        pytest.skip(f"{component} ships no config schema")
    on_disk = json.loads(comp.schema_path.read_text(encoding="utf-8"))
    spec = _manifest().get_action(f"{component}-create")
    published = next(g for g in spec.args if g.name == "config").json_schema
    assert published == on_disk, (
        f"{component}: the published schema differs from {comp.schema_path.name} - "
        f"run tools/procesio/gen_manifest.py")


@pytest.mark.parametrize("component", sorted(dto_registry.all_components()))
def test_published_example_validates_against_published_schema(component):
    """The example is the part a caller copies, so it has to satisfy the contract it
    ships beside."""
    spec = _manifest().get_action(f"{component}-create")
    schema = next(g for g in spec.args if g.name == "config").json_schema
    if not schema or not spec.examples:
        pytest.skip(f"{component} publishes no schema/example pair")
    errors = sorted(Draft202012Validator(schema).iter_errors(spec.examples[0]),
                    key=lambda e: list(e.path))
    assert not errors, (
        f"{component}: the published example fails its own schema - "
        + "; ".join(f"{'/'.join(str(p) for p in e.path) or '(root)'}: {e.message}"
                    for e in errors[:5]))
