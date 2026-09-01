# PROCESIO API reliability doctrine

How to drive the PROCESIO Web API **safely and predictably** when building or
operating processes and forms. These are platform truths, not project quirks —
they hold for any workspace. Each was learned by hitting it live; the `procesio`
tool now ENFORCES most of them so you cannot silently violate them (see the
guardrails table at the end), but the operating rules still shape how you sequence
your calls and how you decide a change actually landed.

Load this any time you are about to script a sequence of PROCESIO calls:
`python scripts/run-agent.py procesio guidance --topic reliability`.

---

## 1. Drive PROCESIO sequentially, not concurrently

Do NOT run PROCESIO calls in parallel against one workspace. Mixing synchronous
`run-process` executions with heavy definition reads/writes
(`GET /api/Projects/{id}` ~120 KB, `GET /api/FormTemplate/{id}` ~420 KB) can stall
the definition calls for **minutes**; the same calls issued strictly one-at-a-time
return normally. Fast endpoints (`POST /api/Projects/{id}/run`, `GET /api/Schedules`,
`GET /api/Projects` list, `form-set-code`) stay responsive throughout.

The leading explanation (a **hypothesis**, not confirmed): a process is many
actions each with its own timeout, workspace execution capacity is finite, and
under load both executions and definition reads/writes **queue** behind it — i.e.
the "hangs" are legitimate long/queued work, not a broken API. Whether or not that
is the mechanism, the operating rule is the same: **one PROCESIO call in flight at
a time.** Build loops sequentially; do not fan out.

## 2. Behavioural verification over re-read — writes can lie

A success-shaped response is NOT proof the change persisted. A definition PUT has
been seen to return `200` with an empty/`{"raw_text":""}` body while the change did
**not** land server-side. The only trustworthy check is **behavioural**: run the
process (or open/submit the form) and observe the effect — or re-read the
definition and diff it. Never conclude "it worked" from the write's own echo.
`put-projects` now warns you when the body comes back empty.

## 3. The client surfaces a stall instead of hanging

The client's HTTP timeout is a *per-read inactivity* guard, not a total deadline:
a connection that is accepted and then dribbles (or is held open) never trips it,
so a stalled call used to run until the process was killed. The client now imposes
a **total wall-clock deadline** per call, by class — definition/list/schedule
**reads ~90 s**, definition **writes (PUT) ~180 s** — and on expiry raises a
structured `deadline_exceeded` error (`outcome:"unknown"`, exit non-zero) instead
of hanging. `run-process` is **exempt** (see §4). Opt out with
`AAT_PROCESIO_NO_DEADLINE=1` if you are deliberately waiting on something slow.

## 4. Client-side abort ≠ server-side stop

Aborting a slow synchronous run on the client does **not** stop the run on the
server — it keeps executing and writing its side effects (Sheet rows, emails,
social posts, DB writes). So `run-process --synchronous` is exempt from the total
deadline: a many-action process legitimately runs for minutes, and killing it
client-side is itself a hazard. If you must bound it, pass `--timeout`
(`secondsTimeOut`) so the SERVER stops it, or use the async
publish → launch → poll path and stop the instance in the UI. Never assume a
client-side timeout undid anything.

## 5. The workspace is never idle

Server-side **schedules** fire processes around the clock (a dispatcher tick every
few minutes is common). Any reasoning that "nothing else is running right now" is
wrong, and the client cannot see scheduled executions. When latency looks off,
list the schedules (`list-schedules`) and check their next-run times before
blaming your own call.

## 6. Retry reads, never writes

The client retries **GET only**, on transient statuses (`429/502/503/504`) and
network errors, with jittered backoff inside the deadline. `POST/PUT/PATCH/DELETE`
are **never** retried: re-POSTing an execution double-runs a process with real
side effects, and a timed-out write may already have applied. If a write fails or
times out, treat the outcome as **unknown** and verify behaviourally (§2) before
resending. Opt out of retries with `AAT_PROCESIO_NO_RETRY=1`.

## 7. Form-build traps (accepted silently by the server)

These cost a debugging session each because the server accepts them without
complaint. `form-update` now emits non-blocking **lint warnings** for the first
three; full detail in `tools/procesio/FORM-DEV-GUIDE/08-PITFALLS.md`.

- **Phantom `parentId`** — an element whose `parentId` matches no element id
  renders on NO pane. Tab/container membership is by `parentId` = a container
  element's id; a dangling reference is invisible, not an error.
- **`form-update` deep-merge** — arrays REPLACE wholesale (pass the whole new
  array to change one item); `None` sets the key to `null` (it does not delete);
  and a patch wrapped as `{"Data": {...}}` becomes an inert junk key that changes
  nothing. Pass the INNER fields directly.
- **Duplicate `id`/`name` configs** across elements collide for CSS/JS selectors
  and process mapping — keep them unique.
- **Event editing is replace-then-append.** An element commonly carries
  `[RUN_PROCESS, RUN_JAVASCRIPT]` on one click trigger. A blanket "replace" wipes
  BOTH. Replace only the one action you mean (`form-set-element-event
  --replace-action RUN_PROCESS`) and the sibling survives in order; bare
  `--replace` now warns before discarding more than one.

---

## What the tool enforces for you

| Rule | Enforcement in the `procesio` tool |
|---|---|
| §2 writes can lie | `put-projects` reports HTTP status/elapsed and WARNS on an empty body |
| §3 no total deadline | class-aware wall-clock deadline → `deadline_exceeded` (`AAT_PROCESIO_NO_DEADLINE=1` to opt out) |
| §4 abort ≠ stop | `run-process` exempt from the deadline; keeps its own `--timeout` |
| §6 retry reads only | GET-only retry with backoff; POST/PUT never retried (`AAT_PROCESIO_NO_RETRY=1` to opt out) |
| §7 form traps | `form-update` DTO lints; `form-set-element-event --replace-action` |

The rules the tool does NOT enforce — sequential sequencing (§1), behavioural
verification (§2), and reading schedules (§5) — are on you. Follow them.
