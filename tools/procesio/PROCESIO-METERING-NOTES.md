# PROCESIO metering — where run cost actually lives, and where it does not

How to read what a process run consumed. Written after an attempt to measure the
cost of a long-running run found the obvious endpoint empty and a better one
undocumented. Auth/connection mechanics stay in
[PROCESIO-AUTH-NOTES.md](PROCESIO-AUTH-NOTES.md).

> ## ⚠ CORRECTION, 31/08/2026 — READ THIS BEFORE §2
>
> **§2 below was wrong about what the per-instance figures mean, and the error
> was the expensive kind: it named a live-looking instrument as the fallback for
> a dead one.** Controlled measurement on an unmetered workspace, with a positive
> control on every reading:
>
> | what was done | what the platform recorded |
> |---|---|
> | 100,001 ms of busy loop inside Node actions, 5 runs | **31 ms** total |
> | a Call API blocked for 30,000 ms by the callee | **14 ms** |
> | a Call API blocked for 120,000 ms | **8 ms** |
> | a Call API blocked for 300,000 ms | **15 ms** |
>
> `timeConsumed` is **not** wall-clock occupancy and does **not** include time
> spent waiting on a reply. It is flat in the single-to-low-double-digit
> milliseconds whatever the action does, and `timeConsumed == totalTimeConsumed`
> in every reading — including a five-minute wait, where §2 predicts the widest
> divergence. Treat both fields as **per-action orchestration overhead**, not as
> a measure of work.
>
> **The rule this leaves.** On a workspace with `subscriptionType: null` there is
> no endpoint that prices a run: the quota counter is dead (§1), the per-instance
> figures are blind to compute and to waiting, and the per-process endpoints
> return empty. If a decision needs the cost of a long wait, it cannot be
> measured on an unmetered account — say so and name it as a blocker, rather than
> substituting a number from an instrument that has not been shown to track the
> work. **Prove the instrument moves with the work before believing any figure it
> reports** — the same rule §1 states for the quota counter applies to its
> replacement, and skipping that step is exactly how the fallback was adopted.
>
> The instance-level fields remain useful for what they DO report reliably:
> `actionsConsumed` (an action count) and the existence and status of an instance.

---

## 1. `/api/Resources/used` is the QUOTA, and it may carry no consumption at all

`GET /api/Resources/used` returns the workspace's time budget:

```json
{"result": {"subscriptionType": null, "price": 0.0,
  "time": {"consumed": 0, "masterConsumed": 0, "canExceedPaidTime": true,
           "limit": {"soft": 36000000, "hard": 36000000},
           "notifyThreshold": 28800000},
  "average": {"platform": {"total": 0, "internal": 0, "external": 0}, "custom": 0},
  "expirationDate": "...", "autoRenewable": true}}
```

**The budget is published even when nothing is counted against it.** On a workspace
with **`subscriptionType: null`** every consumption field stays at `0` — before a
run, after it, and after many runs across an hour. It is not a settling lag and it
is not a disabled recorder: `GET /api/ResourceTrackingConfig` reports
**`isRecordingEnabled: true`** on the same workspace.

**The trap:** the endpoint answers `200` with a plausible-looking body, so a
before/after diff reads as "this run cost nothing" rather than "this endpoint does
not measure". **Never infer cost from a zero delta here.** Prove the counter moves
at all before interpreting any reading from it; if `subscriptionType` is null,
expect it not to.

Scope note: these endpoints are workspace-scoped. `MasterWorkspace.Read` variants
(`/api/Resources/used/subworkspaces`, `/api/Subscriptions`, the
`executionEnvironment/concurrency` analytics) return **403** to a sub-workspace
credential.

## 2. The real per-run meter is per INSTANCE, and it is in two places

Both are populated immediately and on any workspace, metered or not.

**`GET /api/Projects/{processId}/instances`** — each `pageItems[]` entry carries:

| Field | Meaning |
|---|---|
| `actionsConsumed` | actions executed in that instance |
| `timeConsumed` | **wall-clock occupancy**, including time spent waiting on a reply |
| `totalTimeConsumed` | **compute**, the time actions spent executing |
| `timeout` | the instance's own timeout setting |

**`GET /api/Resources/analytics/instances/{instanceId}/details`** — the same run
broken down by action type:

```json
{"result": [{"instanceId": "...", "actionName": "Node",
             "totalRuns": 15, "totalTime": 200, "actionExecutionTime": 198}]}
```

`totalTime` ↔ `timeConsumed`; `actionExecutionTime` ↔ `totalTimeConsumed`.

### The naming is inverted from intuition — check it, do not trust it

**`totalTimeConsumed` is the SMALLER figure.** It is compute. `timeConsumed`, which
sounds like the subset, is the larger occupancy figure. Verify the pairing on a
known instance before building anything on it: read both endpoints for the same
instance id and confirm which number is larger.

### The two columns diverge exactly where a wait is

Occupancy minus compute is the time an action spent blocked. On a flow whose actions
are all local the two are nearly equal; on a Call API waiting for a reply they
separate sharply (observed: an action at `totalTime` 747 ms against
`actionExecutionTime` 5 ms). Across repeated runs **compute is stable and occupancy
is volatile**, and all the volatility sits in the calls that wait.

## 3. The two endpoints can permanently DISAGREE about the same instance

Observed on the run with the longest wait in a set: the details endpoint reported
fewer actions and a lower total than the instance list, and **the two never
converged** across re-reads minutes and then tens of minutes apart.

Worse for anyone testing for lag: **the details endpoint was stable across two reads
thirty seconds apart while still being incomplete.** Two matching reads are not proof
of settlement. Reconcile the two endpoints against each other rather than trusting a
repeat read of one.

## 4. Nested processes are metered SEPARATELY, and occupancy double-counts them

A process reaching another through **Call API** launches a **separate instance** with
its own `actionsConsumed` / `timeConsumed` / `totalTimeConsumed`. While the caller's
Call API waits, the callee is executing and billing its own instance.

Consequences:

- **Count the whole call tree, not the entry instance.** An entry process's action
  count can be a fraction of the request's true total once its callees are added.
  Comparing an entry instance's count against a whole-tree figure loses the
  difference silently.
- **On the occupancy column the same stretch of time appears twice** — as the
  caller's wait and as the callee's run. On the compute column it appears once.

## 5. What the vendor documents about which time is charged

From the PROCESIO docs (processing-time FAQ). **Documented, not verified by
measurement** — the endpoint that would confirm it is the one in §1:

- *"the processing time is consumed while waiting for an external service to reply
  as a running process consumes resources on our infrastructure"* — **a blocking
  external call is charged for the whole wait.**
- *"Delay action is counted only while during its processing. But for the period set
  to delay... the action is not processing, and therefore this delay time is not
  counted"* — **a parked Delay is exempt.**
- *"webhooks that trigger a process are not counted against the processing time"*.
- The stated platform average is **~100 ms per action**.

**The measurement trap this creates:** a Delay is the natural way to synthesise a
long run, and it is the one mechanism documented as exempt. Timing a Delay therefore
measures the exempt case and says nothing about a blocking call. **To measure what a
long external wait costs, the long run must be produced by a call that blocks**, not
by a Delay.

## 6. Timeouts

| Timeout | Value | Applies to |
|---|---|---|
| **Instance / process** | **none.** Per-instance `timeout: 0`; docs state a per-process timeout "is not possible" and the feature does not exist | nothing kills a long run |
| **Call API action** | min **60 s**, max **3600 s** | one HTTP call |
| **AI Decisional action** | 1–3600 s, default 60 s | one provider call |
| **Node action** | integer; throws on expiry | one script |
| **Synchronous launch** | `?runSynchronous=true&secondsTimeOut=N` (300 in the documented example, **no maximum stated**) | the caller's own wait |

A run is not bounded by the platform. It is bounded by whichever action timeout it
trips first.

## 7. Instance history is trimmed aggressively, and the two endpoints differ

Only a handful of instances per process survive. **Do not plan to read an
interesting run later** — capture its figures in the same script that launches
them.

Trimming is faster than "within days": rows have been observed ageing out of
`GET /api/Projects/{id}/instances` **within about eight minutes**, one by one,
with no new runs to displace them. The analytics **details endpoint outlived the
list** for the same instance, so the two have different retention and a missing
row in one is not proof the run is gone from the other.

## 9. Resource recording defaults to OFF on a new workspace

`GET /api/ResourceTrackingConfig` reports `isRecordingEnabled` per workspace, and
a freshly created workspace can arrive with it **false** and a zeroed `gid`. In
that state the analytics details endpoint returns an **empty array** while the
instance list still answers — so a zero from the details endpoint is confounded
between "not recorded" and "not consumed" until the flag is read.

Check the flag before interpreting any analytics zero.
`PUT /api/ResourceTrackingConfig/toggle/{true|false}` sets it (needs
`Workspace.Admin`) and creates the per-workspace record. Note that enabling it
does **not** make the figures track the work — see the correction at the top of
this file; it only makes the details endpoint answer at all.

## 8. Wall-clock measured by a polling harness is not the run

A harness that polls on an interval quantises to that interval: runs the platform
records at a few hundred milliseconds read as ~9 s against a 5 s poll. **Use the
platform's own figures for duration**, never the harness's elapsed time.
