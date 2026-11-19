from __future__ import annotations

from agents.procesio import audit
from agents.procesio.tests.conftest import action

START = action("Start")
STOP = action("Stop")


def _codes(findings):
    return {f["code"] for f in findings}


def test_clean_process_has_no_correctness_findings():
    configured = action("Add", params=[{"Value": "x", "Variable": []}],
                        settings=[{"value": "x"}])
    flow = {"Title": "Clean", "Description": "does a thing",
            "Actions": [START, configured, STOP]}
    assert audit.correctness_findings(flow) == []


def test_designer_blank_is_flagged_as_correctness_warn():
    # runtime Parameters set, designer configuration empty -> the documented bug
    blank = action("Send Email", params=[{"Value": "<%0%>", "Variable": [{"id": 0}]}],
                   settings=[{"value": ""}])
    flow = {"Actions": [START, blank, STOP]}
    cf = audit.correctness_findings(flow)
    assert "designer-blank" in _codes(cf)
    assert all(f["severity"] in ("warn", "fail") for f in cf)


def test_datastore_masquerade_flagged_as_fail():
    # a Call API node NAMED like a cache op is the FX-usecase bug: it never touches
    # the Data Store, but the process still runs green.
    masq = action("Call API", name="Cache read")
    flow = {"Actions": [START, masq, STOP]}
    cf = audit.correctness_findings(flow)
    hits = [f for f in cf if f["code"] == "datastore-as-callapi"]
    assert hits and hits[0]["severity"] == "fail"
    assert hits[0]["action"] == "Cache read"


def test_real_datastore_node_and_plain_callapi_not_flagged():
    real_cache = action("Data Store", name="Cache read",
                        params=[{"Value": "x"}], settings=[{"value": "x"}])
    plain_api = action("Call API", name="Fetch BNR XML",
                       params=[{"Value": "https://bnr.ro"}], settings=[{"value": "url"}])
    flow = {"Actions": [START, real_cache, plain_api, STOP]}
    assert "datastore-as-callapi" not in _codes(audit.correctness_findings(flow))


def test_practice_smells_flagged():
    acts = [START, STOP]
    acts += [action("Call API"), action("SQL Server"), action("Decisional")]
    acts += [action(f"Add{i}", params=[{"Value": "1"}], settings=[{"value": "1"}])
             for i in range(4)]  # push count over 5
    flow = {"Title": "Heavy", "Description": "", "Actions": acts}
    rep = audit.audit_process(flow)
    codes = _codes(rep["findings"])
    assert "high-action-count" in codes
    assert "slow-actions" in codes
    assert "missing-description" in codes
    assert rep["summary"]["nonstructural_action_count"] == 7


def test_audit_handles_live_camelcase_shape():
    # the LIVE Web-API returns camelCase; the auditor must work on it, not just
    # PascalCase export goldens (regression: live audit found 0 actions before ci()).
    flow = {"title": "Live", "description": "", "actions": [
        {"actionTemplateName": "Start", "parameters": []},
        {"actionName": "notify", "actionTemplateName": "Send Email",
         "parameters": [{"value": "<%0%>", "variable": [{"id": 0}]}],
         "customData": {"configuration": [{"settings": [{"value": ""}]}]}},
        {"actionTemplateName": "Stop", "parameters": []}]}
    rep = audit.audit_process(flow)
    assert rep["summary"]["nonstructural_action_count"] == 1
    assert rep["summary"]["title"] == "Live"
    assert "designer-blank" in _codes(rep["findings"])


def test_inline_secret_flagged_but_guid_credential_is_not():
    secret = action("Connect", params=[{"Value": "p@ssw0rd-secret-value", "Variable": []}])
    credid = action("Send Email",
                    params=[{"Value": "2aacf4f1-310c-469f-80ef-394d6ab9582f", "Variable": []}])
    flow = {"Actions": [START, secret, credid, STOP]}
    codes = _codes(audit.audit_process(flow)["findings"])
    assert "possible-inline-secret" in codes
    # the credential GUID literal must NOT be mistaken for a secret
    secret_findings = [f for f in audit.audit_process(flow)["findings"]
                       if f["code"] == "possible-inline-secret"]
    assert all(f["action"] != "Send Email" for f in secret_findings)


# -- a process that only reads a Data Store ----------------------------------

def _query_store(sql):
    return action("Query Store", name="Read stock",
                  params=[{"Value": sql, "Variable": []}, {"Value": "60"}],
                  settings=[{"value": sql}])


def _data_store(operation):
    return action("Data Store", name="Read stock",
                  params=[{"Value": "store-guid"}, {"Value": operation}],
                  settings=[{"value": operation}])


def _read_only_hits(*acts):
    flow = {"Title": "Reader", "Description": "reads", "Actions": [START, *acts, STOP]}
    return [f for f in audit.audit_process(flow)["findings"]
            if f["code"] == "datastore-read-only"]


def test_a_process_that_only_selects_from_a_data_store_points_to_the_form_trigger():
    hits = _read_only_hits(_query_store("SELECT Sku, Qty FROM <%0%>\nWHERE <%1%> = @c"))
    assert hits and hits[0]["severity"] == "info"
    assert "saved query" in hits[0]["message"] and "form" in hits[0]["message"]


def test_a_data_store_select_rows_node_counts_as_a_read():
    assert _read_only_hits(_data_store("SelectRows"))


def test_a_read_with_a_cte_and_comments_is_still_a_read():
    sql = "-- latest first\nWITH t AS (SELECT * FROM <%0%>) SELECT * FROM t ORDER BY 1"
    assert _read_only_hits(_query_store(sql))


def test_a_write_is_not_flagged():
    assert not _read_only_hits(_query_store("UPDATE <%0%> SET Qty = 0 WHERE Sku = @s"))
    assert not _read_only_hits(_query_store("SELECT 1; DELETE FROM <%0%>"))
    assert not _read_only_hits(_data_store("InsertRows"))


def test_a_word_like_update_inside_a_literal_does_not_make_it_a_write():
    assert _read_only_hits(_query_store("SELECT * FROM <%0%> WHERE Note = 'update me'"))


def test_a_read_followed_by_other_work_is_not_flagged():
    other = action("Call API", params=[{"Value": "https://x"}], settings=[{"value": "u"}])
    assert not _read_only_hits(_query_store("SELECT * FROM <%0%>"), other)


def test_a_process_with_no_data_store_action_is_not_flagged():
    add = action("Add", params=[{"Value": "1"}], settings=[{"value": "1"}])
    assert not _read_only_hits(add)
