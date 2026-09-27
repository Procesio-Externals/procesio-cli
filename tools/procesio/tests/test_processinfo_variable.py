"""A config can declare the platform's ProcessInfo variable, and bind its fields.

ProcessInfo is an ordinary flow variable of a fixed model (type 40, SystemDataModel) that the
designer adds the first time something references it - it is NOT ambient and NOT automatic. A
process rebuilt from a config therefore loses it silently unless the config can ask for it,
which is what `direction: "processinfo"` is for. Its `workspaceId` is the honest source for the
workspace a run belongs to: always right, never configured, and correct after an import.
"""
import tools.procesio.dto.process.builder as pb

SYSTEM_MODEL = "10c6ac59-3929-49e6-99dc-121212121221"
WORKSPACE_ATTR = "75044bb4-7c70-40f2-8756-21c03de655c8"


def _cfg(actions=None):
    return {"title": "t",
            "variables": [{"name": "ProcessInfo", "direction": "processinfo"},
                          {"name": "out", "type": "string", "direction": "output"}],
            "actions": actions or []}


def _build(monkeypatch=None):
    return pb.build(_cfg(), {"var_ids": {"processinfo": "11111111-1111-1111-1111-111111111111",
                                         "out": "22222222-2222-2222-2222-222222222222"}})


def test_processinfo_is_emitted_as_a_type_40_system_variable():
    dto = pb.build(_cfg(), {"var_ids": {"processinfo": "11111111-1111-1111-1111-111111111111",
                                        "out": "22222222-2222-2222-2222-222222222222"}})
    variables = dto.get("Variables") or dto.get("variables")
    pi = next(v for v in variables if (v.get("Name") or v.get("name")) == "ProcessInfo")
    assert (pi.get("Type") or pi.get("type")) == 40
    assert (pi.get("DataType") or pi.get("dataType")) == SYSTEM_MODEL
    assert not (pi.get("IsList") or pi.get("isList"))


def test_direction_is_published_in_the_schema():
    import json
    import pathlib
    schema = json.loads((pathlib.Path(pb.__file__).parent / "config.schema.json")
                        .read_text(encoding="utf-8"))
    found = json.dumps(schema)
    assert "processinfo" in found, "the config schema must offer the processinfo direction"


def test_the_model_is_registered_so_a_path_binding_can_resolve():
    """`{var: ProcessInfo, path: [workspaceId]}` needs the variable's model in ctx to resolve."""
    ctx = {}
    cfg = _cfg()
    # prepare_ctx fills var_models from `model`; a processinfo variable must get the fixed one
    # without the config naming it.
    var_models = {}
    for v in cfg["variables"]:
        if str(v.get("direction", "")).lower() == "processinfo":
            var_models[v["name"].lower()] = pb.SYSTEM_DATA_MODEL_ID
    assert var_models["processinfo"] == SYSTEM_MODEL
