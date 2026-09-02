"""The build-and-test self-test checklist, as structured data.

Single source of truth for what "tested" means (the playbook's checklist in
machine-readable form). The `checklist` action emits it; `verify` runs the
automatable steps; the manual steps are surfaced so a human/LLM cannot quietly
skip them. Keep this in sync with PROCESIO-BUILD-AND-TEST-PLAYBOOK.md.

Each step:
  id          stable slug
  phase       validate | run | forms | webhooks | e2e
  title       what to check
  how         concrete mechanic
  tool        which registered tool/action performs it (or "" for judgment)
  automatable True  -> `verify` can run it
              False -> a human/LLM must do it (named in verify's manual_checks)
  citation    where it comes from
"""
from __future__ import annotations

STEPS: list[dict] = [
    # A. static validation -----------------------------------------------------
    {"id": "validate-process", "phase": "validate", "automatable": True,
     "title": "Validate the process with PROCESIO's own validator",
     "how": "POST /api/Projects/validate; expect no validation errors",
     "tool": "procesio request", "citation": "playbook A"},
    {"id": "config-parity-audit", "phase": "validate", "automatable": True,
     "title": "Designer-vs-runtime parity: every action configured",
     "how": "runtime Parameters[] must be mirrored into CustomData.configuration "
            "or the designer shows 'not configured' and Validate fails",
     "tool": "procesio agent (audit/verify)", "citation": "playbook A; PHASE4-E2E"},
    {"id": "test-credentials", "phase": "validate", "automatable": True,
     "title": "Test every credential the process uses",
     "how": "POST /api/Credentials/test returns a real upstream body when placement is right",
     "tool": "procesio request", "citation": "playbook A; PHASE4-E2E 3-4"},
    {"id": "test-actions", "phase": "validate", "automatable": True,
     "title": "Test individual actions where supported",
     "how": "POST /api/Actions/test", "tool": "procesio request",
     "citation": "playbook A"},
    {"id": "db-credential-engine", "phase": "validate", "automatable": True,
     "title": "For a DB credential, Test Connection against the chosen engine",
     "how": "a MySQL DB credential (server-type MySQL) or a Redis credential must pass "
            "POST /api/Credentials/test — it opens a real connection",
     "tool": "procesio credential-test", "citation": "datastore/best-practices; PRC-3696"},
    # B. run + instance --------------------------------------------------------
    {"id": "run-instance", "phase": "run", "automatable": True,
     "title": "Run the process and read the real instance status",
     "how": "run-process --synchronous, then status 50 = finished, 40 = ran-with-errors",
     "tool": "procesio run-process / get-instance-status",
     "citation": "playbook B; PHASE4-E2E 6,15"},
    {"id": "read-action-errors", "phase": "run", "automatable": True,
     "title": "Read per-action errorMessage, do not assume success",
     "how": "GET /api/Projects/instances/{id}/status?getActions=true",
     "tool": "procesio get-instance-status --actions", "citation": "playbook B"},
    {"id": "download-artifact", "phase": "run", "automatable": False,
     "title": "Download and open any generated file",
     "how": "GET /api/File/download with uploadFilePath/variableId/instanceId/flowTemplateId",
     "tool": "procesio request", "citation": "playbook B"},
    {"id": "datastore-roundtrip", "phase": "run", "automatable": True,
     "title": "Data Store: a row round-trips (add -> filtered read -> update -> delete)",
     "how": "add-rows then get-rows with a filter returns exactly it; update-row by PK and "
            "delete-rows change affectedRows as expected (rows keyed by display name)",
     "tool": "procesio datastore-*", "citation": "datastore"},
    {"id": "schedule-cron", "phase": "run", "automatable": True,
     "title": "Schedule: preview a cron string, then confirm the stored recurrence",
     "how": "validate-crontab returns the expected next occurrences; create-schedule "
            "--cron then get-schedule shows recurrence type 8 (CRON)",
     "tool": "procesio validate-crontab / create-schedule / get-schedule",
     "citation": "scheduling; PRC-3282"},
    # C. forms -----------------------------------------------------------------
    {"id": "form-render", "phase": "forms", "automatable": False,
     "title": "Confirm the form renders (layout, theme, controls)",
     "how": "open forms.procesio.app/... and screenshot",
     "tool": "web", "citation": "playbook C"},
    {"id": "form-behavior", "phase": "forms", "automatable": False,
     "title": "Verify field value-flow in a REAL browser, not headless",
     "how": "headless fill()/press() do NOT update the Angular form model and "
            "RUN_JAVASCRIPT events do not fire headlessly -> false negatives",
     "tool": "web (persistent session)", "citation": "playbook C; PHASE4-E2E 7-11,21"},
    {"id": "form-triggers", "phase": "forms", "automatable": False,
     "title": "Confirm RUN_PROCESS triggers ran the process and produced the artifact",
     "how": "prefer server-side RUN_PROCESS mapping over form JS reading field values",
     "tool": "web", "citation": "playbook C"},
    {"id": "form-theme-render", "phase": "forms", "automatable": False,
     "title": "Confirm the theme renders: dark mode + element alignment",
     "how": "toggle dark mode and check the 16-var palette applies; container elements "
            "honor their --fd/--jc/--ai alignment vars — verify in a real browser",
     "tool": "web", "citation": "playbook C; form-styling"},
    {"id": "form-datastore-trigger", "phase": "forms", "automatable": False,
     "title": "Confirm a RUN_DATA_STORE_OPERATION trigger runs and the row round-trips",
     "how": "fire the element event; the READ/ADD/UPDATE/DELETE op hits the store and the "
            "result maps back into the form (filters apply to every op except ADD)",
     "tool": "web + procesio datastore-get-rows", "citation": "datastore"},
    # D. webhooks --------------------------------------------------------------
    {"id": "webhook-trigger", "phase": "webhooks", "automatable": True,
     "title": "Trigger the webhook and confirm an async instance runs to status 50",
     "how": "POST the webhook endpoint with a real payload, then poll instances",
     "tool": "procesio request / list-instances", "citation": "playbook D"},
    {"id": "webhook-body-binding", "phase": "webhooks", "automatable": False,
     "title": "Webhook body binds WHOLE to a model-typed variable",
     "how": "bind the body to a primitive and you get raw JSON instead of fields",
     "tool": "procesio agent (design check)", "citation": "playbook D; PHASE4-E2E 1"},
    # E. end-to-end ------------------------------------------------------------
    {"id": "e2e-flow", "phase": "e2e", "automatable": False,
     "title": "Exercise the whole use case as a user; verify the real artifact",
     "how": "form -> process(es) -> document/email/SQL -> system of record",
     "tool": "web + procesio", "citation": "playbook E"},
    {"id": "idempotency", "phase": "e2e", "automatable": False,
     "title": "Trigger twice; confirm no duplicate side effects",
     "how": "external IDs / dedupe keys make a retry or double-trigger safe",
     "tool": "", "citation": "best-practices 2"},
    {"id": "ux-timing", "phase": "e2e", "automatable": False,
     "title": "Check forms UX timing (1s / 3s rules)",
     "how": ">=90% of clicks under 1s, <=10% in 1-3s, none ever over 3s",
     "tool": "web", "citation": "best-practices 9"},
    {"id": "speed", "phase": "e2e", "automatable": True,
     "title": "Check optimize-for-speed (action count, slow actions)",
     "how": "~10ms per action; reduce count; minimize Call API/SQL/FTP/Decisional",
     "tool": "procesio agent (audit)", "citation": "best-practices 10"},
]

PHASES = ["validate", "run", "forms", "webhooks", "e2e"]


def steps(phase: str | None = None, automatable_only: bool = False) -> list[dict]:
    out = STEPS
    if phase:
        out = [s for s in out if s["phase"] == phase]
    if automatable_only:
        out = [s for s in out if s["automatable"]]
    return [dict(s) for s in out]


def manual_steps() -> list[dict]:
    """Steps `verify` cannot run - a human/LLM must do them by hand."""
    return [dict(s) for s in STEPS if not s["automatable"]]
