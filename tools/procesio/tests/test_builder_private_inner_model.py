"""A path into a PRIVATE inner model must resolve.

"Create from JSON" turns every nested object of the sample into a private model that lives only
inside its parent. `GET /api/DataTypes/{id}` on that inner model answers 400 "Requested data type
not found!", so a builder that fetched each child model on its own could not index it, and a
binding such as `{"var": "order", "path": ["customer", "name"]}` wrote the NAME "name" into
`attribute.attributeId`. The API then refused the whole save (`Error converting value "name" to
type 'System.Guid'`). The parent returns the inner model's attributes inline, so those are used.
"""
from __future__ import annotations

from tools.procesio.dto.process import builder

ORDER_ID = "11111111-1111-1111-1111-111111111111"
CUSTOMER_ID = "22222222-2222-2222-2222-222222222222"
CUSTOMER_ATTR = "aaaaaaaa-0000-0000-0000-000000000001"
NAME_ATTR = "bbbbbbbb-0000-0000-0000-000000000001"


class _Client:
    """Answers like the live API: the parent model reads fine, its private child does not."""

    def get(self, path, params=None):
        if path == "/api/DataTypes":
            return {"pageItems": [{"id": ORDER_ID, "name": "order"}]}
        if path == f"/api/DataTypes/{ORDER_ID}":
            return {"result": {"id": ORDER_ID, "attributes": [
                {"id": CUSTOMER_ATTR, "name": "customer", "dataTypeId": CUSTOMER_ID,
                 "isDataModel": True, "isPublic": False,
                 "attributes": [{"id": NAME_ATTR, "name": "name", "isDataModel": False,
                                 "dataTypeId": "0317bfee-b2f5-4bde-bfe8-121212121214"}]},
            ]}}
        raise RuntimeError(f"HTTP 400 Requested data type not found! ({path})")


def _no_catalog(*_a, **_k):
    raise RuntimeError("offline")


def test_a_private_inner_model_is_indexed_from_its_parent(monkeypatch):
    monkeypatch.setattr(builder, "_fetch_live_catalog", _no_catalog)
    monkeypatch.setattr(builder, "_fetch_custom_actions", _no_catalog)
    ctx = builder.prepare_ctx(_Client(), {"variables": [
        {"name": "order", "model": "order", "direction": "input"}]})

    assert ctx["model_attrs"][CUSTOMER_ID]["name"]["id"] == NAME_ATTR

    ctx["var_ids"] = {"order": "var-order"}
    chain = builder._attr_chain(["customer", "name"], ctx["var_models"]["order"], ctx)
    assert chain == {"attributeId": CUSTOMER_ATTR,
                     "nextAttribute": {"attributeId": NAME_ATTR, "nextAttribute": None}}
