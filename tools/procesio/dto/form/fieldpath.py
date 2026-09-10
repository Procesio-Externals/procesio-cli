"""The one definition of a form FIELD VALUE PATH — how it is built, and what makes one valid.

A process addresses a form field by a four-segment path:

    {formDataModelRootId}.{FIELDS_NS}.{elementId}.{valueConfigId}

Two places produce such a path and they must not drift: the DTO builder writes them while
BUILDING a form from a config (it knows every id it just minted), and `form-set-element-event`
has to check or produce them against a LIVE form it fetched. The builder's rule lived only in
its own build pass, so the surgical action could not reuse it and simply passed whatever the
caller sent straight through.

Why a wrong path is worth this much code: nothing rejects it. The API accepts the row and
answers `updated: true`, the designer renders the mapping, and the control silently launches
nothing — measured across five autonomous builds, every one of which wrote
`root.fields.<elementId>.value`, substituting the NAMES from the guide's tree diagram for the
ids printed beside them. There is no error to read, so the only place the mistake can be caught
is before the write.
"""
from __future__ import annotations

from tools.procesio.errors import UsageError

# The platform's "fields" container id. Constant across every form (verified against real
# production forms); it is not read from the form and must not be.
FIELDS_NS = "11223344-5566-7788-99aa-aabbccddeeff"

# The config key that carries a control's value, where it is not `value`. A `file-viewer` has
# no `value` config at all — its content lives in `src` (type url-or-file).
VALUE_CONFIG_KEY = {"file-viewer": "src"}

SEGMENTS = 4


def value_key(el_type) -> str:
    """The config key holding this control's field value."""
    return VALUE_CONFIG_KEY.get(el_type, "value")


def build(root_id: str, element_id: str, value_config_id: str) -> str:
    return f"{root_id}.{FIELDS_NS}.{element_id}.{value_config_id}"


def looks_like_path(value) -> bool:
    """A caller that sent a path rather than a field name — right or wrong.

    Deliberately shape-only: this asks WHICH branch to take, never whether the path is
    correct. Treating "has dots" as "is valid" is exactly the hole that let the invented
    `root.fields.<id>.value` through untouched.
    """
    return isinstance(value, str) and value.count(".") == SEGMENTS - 1


def _config_id(element: dict, key: str):
    for c in element.get("configs") or []:
        if c.get("key") == key:
            return c.get("id")
    return None


def _name_of(element: dict):
    for c in element.get("configs") or []:
        if c.get("key") == "name":
            v = str(c.get("value") or "").strip()
            return v or None
    return None


class LiveForm:
    """The field index of a form as it exists on the server: what its root is, which
    elements it has, and each one's value-config id."""

    def __init__(self, form: dict):
        data = (form or {}).get("data") or {}
        self.root_id = str(((data.get("dataModel") or {}).get("id")) or "")
        self.elements = data.get("elements") or []
        self.by_id: dict[str, dict] = {}
        self.by_name: dict[str, list[dict]] = {}
        for el in self.elements:
            eid = el.get("id")
            if not eid:
                continue
            self.by_id[str(eid)] = el
            name = _name_of(el)
            if name:
                self.by_name.setdefault(name, []).append(el)

    def value_config_id(self, element: dict):
        return _config_id(element, value_key(element.get("type")))

    def field_names(self) -> list[str]:
        """Names of the elements that can actually carry a value — the only ones a map row
        may point at, so an error message must not offer the others."""
        return sorted(n for n, els in self.by_name.items()
                      if any(self.value_config_id(e) for e in els))

    def path_for_name(self, name: str) -> str:
        els = self.by_name.get(name) or []
        if not els:
            raise UsageError(
                f"{name!r} is not a field on this form. Fields that can carry a value: "
                f"{', '.join(self.field_names()) or '(none)'}")
        if len(els) > 1:
            raise UsageError(
                f"{len(els)} elements are named {name!r}; pass the element id or the full "
                f"value path instead")
        el = els[0]
        vcid = self.value_config_id(el)
        if not vcid:
            raise UsageError(
                f"element {name!r} (type {el.get('type')!r}) has no "
                f"{value_key(el.get('type'))!r} config, so it holds no value and cannot be "
                f"mapped")
        return build(self.root_id, str(el["id"]), str(vcid))

    def check(self, path: str, where: str) -> None:
        """Raise unless `path` addresses a real value-bearing field of THIS form.

        Every segment is checked against the live form and the message names the right
        answer: a caller that guessed the shape has no other way to learn it, because the
        platform accepts the wrong one without complaint.
        """
        parts = str(path).split(".")
        problems: list[str] = []
        if len(parts) != SEGMENTS:
            raise UsageError(
                f"{where}: {path!r} is not a form value path. It must have {SEGMENTS} "
                f"segments: {{formDataModelRootId}}.{{FIELDS_NS}}.{{elementId}}."
                f"{{valueConfigId}} — or pass the field NAME instead and it will be "
                f"resolved for you. Fields: {', '.join(self.field_names()) or '(none)'}")

        root, ns, element_id, value_id = parts
        if root != self.root_id:
            problems.append(f"segment 1 {root!r} must be this form's data-model root "
                            f"{self.root_id!r}")
        if ns != FIELDS_NS:
            problems.append(f"segment 2 {ns!r} must be the fields container id {FIELDS_NS!r}")

        element = self.by_id.get(element_id)
        if element is None:
            problems.append(f"segment 3 {element_id!r} is not an element on this form")
        else:
            expected = self.value_config_id(element)
            if not expected:
                problems.append(
                    f"segment 3 {element_id!r} is a {element.get('type')!r}, which has no "
                    f"{value_key(element.get('type'))!r} config and holds no value")
            elif value_id != str(expected):
                # The subtle one: four guid-shaped segments, but the value id belongs to a
                # different element. Nothing downstream notices.
                problems.append(f"segment 4 {value_id!r} must be that element's own "
                                f"{value_key(element.get('type'))!r} config id {expected!r}")

        if not problems:
            return

        hint = ""
        if element is not None and self.value_config_id(element):
            correct = build(self.root_id, element_id, str(self.value_config_id(element)))
            name = _name_of(element)
            hint = f"\n  correct path: {correct}"
            if name:
                hint += f"\n  or just pass the field name: {name}"
        else:
            hint = ("\n  pass the field NAME instead and it will be resolved: "
                    + (", ".join(self.field_names()) or "(no value-bearing fields)"))

        raise UsageError(f"{where}: {path!r} is not a valid value path on this form.\n  "
                         + "\n  ".join(problems) + hint)

    def resolve(self, value, where: str) -> str:
        """A map row's form side -> a validated value path.

        Three inputs, three outcomes: a known field NAME is built into its path; a path is
        checked and passed through; anything else is refused with the field list. The middle
        case is the one that matters — it is what every observed failure sent.
        """
        if isinstance(value, str) and value in self.by_name:
            return self.path_for_name(value)
        if looks_like_path(value):
            self.check(value, where)
            return value
        raise UsageError(
            f"{where}: {value!r} is neither a field on this form nor a full value path. "
            f"Fields that can carry a value: "
            f"{', '.join(self.field_names()) or '(none)'}")
