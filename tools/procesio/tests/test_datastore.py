"""Data Store curated actions — faked client boundary (zero live HTTP).

Mirrors tests/test_schedules.py: a FakeSession records every HTTP call and serves
canned responses, so we assert the method, URL, query, and body each Data Store
action emits — including the recursive filter-tree the read/update/delete paths build
and the raw escape hatches. Contract verified against PROCESIO/Web-Api main (2026-08).
"""
from __future__ import annotations

import pytest

from tools.procesio import errors, main
from tools.procesio.client import ProcesioClient
from tools.procesio.tests.conftest import FakeResp, FakeSession


def _builder(profile, session):
    return lambda prof: ProcesioClient(profile=profile, name="t", session=session)


APIKEY = {"type": "apikey", "key": "N", "value": "V"}
DS = "11111111-1111-1111-1111-111111111111"


def _last(sess):
    return sess.calls[-1]


# -- metadata / schema ------------------------------------------------------

def test_create_posts_payload():
    sess = FakeSession(queue=[FakeResp(200, {"id": "NEW"})])
    out = main.dispatch("datastore-create",
                        ["--payload", '{"name":"Clients","columns":[]}'],
                        client_builder=_builder(APIKEY, sess))
    assert out["result"] == {"id": "NEW"}
    c = _last(sess)
    assert c["method"] == "POST" and c["url"].endswith("/api/DataStore")
    assert c["json"] == {"name": "Clients", "columns": []}


def test_update_puts_payload():
    sess = FakeSession(queue=[FakeResp(200, {"ok": True})])
    main.dispatch("datastore-update", ["--payload", '{"id":"D1","name":"C2"}'],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "PUT" and c["url"].endswith("/api/DataStore")
    assert c["json"] == {"id": "D1", "name": "C2"}


def test_modify_column_patches_path():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-modify-column",
                  ["--id", DS, "--payload",
                   '{"originalColumn":{"name":"A"},"updatedColumn":{"name":"B"}}'],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "PATCH"
    assert c["url"].endswith(f"/api/DataStore/{DS}/column")
    assert c["json"]["updatedColumn"] == {"name": "B"}


def test_delete_uses_id_in_path():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-delete", ["--id", DS],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "DELETE" and c["url"].endswith(f"/api/DataStore/{DS}")


def test_get_uses_id_in_path():
    sess = FakeSession(queue=[FakeResp(200, {"id": DS})])
    main.dispatch("datastore-get", ["--id", DS],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["url"].endswith(f"/api/DataStore/{DS}")


def test_list_maps_paging():
    sess = FakeSession(queue=[FakeResp(200, {"pageItems": []})])
    main.dispatch("datastore-list", ["--page", "2", "--page-size", "10", "--search", "x"],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "GET" and c["url"].endswith("/api/DataStore")
    assert c["params"] == {"pageNumber": 2, "pageItemCount": 10, "searchName": "x"}


def test_list_restricted_endpoint():
    sess = FakeSession(queue=[FakeResp(200, [])])
    main.dispatch("datastore-list-restricted", [],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["url"].endswith("/api/DataStore/restricted")


def test_from_data_model_posts():
    sess = FakeSession(queue=[FakeResp(200, {"id": "NEW"})])
    main.dispatch("datastore-from-data-model",
                  ["--payload", '{"dataModelId":"M1","name":"C"}'],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["url"].endswith("/api/DataStore/from-data-model")
    assert c["json"] == {"dataModelId": "M1", "name": "C"}


def test_from_json_posts():
    sess = FakeSession(queue=[FakeResp(200, {"id": "NEW"})])
    main.dispatch("datastore-from-json",
                  ["--payload", '{"name":"C","content":"[]"}'],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["url"].endswith("/api/DataStore/from-json")


def test_get_data_model_path():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-get-data-model", ["--id", DS],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["url"].endswith(f"/api/DataStore/{DS}/data-model")


# -- rows: read (filter tree) -----------------------------------------------

def test_get_rows_builds_filter_tree_and_query_paging():
    sess = FakeSession(queue=[FakeResp(200, {"rows": {"pageItems": []}})])
    main.dispatch("datastore-get-rows",
                  ["--id", DS, "--page", "1", "--page-size", "50",
                   "--filters", '[{"column":"Status","operator":"Contains","value":"A"}]',
                   "--sort", '{"column":"CreatedOn","direction":"desc"}'],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "POST"
    assert c["url"].endswith(f"/api/DataStore/{DS}/rows/filter")
    # pagination is on the query string, NOT the body
    assert c["params"] == {"pageNumber": 1, "pageItemCount": 50}
    assert c["json"]["filter"] == {
        "id": 0, "logic": 1, "items": [
            {"id": 0, "type": 1, "logic": 1,
             "condition": {"id": 0, "column": "Status", "operator": 17, "value": "A"}}]}
    assert c["json"]["sort"] == [{"column": "CreatedOn", "direction": 2}]  # desc=2
    assert "pageNumber" not in c["json"]                                    # not in body


def test_get_rows_between_uses_auxvalue():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-get-rows",
                  ["--id", DS,
                   "--filters", '[{"column":"Age","operator":"between","value":18,"auxValue":65}]'],
                  client_builder=_builder(APIKEY, sess))
    cond = _last(sess)["json"]["filter"]["items"][0]["condition"]
    assert cond["operator"] == 7 and cond["value"] == 18 and cond["auxValue"] == 65


def test_get_rows_logic_or():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-get-rows",
                  ["--id", DS, "--logic", "or",
                   "--filters", '[{"column":"A","operator":"equals","value":1},'
                                '{"column":"B","operator":"equals","value":2}]'],
                  client_builder=_builder(APIKEY, sess))
    grp = _last(sess)["json"]["filter"]
    assert grp["logic"] == 2 and len(grp["items"]) == 2 and grp["items"][1]["logic"] == 2


def test_get_rows_accepts_numeric_operator():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-get-rows",
                  ["--id", DS, "--filters", '[{"column":"N","operator":1,"value":"x"}]'],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["json"]["filter"]["items"][0]["condition"]["operator"] == 1


def test_get_rows_rejects_unknown_operator():
    with pytest.raises(errors.UsageError):
        main.dispatch("datastore-get-rows",
                      ["--id", DS, "--filters", '[{"column":"N","operator":"wat"}]'],
                      client_builder=_builder(APIKEY, FakeSession()))


def test_get_rows_condition_requires_column():
    with pytest.raises(errors.UsageError):
        main.dispatch("datastore-get-rows",
                      ["--id", DS, "--filters", '[{"operator":"equals","value":1}]'],
                      client_builder=_builder(APIKEY, FakeSession()))


def test_get_rows_raw_filter_group_overrides():
    sess = FakeSession(queue=[FakeResp(200, {})])
    grp = '{"id":0,"logic":2,"items":[{"id":0,"type":2,"logic":1,"group":{"id":1,"logic":1,"items":[]}}]}'
    main.dispatch("datastore-get-rows", ["--id", DS, "--filter", grp],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["json"]["filter"]["items"][0]["type"] == 2   # nested group, verbatim


def test_get_rows_raw_body_overrides():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-get-rows",
                  ["--id", DS, "--body", '{"custom":true}'],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["json"] == {"custom": True}


def test_get_rows_no_filter_reads_all():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-get-rows", ["--id", DS],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["json"] is None                                  # empty body = read all
    assert c["params"] == {"pageNumber": 1, "pageItemCount": 50}


# -- rows: add / update / delete --------------------------------------------

def test_add_rows_wraps_rows_key():
    sess = FakeSession(queue=[FakeResp(200, {"affectedRows": 2})])
    main.dispatch("datastore-add-rows",
                  ["--id", DS, "--rows", '[{"Name":"a"},{"Name":"b"}]'],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "POST" and c["url"].endswith(f"/api/DataStore/{DS}/rows")
    assert c["json"] == {"rows": [{"Name": "a"}, {"Name": "b"}]}


def test_add_rows_rejects_non_array():
    with pytest.raises(errors.UsageError):
        main.dispatch("datastore-add-rows", ["--id", DS, "--rows", '{"Name":"a"}'],
                      client_builder=_builder(APIKEY, FakeSession()))


def test_update_row_values_and_filter():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-update-row",
                  ["--id", DS, "--values", '{"Status":"Done"}',
                   "--filters", '[{"column":"Id","operator":"equals","value":"1"}]'],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "PUT" and c["url"].endswith(f"/api/DataStore/{DS}/rows")
    assert c["json"]["values"] == {"Status": "Done"}
    assert c["json"]["filter"]["items"][0]["condition"] == {
        "id": 0, "column": "Id", "operator": 1, "value": "1"}


def test_update_row_requires_values():
    with pytest.raises(errors.UsageError):
        main.dispatch("datastore-update-row",
                      ["--id", DS, "--filters", '[{"column":"Id","operator":"equals","value":"1"}]'],
                      client_builder=_builder(APIKEY, FakeSession()))


def test_update_row_requires_filter():
    with pytest.raises(errors.UsageError, match="filter"):
        main.dispatch("datastore-update-row", ["--id", DS, "--values", '{"Status":"Done"}'],
                      client_builder=_builder(APIKEY, FakeSession()))


def test_update_row_raw_body_overrides():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-update-row", ["--id", DS, "--body", '{"raw":1}'],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["json"] == {"raw": 1}


def test_delete_rows_wraps_filter():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-delete-rows",
                  ["--id", DS, "--filters", '[{"column":"Id","operator":"equals","value":"1"}]'],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "DELETE" and c["url"].endswith(f"/api/DataStore/{DS}/rows")
    assert c["json"]["filter"]["items"][0]["condition"]["column"] == "Id"


def test_delete_rows_requires_filter():
    with pytest.raises(errors.UsageError, match="filter"):
        main.dispatch("datastore-delete-rows", ["--id", DS],
                      client_builder=_builder(APIKEY, FakeSession()))


# -- CSV --------------------------------------------------------------------

def test_export_start_posts_no_body():
    sess = FakeSession(queue=[FakeResp(200, {"jobId": "J1"})])
    main.dispatch("datastore-export-start", ["--id", DS],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "POST"
    assert c["url"].endswith(f"/api/DataStore/{DS}/export-start")
    assert c["json"] is None


def test_export_download_writes_bytes(tmp_path):
    out = tmp_path / "rows.csv"
    sess = FakeSession(queue=[FakeResp(200, content=b"a,b\n1,2\n")])
    res = main.dispatch("datastore-export-download",
                        ["--id", DS, "--job-id", "J1", "--out", str(out)],
                        client_builder=_builder(APIKEY, sess))
    assert out.read_bytes() == b"a,b\n1,2\n"
    assert res["result"]["bytes"] == 8
    assert _last(sess)["url"].endswith(f"/api/DataStore/{DS}/export-download/J1")


def test_import_start_sends_multipart(tmp_path):
    csv = tmp_path / "in.csv"
    csv.write_bytes(b"Name\nx\n")
    sess = FakeSession(queue=[FakeResp(200, {"jobId": "J2"})])
    main.dispatch("datastore-import-start", ["--id", DS, "--file", str(csv)],
                  client_builder=_builder(APIKEY, sess))
    c = _last(sess)
    assert c["method"] == "POST"
    assert c["url"].endswith(f"/api/DataStore/{DS}/import-start")
    assert c["files"]["file"][0] == "in.csv"


def test_import_failures_get_path():
    sess = FakeSession(queue=[FakeResp(200, {"failures": []})])
    main.dispatch("datastore-import-failures", ["--id", DS, "--job-id", "J2"],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["url"].endswith(f"/api/DataStore/{DS}/import-failures/J2")


# -- provisioning timeout ----------------------------------------------------

def test_provisioning_ops_use_longer_timeout():
    sess = FakeSession(queue=[FakeResp(200, {"id": "NEW"})])
    main.dispatch("datastore-create", ["--payload", '{"name":"C","columns":[]}'],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["timeout"] == 300          # table provisioning gets a longer budget


def test_row_reads_use_default_timeout():
    sess = FakeSession(queue=[FakeResp(200, {})])
    main.dispatch("datastore-get-rows", ["--id", DS],
                  client_builder=_builder(APIKEY, sess))
    assert _last(sess)["timeout"] == 60           # row reads are fast: default read timeout


# -- B-048 cluster 4a: add-attribute must not silently destroy a store -------

_MODEL = "22222222-2222-2222-2222-222222222222"


def _add_attr(session, extra=None):
    argv = ["--id", _MODEL, "--name", "x", "--data-type", "string"] + (extra or [])
    return main.dispatch("datatype-add-attribute", argv,
                         client_builder=_builder(APIKEY, session))


def test_add_attribute_warns_when_model_backs_a_store():
    # GET /api/DataStore -> one store whose data-model IS the target model: the add still
    # PROCEEDS (4a did not reproduce live) but carries a caution to verify the store after.
    s = FakeSession(queue=[
        FakeResp(200, {"data": [{"id": DS}]}),   # store list
        FakeResp(200, {"id": _MODEL}),           # its data-model == target
        FakeResp(200, {}),                       # POST attribute
        FakeResp(200, {"attributes": []}),       # re-GET model
    ])
    out = _add_attr(s)
    assert out["added"] is True and "warning" in out and DS in out["warning"]


def test_add_attribute_proceeds_clean_when_no_store_backs_the_model():
    # GET /api/DataStore -> empty -> no caution -> POST + re-GET the model.
    s = FakeSession(queue=[
        FakeResp(200, {"data": []}),
        FakeResp(200, {}),                       # POST attribute
        FakeResp(200, {"attributes": []}),       # re-GET model
    ])
    out = _add_attr(s)
    assert out["added"] is True and "warning" not in out
    assert any(c["url"].endswith("/api/DataStore") for c in s.calls)


def test_add_attribute_force_skips_the_store_check_entirely():
    # --force -> no /api/DataStore read at all, straight to POST + re-GET.
    s = FakeSession(queue=[
        FakeResp(200, {}),                       # POST attribute
        FakeResp(200, {"attributes": []}),       # re-GET model
    ])
    out = _add_attr(s, ["--force"])
    assert out["added"] is True and "warning" not in out
    assert not any("/api/DataStore" in c["url"] for c in s.calls)
