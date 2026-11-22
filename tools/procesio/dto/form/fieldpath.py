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

import re

from tools.procesio.errors import UsageError

# The platform's "fields" container id. Constant across every form (verified against real
# production forms); it is not read from the form and must not be.
FIELDS_NS = "11223344-5566-7788-99aa-aabbccddeeff"

# The config key that carries a control's value, where it is not `value`. A `file-viewer` has
# no `value` config at all — its content lives in `src` (type url-or-file).
VALUE_CONFIG_KEY = {"file-viewer": "src"}

SEGMENTS = 4

# A Data Store event keeps a typed value and a form value in the same place: the right side of
# a map row is text, and the form runtime reads as a form value only the parts of it that are a
# chain of ids starting at a form variable (form-runtime getFormVariablesAttributeValue). Any
# other text is sent as it is written. So the question "is this a path or a value" has to be
# answered here, from the text alone.
_GUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_GUID_ONLY = re.compile(rf"^{_GUID}$")
_ID_CHAIN = re.compile(rf"{_GUID}(?:\.{_GUID})+")
_DOTTED_TOKEN = re.compile(r"^[\w-]+(?:\.[\w-]+)+$")

# Where a list of rows lands. A table shows them through its dynamic row's source, a dropdown
# through its own; both are the `sourceValue` config.
SOURCE_KEY = "sourceValue"
_TABLE, _DYNAMIC_ROW, _STATIC_ROW = "table", "dynamic-table-row", "static-table-row"


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


def _config_text(element: dict, key: str):
    for c in element.get("configs") or []:
        if c.get("key") == key:
            v = str(c.get("value") or "").strip()
            return v or None
    return None


def _name_of(element: dict):
    return _config_text(element, "name")


class LiveForm:
    """The field index of a form as it exists on the server: what its root is, which
    elements it has, and each one's value-config id."""

    def __init__(self, form: dict):
        data = (form or {}).get("data") or {}
        self.root_id = str(((data.get("dataModel") or {}).get("id")) or "")
        self.elements = data.get("elements") or []
        self.by_id: dict[str, dict] = {}
        self.by_name: dict[str, list[dict]] = {}
        # The `id` config: the DOM id the element carries on the page. It is the handle a caller
        # holds after reading the form's script, where the name never appears.
        self.by_dom_id: dict[str, list[dict]] = {}
        for el in self.elements:
            eid = el.get("id")
            if not eid:
                continue
            self.by_id[str(eid)] = el
            name = _name_of(el)
            if name:
                self.by_name.setdefault(name, []).append(el)
            dom_id = _config_text(el, "id")
            if dom_id:
                self.by_dom_id.setdefault(dom_id, []).append(el)
        # Form variables (Offer_ID, isConfirmed…) are mapped by their own id, and the form's
        # data model also carries the platform's `instance` tree (instance.currentUser.email…),
        # addressed as root.<attr id>.<attr id>…; both are as valid on a map row as a field.
        self.variables: dict[str, dict] = {}
        self.variable_ids: dict[str, dict] = {}
        for v in data.get("variables") or []:
            if not v.get("id") or not v.get("name") or v.get("name") == "form":
                continue                      # `form` is the data-model handle, not a value
            self.variables[str(v["name"])] = v
            self.variable_ids[str(v["id"])] = v
        self.model = data.get("dataModel") or {}

    def is_variable(self, value) -> bool:
        return isinstance(value, str) and value in self.variable_ids

    def variable_for(self, value):
        """`@Name`, or a bare name no field carries, or the variable's id -> the variable."""
        if not isinstance(value, str):
            return None
        if value.startswith("@"):
            return self.variables.get(value[1:])
        if value in self.variable_ids:
            return self.variable_ids[value]
        if value not in self.by_name:
            return self.variables.get(value)
        return None

    def model_path(self, value):
        """A dotted NAME path into the form's data model (instance.currentUser.email) -> its
        id path, or None when the first name is not a top-level attribute of the model."""
        if not isinstance(value, str) or "." not in value or not self.root_id:
            return None
        names = value.split(".")
        attrs, ids = self.model.get("attributes") or [], []
        for i, nm in enumerate(names):
            hit = next((a for a in attrs if a.get("name") == nm), None)
            if hit is None:
                if i == 0:
                    return None
                known = ", ".join(sorted(a.get("name", "") for a in attrs)) or "(none)"
                raise UsageError(f"{value!r}: {nm!r} is not an attribute of "
                                 f"{'.'.join(names[:i])!r}; it has: {known}")
            ids.append(str(hit["id"]))
            attrs = hit.get("attributes") or []
        return ".".join([self.root_id] + ids)

    def _model_ids_ok(self, path: str) -> bool:
        parts = str(path).split(".")
        if len(parts) < 2 or parts[0] != self.root_id or parts[1] == FIELDS_NS:
            return False
        attrs = self.model.get("attributes") or []
        for pid in parts[1:]:
            hit = next((a for a in attrs if str(a.get("id")) == pid), None)
            if hit is None:
                return False
            attrs = hit.get("attributes") or []
        return True

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

    def element(self, ref: str) -> dict:
        """One element by id, else by its unique `name` config."""
        if ref in self.by_id:
            return self.by_id[ref]
        els = self.by_name.get(ref) or []
        if len(els) == 1:
            return els[0]
        if not els:
            raise UsageError(f"{ref!r} is not an element on this form (by id or name)")
        raise UsageError(f"{len(els)} elements are named {ref!r}; pass the element id instead")

    def config_path(self, ref: str, key: str) -> str:
        """The path of ANY config of an element (`disabled`, `visible`, `label`…), not only its
        value. A MAP_FORM_DATA row and a condition address a config the same way a process
        addresses the value: the fourth segment is that config's own id, which the data model
        reuses as the attribute id. Same failure mode as a wrong value path, so same refusal."""
        el = self.element(ref)
        cid = _config_id(el, key)
        if not cid:
            keys = ", ".join(c.get("key", "") for c in el.get("configs") or []
                             if not str(c.get("key", "")).startswith("on"))
            raise UsageError(f"element {ref!r} (type {el.get('type')!r}) has no {key!r} config; "
                             f"it has: {keys}")
        return build(self.root_id, str(el["id"]), str(cid))

    def dom_id_config_path(self, ref: str, key: str, where: str):
        """`<DOM id>.<config key>` -> that config's path, or None when the text is not one.

        An element's id and name are tried before this, as everywhere else. A DOM id counts
        only when `key` is a config of an element that carries it: a new element starts with
        its type's word as its DOM id (`image`, `button`, `input`), so `image.png` on a form
        with one image is far more often a typed value than a config. Several elements may
        share a DOM id; that is refused, never guessed."""
        carriers = self.by_dom_id.get(ref) or []
        if not any(_config_id(e, key) for e in carriers):
            return None
        if len(carriers) > 1:
            names = ", ".join(repr(_name_of(e) or e.get("id")) for e in carriers[:8])
            raise UsageError(
                f"{where}: {len(carriers)} elements carry the DOM id {ref!r} in their `id` "
                f"config ({names}); write {key!r} after the element's name or its element id "
                f"instead")
        return self.config_path(str(carriers[0]["id"]), key)

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
            own_configs = {str(c.get("id")) for c in element.get("configs") or [] if c.get("id")}
            if value_id in own_configs and value_id != str(expected):
                pass                          # a config of THIS element (label, visible, src…)
            elif not expected:
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
        if isinstance(value, str) and value in self.by_name and not value.startswith("@"):
            return self.path_for_name(value)
        var = self.variable_for(value)
        if var is not None:
            return str(var["id"])
        if isinstance(value, str) and self._model_ids_ok(value):
            return value                      # an id path into the instance tree, already valid
        if isinstance(value, str) and value.count(".") == 1:
            ref, key = value.split(".")
            if ref in self.by_id or ref in self.by_name:   # Paragraph9.label, Section3.visible
                return self.config_path(ref, key)
            by_dom_id = self.dom_id_config_path(ref, key, where)
            if by_dom_id is not None:
                return by_dom_id
        mp = self.model_path(value)
        if mp is not None:
            return mp
        if looks_like_path(value):
            self.check(value, where)
            return value
        raise UsageError(
            f"{where}: {value!r} is neither a field on this form, a form variable (@name), a "
            f"data-model path (instance.currentUser.email) nor a full value path. "
            f"Fields that can carry a value: {', '.join(self.field_names()) or '(none)'}; "
            f"variables: {', '.join(sorted(self.variables)) or '(none)'}")

    # -- the form side of a Data Store event ------------------------------------------------
    #
    # A process map row has a form value on its right and nothing else, so `resolve` can refuse
    # whatever is not one. A Data Store row cannot: its right side is a form value OR a typed
    # value ("50", "open"), and the runtime tells them apart by shape alone. A path that is
    # nearly right is therefore not an error anywhere: the runtime sends its text as the value.

    def _is_path_attempt(self, text: str) -> bool:
        """One dotted token written as a path, right or wrong: it carries an id or an element
        of this form, or starts at the form's root. `10.0.0.1` and `v1.2` are typed values."""
        if not _DOTTED_TOKEN.match(text):
            return False
        parts = text.split(".")
        return (parts[0] == self.root_id
                or any(_GUID_ONLY.match(p) or p in self.by_id for p in parts))

    def _check_chain(self, path: str, where: str) -> None:
        if self._model_ids_ok(path) or path.split(".")[0] in self.variable_ids:
            return
        self.check(path, where)

    def check_embedded(self, text, where: str) -> None:
        """Raise when a text holds a path the runtime will not read as one. Text with no path
        in it passes: this never decides that a typed value is wrong."""
        if not isinstance(text, str) or not text.strip():
            return
        text = text.strip()
        if self._is_path_attempt(text):
            self._check_chain(text, where)
            return
        for chain in _ID_CHAIN.findall(text):     # "Score: <path>": the runtime reads each part
            self._check_chain(chain, where)

    def resolve_input(self, value, where: str) -> tuple:
        """The right side of a Data Store INPUT row (a column's or a parameter's value) ->
        (the text to store, what it is: field | variable | model | typed | empty).

        A field NAME, an element id, `Element.config`, `@variable` and a data-model name path
        (instance.currentUser.id) are built into the id path the runtime reads. A path is
        checked against the live form. Anything else is a typed value and is kept as written,
        except the spelling that is one letter case away from a field: nobody types that on
        purpose, and stored as text it would be written into every row."""
        if not isinstance(value, str):
            return value, "typed"
        text = value.strip()
        if not text:
            return "", "empty"
        if text in self.by_name:
            return self.path_for_name(text), "field"
        if text.startswith("@"):
            var = self.variables.get(text[1:])
            if var is None:
                raise UsageError(
                    f"{where}: {text!r} names no form variable (variables: "
                    f"{', '.join(sorted(self.variables)) or 'none'}). To send the text itself, "
                    f"pass it as `value` instead of `right`.")
            return str(var["id"]), "variable"
        if text in self.variable_ids:
            return text, "variable"
        if text in self.by_id:
            return self.config_path(text, value_key(self.by_id[text].get("type"))), "field"
        if self._model_ids_ok(text):
            return text, "model"
        if text.count(".") == 1:
            ref, key = text.split(".")
            if ref in self.by_id or ref in self.by_name:
                return self.config_path(ref, key), "field"
            by_dom_id = self.dom_id_config_path(ref, key, where)
            if by_dom_id is not None:
                return by_dom_id, "field"
        named = self.model_path(text)
        if named is not None:
            return named, "model"
        if self._is_path_attempt(text):
            self._check_chain(text, where)
            return text, "field"
        self.check_embedded(text, where)
        near = sorted(n for n in self.by_name if n.casefold() == text.casefold())
        if near:
            raise UsageError(
                f"{where}: {text!r} is not a field on this form, but {near[0]!r} is. Spell the "
                f"name as the form has it, or pass the text as `value` instead of `right` to "
                f"send it as a typed value.")
        return value, "typed"

    def _named_element(self, text: str):
        """(the element a right side names, the config id it names or None): by name, by id,
        or as the third segment of a four-segment path."""
        if text in self.by_name or text in self.by_id:
            return self.element(text), None
        parts = text.split(".")
        if len(parts) == SEGMENTS and parts[2] in self.by_id:
            return self.by_id[parts[2]], parts[3]
        return None, None

    def resolve_rows_target(self, value, where: str) -> tuple:
        """Where a list of rows goes -> (the path to store, warnings).

        A table shows rows through the `sourceValue` of its DYNAMIC ROW and a dropdown through
        its own. Mapped to a table's or a row's `value`, every result adds a row with all cells
        empty and nothing reports it, so a table, its row or a path into either is turned into,
        or checked against, the one path that works."""
        text = str(value).strip()
        element, config_id = self._named_element(text)
        if element is None:
            return self.resolve(text, where), []
        name = _name_of(element) or element.get("id")
        if element.get("type") == _STATIC_ROW:
            raise UsageError(f"{where}: {name!r} is a static table row, which has no source to "
                             f"fill. Rows go to the table's dynamic row.")
        if element.get("type") == _TABLE:
            rows = [e for e in self.elements
                    if e.get("parentId") == element.get("id") and e.get("type") == _DYNAMIC_ROW]
            if not rows:
                raise UsageError(
                    f"{where}: table {name!r} has no dynamic row, so it cannot show a list of "
                    f"rows. Give the table a dynamic row first.")
            if len(rows) > 1:
                names = ", ".join(repr(_name_of(r) or r.get("id")) for r in rows)
                raise UsageError(f"{where}: table {name!r} has {len(rows)} dynamic rows "
                                 f"({names}); name the one that takes the rows.")
            element = rows[0]
        source_id = _config_id(element, SOURCE_KEY)
        if element.get("type") == _DYNAMIC_ROW:
            if not source_id:
                raise UsageError(
                    f"{where}: dynamic row {_name_of(element) or element.get('id')!r} has no "
                    f"{SOURCE_KEY!r} config, so no list can be mapped to it. Rebuild the table "
                    f"with form-edit, which declares it.")
            right = build(self.root_id, str(element["id"]), str(source_id))
            if config_id is not None and text != right:
                raise UsageError(
                    f"{where}: {text!r} is not where a list of rows goes. A table shows rows "
                    f"through its dynamic row's {SOURCE_KEY!r}; mapped to the table's or the "
                    f"row's `value`, each result adds a row with every cell empty.\n"
                    f"  correct path: {right}\n  or just pass the name: {name}")
            return right, []
        if config_id is not None:                 # a full path to another control: as written
            self.check(text, where)
            return text, []
        if not source_id:                         # a plain field, by name: its value
            return self.config_path(text, value_key(element.get("type"))), []
        source_type = next((c for c in element.get("configs") or []
                            if c.get("key") == "sourceType"), None)
        warnings = []
        if not (source_type or {}).get("value"):
            warnings.append(
                f"{name!r} takes the rows as its options, but it has no source type, so the "
                f"runtime builds no option and the control says \"No data available\". Set its "
                f"`sourceType` config to JSON.")
        return build(self.root_id, str(element["id"]), str(source_id)), warnings
