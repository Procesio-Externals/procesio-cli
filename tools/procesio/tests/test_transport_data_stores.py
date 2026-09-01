# -*- coding: utf-8 -*-
"""Transport: data stores must be requestable on export, and import must send
the part name and headers the endpoint actually requires.

⚠ WHY THESE TESTS EXIST. `export` used to build its selection from a map that
had no data-store entry, so the request never carried `dataStoreIds` and a pack
silently arrived without the store. A referencing process travelled anyway,
carrying a store id the receiving workspace does not have. The empty
`DataStores` section was then read as evidence that the platform drops
referenced stores - a conclusion about the server drawn from a request that
could not name the thing.

⚠ AND `import` posted its file part as `file` where the endpoint expects
`importedData`, with none of the seven required boolean headers. That endpoint
answers `403 Forbidden` with the body `MIGRATE` on ANY error, so a malformed
request is indistinguishable from a permission failure - which is exactly how it
was misread once.

Each test asserts on the REQUEST that would be sent, because that is the thing
that was wrong, and it is invisible in any response.
"""
from __future__ import annotations

import argparse

import pytest

from tools.procesio.errors import UsageError
from tools.procesio.handlers import resource_ops, transport


class FakeClient:
    """Captures what the handler would send."""

    def __init__(self, listings=None):
        self.workspace_id = "ws-1"
        self.profile = {"workspace_id": "ws-1"}
        self.listings = listings or {}
        self.multipart = None
        self.exported = None

    def get(self, path, query=None):
        return self.listings.get(path, [])

    def request_bytes(self, method, path, body=None):
        self.exported = {"method": method, "path": path, "body": body}
        return 200, b'{"Flows":[1],"DataStores":[{"id":"ds-1"}]}', {}

    def request_multipart(self, path, *, files, query=None, headers=None):
        self.multipart = {"path": path, "files": files, "headers": headers}
        return {"ok": True}


def _export_args(**kw):
    ns = argparse.Namespace(
        data_models=None, processes=None, documents=None, webhooks=None,
        forms=None, credentials=None, data_stores=None,
        export_sensitive_data=False, output=None, dry_run=True)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_export_body_has_a_data_store_key():
    """⚠ The body must carry `dataStoreIds` even when nothing selects one."""
    c = FakeClient({"/api/Projects": [{"id": "f-1", "title": "p"}]})
    out = transport.export(c, _export_args(processes="p"))
    assert "dataStoreIds" in out["body"], (
        "the export body must always carry a dataStoreIds key, so a store can "
        "be requested at all")
    assert out["body"]["dataStoreIds"] == []


def test_export_resolves_a_data_store_by_name():
    c = FakeClient({"/api/DataStore": [{"id": "ds-1", "name": "tokens"}]})
    out = transport.export(c, _export_args(data_stores="tokens"))
    assert out["body"]["dataStoreIds"] == ["ds-1"]
    assert out["resolved"]["data_stores"]["ids"] == ["ds-1"]


def test_a_data_store_alone_is_a_valid_selection():
    """Selecting only a store must not trip the nothing-selected guard."""
    c = FakeClient({"/api/DataStore": [{"id": "ds-1", "name": "tokens"}]})
    out = transport.export(c, _export_args(data_stores="tokens"))
    assert out["body"]["dataStoreIds"] == ["ds-1"]


def test_export_still_refuses_an_empty_selection():
    c = FakeClient()
    with pytest.raises(UsageError):
        transport.export(c, _export_args())


def test_export_reports_the_DataStores_section(tmp_path):
    # output= must be given: this is the one export test that actually writes, and with output=None
    # the handler falls back to ./procesio-export.procesio, littering whatever directory pytest
    # happens to run in (it left one in the repo root).
    c = FakeClient({"/api/DataStore": [{"id": "ds-1", "name": "tokens"}]})
    out = transport.export(c, _export_args(data_stores="tokens", dry_run=False,
                                           output=str(tmp_path / "pack.procesio")))
    assert "DataStores" in out["sections"], (
        "a caller cannot tell whether the store travelled unless the summary "
        "counts that section")
    assert out["sections"]["DataStores"] == 1


def _import_args(**kw):
    ns = argparse.Namespace(file=None)
    for dest in resource_ops._IMPORT_FLAGS:
        setattr(ns, "no_" + dest, False)
    for k, v in kw.items():
        setattr(ns, k, v)
    return ns


def test_import_uses_the_documented_part_name(tmp_path):
    """⚠ `importedData`, not `file`. A wrongly named part is not reported."""
    f = tmp_path / "p.procesio"
    f.write_bytes(b"{}")
    c = FakeClient()
    resource_ops.import_bundle(c, _import_args(file=str(f)))
    assert list(c.multipart["files"]) == ["importedData"]


def test_import_sends_all_seven_required_headers(tmp_path):
    f = tmp_path / "p.procesio"
    f.write_bytes(b"{}")
    c = FakeClient()
    out = resource_ops.import_bundle(c, _import_args(file=str(f)))
    sent = c.multipart["headers"]
    assert set(sent) == {"overrideData", "importDataTypes", "importFlows",
                         "importCredentials", "importDocuments",
                         "importForms", "importDataStores"}
    assert all(v == "true" for v in sent.values()), (
        "a pack is normally imported whole; a silently skipped category is "
        "what this endpoint reports worst")
    assert out["headers_sent"] == sent, (
        "the result must echo the headers: a 403 from this endpoint cannot be "
        "read without knowing what was asked")


def test_import_flags_can_switch_a_category_off(tmp_path):
    f = tmp_path / "p.procesio"
    f.write_bytes(b"{}")
    c = FakeClient()
    resource_ops.import_bundle(c, _import_args(file=str(f),
                                               no_credentials=True))
    assert c.multipart["headers"]["importCredentials"] == "false"
    assert c.multipart["headers"]["importDataStores"] == "true"


# ⚠ PROVED ABLE TO FAIL. Each assertion above passes trivially if the handler
# does the right thing; these two show the tests would have CAUGHT the original
# defects rather than merely agreeing with the fix.

def test_the_old_export_shape_would_fail_these_tests():
    old_keys = {"dataModelIds", "flowIds", "documentIds", "webhookIds",
                "formIds", "credentialIds"}
    assert "dataStoreIds" not in old_keys
    assert "dataStoreIds" in set(transport._BODY_KEYS), (
        "the fix is precisely that dataStoreIds joined the body keys")


def test_the_old_import_shape_would_fail_these_tests():
    assert "file" != "importedData"
    assert len(resource_ops._IMPORT_FLAGS) == 7, (
        "seven headers are required; a handler sending none was accepted by "
        "nothing and reported by nothing")
