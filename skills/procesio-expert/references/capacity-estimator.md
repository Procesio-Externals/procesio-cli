> Last verified: March 2026

# PROCESIO Capacity & Cost Estimator

A structured methodology for estimating PROCESIO automation capacity, costs, and the optimal pricing model (Processing Time vs Reserved EEs).

**Audience**: Presales, sales engineers, solution architects, implementation partners.

---

## Overview

This guide provides a data-driven approach to sizing PROCESIO deployments. Given a set of business flows, volumes, and usage patterns, it calculates:

1. Total actions and CPU time required
2. Concurrency needs (how many parallel processes)
3. Number of Execution Environments (EEs) needed
4. Cost comparison: Processing Time vs Reserved EEs
5. Break-even analysis and recommendation

---

## Default Pricing

These are the standard prices. Override when client-specific pricing applies.

| Model | Price | Annual Equivalent |
|-------|-------|-------------------|
| **Processing Time** | €10/h | Variable (usage-based) |
| **Reserved EE (PROCESIO-hosted)** | €0.70/h/EE | ~€6,132/EE/year |
| **Reserved EE (Self-hosted license)** | — | ~€3,500/EE/year |

**Break-even**: At €10/h, one Reserved EE (~€6,132/year) becomes cheaper than Processing Time when annual active CPU time exceeds **~613 hours** (~1.7h/day or ~2.6h/day at 20 working days/month).

---

## Core Concepts

### Business Flow
A business flow is an automation target — e.g., "Order Processing", "Invoice Submission", "Customer Onboarding". Each flow typically decomposes into multiple PROCESIO processes.

### Process Modularization
Default assumption: **3 PROCESIO processes per business flow** (e.g., main orchestrator + 2 reusable subprocesses for auth, validation, notifications).

### Action
An atomic step inside a process. Platform actions execute in ~10ms. Actions involving external calls (API, SQL, sFTP) take longer — typically 300-500ms average including network latency.

### UI/Webform Workload
Forms and dashboards built with PROCESIO trigger backend processes for data retrieval, filtering, pagination. Each user interaction (page load, filter change, pagination) triggers one or more process executions.

### Execution Environment (EE)
An EE is a compute unit. **Concurrency = number of EEs**. When all EEs are busy, new process instances queue.

---

## Data Collection Checklist

Collect or deduce these inputs before running the estimation:

### Required
| Input | Description | Example |
|-------|-------------|---------|
| Business flows | List of automation targets | Order Processing, Invoice Submission |
| Monthly volume per flow | # of executions/month | 10,000 orders/month |

### If Flow Has UI/Webform
| Input | Default | Description |
|-------|---------|-------------|
| # UIs per flow | 2 | How many screens/dashboards |
| Type | Form or Table | Affects complexity |
| # Users | 10 | Concurrent users |
| Refreshes/user/day | 5 | Page loads, filter changes, pagination clicks |
| % Active UIs/day | 50% | Not all UIs are used daily |

### Process Complexity
| Input | Default | Description |
|-------|---------|-------------|
| Processes per flow | 3 | Modularization level |
| Actions per business process | 13 | Average action count |
| Actions per UI process | 4-7 | Simpler than business processes |

### Timing
| Input | Default | Description |
|-------|---------|-------------|
| Action duration (business) | 0.5s | Includes external call latency |
| Action duration (UI) | 0.3s | Faster, simpler queries |
| Peak factor | 2.5x | Peak vs average load multiplier |

### Working Schedule (Critical)
| Input | How to Determine |
|-------|------------------|
| H (hours/day) | Employee operations = 8-9h. Consumer/global = 12-24h. |
| D (days/month) | Weekdays only = 20. 24/7 operations = 30. |

**If unclear, use conservative fallback: H=6h/day, D=20 days/month** — this avoids underestimation.

---

## Calculation Logic

### Step 1: Business Process Load

```
For each flow:
  Executions/month = [user input]
  Processes/flow = 3 (or input)
  Actions/process = 13 (or input)
  
  Actions/month (this flow) = Executions x Processes x Actions

Total Actions (Business) = Sum of all flows
```

**Example:**
- Order Processing: 10,000 exec x 3 proc x 13 actions = 390,000 actions/month
- Invoice Submission: 5,000 exec x 3 proc x 13 actions = 195,000 actions/month
- **Total Business Actions**: 585,000/month

### Step 2: UI Process Load

```
For each flow with UI:
  UIs/flow = 2 (or input)
  Processes/UI = 3 (or input)
  Actions/process = 5 (avg 4-7)
  Users = 10 (or input)
  Refreshes/day/user = 5 (or input)
  % Active = 50% (or input)
  D = 20 days/month (or input)
  
  Executions/month/UI = Users x Refreshes x D x %Active
  Executions/month (UI processes) = UIs x Processes/UI x Executions/month/UI
  Actions/month (this flow) = Executions x Actions/process

Total Actions (UI) = Sum of all flows with UI
```

**Example:**
- Order Dashboard: 2 UIs x 3 proc/UI x (10 users x 5 refresh x 20 days x 50%) x 5 actions = 15,000 actions/month
- Invoice Dashboard: 2 UIs x 3 proc/UI x (10 x 5 x 20 x 50%) x 5 actions = 15,000 actions/month
- **Total UI Actions**: 30,000/month

### Step 3: Total CPU Time

```
CPU Time (Business) = Actions (Business) x Duration (Business) / 3600
CPU Time (UI) = Actions (UI) x Duration (UI) / 3600

Total CPU Hours/Month = CPU Time (Business) + CPU Time (UI)
CPU Hours/Day = Total / D
```

**Example:**
- Business: 585,000 x 0.5s / 3600 = 81.25 hours/month
- UI: 30,000 x 0.3s / 3600 = 2.5 hours/month
- **Total**: 83.75 hours/month = **4.19 hours/day** (at D=20)

### Step 4: Concurrency & EE Sizing

```
Process Duration (Business) = Actions x Duration = 13 x 0.5s = 6.5s
Process Duration (UI) = Actions x Duration = 5 x 0.3s = 1.5s

Total Executions/Month = Business Exec + UI Exec
Executions/Hour (avg) = Total Exec / (D x H)
Executions/Hour (peak) = avg x Peak Factor (2.5)

Concurrent Processes = 
  ((Peak Exec Business x Duration Business) + (Peak Exec UI x Duration UI)) / 3600

EEs Required = ceil(Concurrent Processes x 1.25 buffer)
```

**Example:**
- Total Exec: 15,000 (business) + 6,000 (UI) = 21,000/month
- Avg Exec/Hour: 21,000 / (20 x 6) = 175/hour
- Peak Exec/Hour: 175 x 2.5 = 437.5/hour
- Concurrent: ((300 x 6.5s) + (137.5 x 1.5s)) / 3600 = 0.6 concurrent
- EEs: ceil(0.6 x 1.25) = **1 EE**

---

## Cost Comparison

### Processing Time Cost
```
Monthly Cost = CPU Hours/Month x Euro/hour
Annual Cost = Monthly x 12
```

### Reserved EE Cost
```
Annual Cost = # EEs x 6,132 Euro/EE
Monthly Cost = Annual / 12
```

### Break-Even Analysis
```
Break-even CPU Hours/Year = (# EEs x 6,132) / 10 Euro/h
Break-even CPU Hours/Day = Break-even/Year / (D x 12)
```

**For 1 EE at Euro10/h:**
- Break-even = 6,132 / 10 = 613 CPU hours/year
- At D=20: 613 / 240 = **2.55 hours/day**
- At D=30: 613 / 360 = **1.70 hours/day**

---

## Recommendation Framework

### Recommend Processing Time When:
- CPU time/day is well below break-even (< 50% of threshold)
- Workload is irregular or unpredictable
- Just starting out or testing
- No strict SLA requirements

### Recommend Reserved EEs When:
- CPU time/day exceeds break-even threshold
- Heavy UI/dashboard usage (many users, frequent refreshes)
- Strict SLA requirements (< 1s response)
- Predictable, steady workload

### Transition Strategy
For clients starting out: begin with Processing Time, monitor actual usage, transition to 1-2 Reserved EEs when daily CPU time consistently exceeds 2-3 hours/day.

---

## Report Template

When presenting an estimate, include these sections:

### A) Executive Summary
- Context and client situation
- Top-line recommendation (PT vs EE)
- Key numbers: CPU hours/day, EEs needed, annual cost

### B) Numeric Summary Table

| Metric | Value |
|--------|-------|
| Business Flows | X |
| Total Processes | Y |
| Total Executions/Month | Z |
| Total Actions/Month | A |
| CPU Hours/Month | B |
| CPU Hours/Day | C |
| Peak Concurrency | D |
| EEs Required | E |
| Processing Time Cost (Annual) | Euro F |
| Reserved EE Cost (Annual) | Euro G |
| Break-Even | H hours/day |

### C) Inputs Summary
Mark each input as: [Confirmed] / [Deduced] / [Fallback Default]

Include working schedule assumptions (H, D).

### D) Detailed Calculations
Show formulas and intermediate results for transparency.

### E) Sensitivity Analysis
Run +/- 20% on key variables:
- Volume +20%: CPU hours = X, Cost = Y
- Volume -20%: CPU hours = X, Cost = Y
- Alternative H/D scenarios

### F) Recommendation & Next Steps
- Clear recommendation with rationale
- Suggested transition path if applicable
- What additional data would refine the estimate

---

## Quick Reference: Safe Defaults

When data is missing, use these conservative defaults:

| Parameter | Default | Rationale |
|-----------|---------|-----------|
| Processes/flow | 3 | Standard modularization |
| Actions/business process | 13 | Typical complexity |
| Actions/UI process | 5 | Range 4-7, use midpoint |
| UIs/flow | 2 | Dashboard + detail view |
| Users | 10 | Small team |
| Refreshes/user/day | 5 | Moderate usage |
| % Active UIs/day | 50% | Not all screens used daily |
| Action duration (business) | 0.5s | Includes external latency |
| Action duration (UI) | 0.3s | Simpler queries |
| Peak factor | 2.5x | Industry standard |
| H (hours/day) | 6 | Conservative fallback |
| D (days/month) | 20 | Working days |

---

## Edge Cases

### No UI Component
Skip the UI calculation section entirely. Focus only on business process load.

### UI-Only / Reporting Project
Minimal business process load. UI workload dominates. Size for concurrency (response time SLA) more than CPU hours.

### Strict SLA (< 1s UI Response)
Increase EE count beyond the calculated minimum. Explain the trade-off: more EEs = faster response but higher cost.

### Very High Volume
If calculated EEs > 5, consider:
- Process optimization (reduce actions/process)
- Async processing patterns
- Caching strategies
- Batch processing instead of real-time

### Unknown Data
If critical data is still missing after asking, output two scenarios:
1. **Conservative**: use high-end defaults
2. **Optimistic**: use low-end defaults

Explain which variable caused the uncertainty and what the difference means for cost.

---

## Interaction Flow (When Used Conversationally)

1. Confirm or adjust default pricing
2. Ask for list of business flows (propose examples if none given)
3. Ask for monthly volume per flow
4. For each flow: Does it have a UI? (If yes: # UIs, type, users, refresh rate, % active)
5. Confirm process modularization and action counts
6. Determine working schedule (ask, deduce, or fallback)
7. Run full calculation
8. If key input is missing, pause and ask only that specific value
9. Deliver full report with summary table, break-even, and recommendation

---

## Example Questions to Ask

**Working Schedule:**
> "Do executions occur only during working hours or 24/7? If unknown, I'll use a conservative fallback (6h/day, 20 days/month) to avoid underestimation."

**UI Assumptions:**
> "I've assumed 2 UIs/flow, 10 users, 5 refreshes/day/UI, 50% active daily. Confirm or adjust?"

**Break-Even Context:**
> "At Euro10/h, break-even for 1 EE (~Euro6,132/year) is ~613 CPU hours/year = ~2.6 hours/day at 20 working days."

---

## Cross-References

- **Licensing models & guarantees**: See `references/sales-offer.md`
- **Implementation best practices**: See `references/best-practices.md`
- **Use case evaluation**: See `references/use-case-evaluation.md`
- **Pricing overview**: See SKILL.md > Pricing section
