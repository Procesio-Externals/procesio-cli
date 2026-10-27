# Capacity sizing method

Estimate capacity from measured active work, concurrency, and service objectives—not from a generic action count.

## Inputs

- executions per period;
- peak arrival rate and burst duration;
- measured active compute time per representative execution;
- external wait behavior and whether it consumes metered/occupied capacity;
- required completion window;
- retry and exception rate;
- growth and safety margin;
- availability and maintenance assumptions;
- verified concurrent slots and compute/throughput limits per Execution Environment (EE), plus whether slots remain occupied during waits.

Count retries and child/subprocess work explicitly. Either measure the whole causal tree per arrival or sum disjoint workload classes; do not count child work twice. Metered time, CPU time, occupied slot time and end-to-end latency are not interchangeable.

## Calculations

For one workload class, with rates in executions/second and durations in seconds:

```text
compute_work_seconds = executions × mean_active_compute_seconds
occupied_slot_seconds = executions × mean_occupied_seconds
average_occupied_slots = occupied_slot_seconds ÷ available_seconds_in_period
busy_interval_slots_estimate = busy_interval_arrival_rate × mean_occupied_seconds
planned_slots = ceil(max(average_occupied_slots, busy_interval_slots_estimate) × safety_factor)
slot_based_EE_lower_bound = ceil(planned_slots ÷ verified_slots_per_EE)
```

`mean_occupied_seconds` includes waits only while they hold a slot; exclude queue time before admission. When occupancy is unknown, show both hold-slot and release-slot scenarios. Compute work is a separate utilization/throughput constraint, not a replacement for occupied slot time.

Arrival rate × mean occupied time is a steady-state estimate, not a peak or SLA guarantee. Use a representative load test or queue/burst model for tail latency, finite bursts and deadline sizing. For concurrent workload classes, sum their overlapping slot demand before sizing shared capacity; do not independently maximize classes and assume their peaks never overlap.

Do not equate one parallel slot with one EE. Convert to an EE lower bound only with verified per-EE slot capacity, then check compute throughput, memory, quotas, utilization headroom and availability requirements. Without those inputs, report demand and the missing capacity contract; do not invent an EE count or a universal seconds-per-EE conversion.

Example (hypothetical, not a PROCESIO limit): 10,000 executions in one hour, each with 2 compute seconds and 20 occupied seconds, require 20,000 compute-seconds and 200,000 slot-seconds (55.6 average occupied slots). A sustained busy interval of 5 arrivals/second suggests 100 occupied slots; a 1.25 safety factor gives 125 planned slots. Only if 10 slots/EE is independently verified does this yield a slot-based lower bound of 13 EEs, still subject to the other constraints and load proof.

Show low/base/high scenarios, input sources, units and uncertainty. Never substitute this illustrative slot count for a product or commercial guarantee.

## Offline arithmetic helper

Run `python <skill-root>/scripts/estimate_capacity.py --input <measurement.json>` with Python 3.11+; no dependencies, network calls or file writes. It accepts one UTF-8 JSON object (maximum 64 KiB):

```json
{
  "executions": 10000,
  "available_seconds": 3600,
  "mean_active_compute_seconds": 2,
  "mean_occupied_seconds": 20,
  "busy_interval_arrival_rate": 5,
  "safety_factor": 1.25
}
```

All rates/durations use seconds. Counts are nonnegative integers; available time is positive; the safety factor is at least one. Missing occupancy, Boolean/nonfinite numbers and unknown fields fail closed. Add optional `verified_slots_per_ee` (positive integer) together with a nonempty `capacity_source` only when that assumption has an attributable basis. The helper does not verify the source and never supplies a default product limit. Without capacity, its EE lower bound is null. Output is one JSON object, exit 0 on success or an error envelope and exit 1 for invalid data. Run low/base/high scenarios separately; it is not a queue simulator, multi-class planner, deployment tool or SLA proof.

## Commercial comparison

Obtain current prices and contractual terms before calculating costs. Compare like for like:

- included capacity and overage;
- concurrency/SLA guarantees;
- environments and support;
- infrastructure and operations for self-hosting;
- implementation and maintenance effort;
- expected growth and retry load.

State the price source and verification date. Never reuse a historical private quote as a public current price.
