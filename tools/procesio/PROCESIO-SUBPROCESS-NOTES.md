# Subprocesses, Form Trigger and the instance-reading actions: measured behaviour

Measured on PROCESIO cloud (2026-10-29) with throwaway processes built by `process-create` and
driven in the designer. Covers `Call Subprocess`, `Trigger Subprocess`, `Form Trigger`,
`Get Instance Outputs`, `Count Recent Instances` and `Get Recent Instances`. Companion to
`PROCESIO-API-NOTES.md` (flow control table, auto variables, `Call Subprocess` and File inputs)
and `dto/process/description.md` (the builder's `subprocess:` shape).

## A designer save hangs on a builder-made Trigger Subprocess

- **Symptom.** Save in the designer shows an hourglass for good. No `PUT /api/projects` is sent,
  and the console has
  `TypeError: ((intermediate value) || [])?.forEach is not a function at X.checkSubprocess`.
  Validate hangs the same way, and Run stays disabled ("Please validate the process...").
- **Cause.** The designer's pre-save check reads the FIRST setting of a subprocess action's
  "Subprocess Configuration" side panel as the input mapping and calls `forEach` on its value.
  The designer keeps that panel sorted by `rowId`; for `Trigger Subprocess` that is
  `Input Variables` (rowId 0) then `Subprocess Instance Id` (rowId 1). The action catalog lists
  them the other way round, and `process-create` writes the catalog order. As soon as
  `Subprocess Instance Id` holds a variable (its value is the variable id, a string), the check
  throws and the save never happens.
- **Scope.** The process saves and runs fine over the API. The hang appears the first time a person
  opens it in the designer and saves, so it looks like a designer bug to them. A
  `Trigger Subprocess` whose instance-id slot is empty saves normally, and so does one whose slot was
  bound in the designer (the designer writes the panel in rowId order). `Call Subprocess` is not
  affected: its panel's catalog order is already inputs first.
- **Workaround until the builder sorts it:** before the PUT, sort every
  `customData.configuration[].settings[type == "side-pannel"].value` list by `rowId`.

## Trigger Subprocess

- Starts the child and moves on at once. A parent whose `Trigger Subprocess` starts a ten-second
  child finishes in about a second, and a `Get Instance Outputs` right after it fails (below).
- `Subprocess Instance Id` must bind a **Guid** variable; a String one is BE 142
  "Data type mismatch".
- Its panel has input mapping only: the child's outputs never come back to the caller. Read them
  later with `Get Instance Outputs` and the id.
- The run view links a `Call Subprocess` step to its child run (below); the docs say
  `Trigger Subprocess` steps get no such link.

## Call Subprocess in the run view

- Select the step in a run's details, General tab: "SUBPROCESS INSTANCE" shows the child run's
  id as a button that calls `window.open` on
  `/admin/process/<childProcessId>/details/<childInstanceId>` (a new tab).

## Get Instance Outputs

- Settings: Select Process, InstanceId (Guid), and an output mapping under Process Configuration.
  The designer flags a missing mapping row as REQUIRED. The builder's
  `subprocess: {target, outputs}` shape fills the process and the mapping, with
  `params: {"InstanceId": {"var": ...}}` for the id.
- A run that is still going: `The child flow status should not be: STATUS_RUNNING`.
- A run already moved to the run history: `Couldn't find the flow instance <id>`.
- So it reads a run only between its end and its move to the history.

## Count Recent Instances and Get Recent Instances

- Both read the process's **current** instance list only (what `GET /api/Projects/{id}/instances`
  returns and what Process instances shows), never `/history`. A finished run leaves that list a
  few minutes after it ends. The move is time-based: two newer runs did not push an older one out.
  "Recent" therefore means "still listed under Process instances".
- `Count Recent Instances`: `List of Process Template Ids` must be a list<Guid> variable
  (list<String> is BE 142). An empty or unbound list counts the whole workspace. `Status type` is a
  select (ALL, 1, 6, 30, 50, 40); the builder takes the number.
- `Get Recent Instances`: Select Process (or `Process Template Id`), Page Number, Page Item Count
  (0 returns everything), Status type. `Result` comes back as a list of
  `{Id, Status, UpdatedOn}` even when bound to a Json variable. `Total Count` is REQUIRED by the
  designer (FE error on save if unbound) although the run needs only `Result`.

## Form Trigger

- Settings: Form Template (required), outputs Result (Boolean) and Form Id (Guid).
- Creates a form instance from the template and returns at once: `Result` true and `Form Id` set
  in the same run. Nothing waits for the form to be filled in.

## The parent's child link is cleared when a child ends (Process-Execution v3.1.0, 2026-11-02)

The engine keeps the link from a parent to its current child (and back) in its cache. It is now
removed when the child finishes, finishes with errors or is stopped by the user; before, the
parent's entry was never removed. No API reads it, so instance lists, outputs and counts look the
same; it only decides where a resumed parent waiting on Call Subprocess continues.
