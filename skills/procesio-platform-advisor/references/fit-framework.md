# Fit and prioritization framework

## Feasibility screen

Score each dimension as proven, plausible, or blocked:

1. **Reachability:** Is there an API, database, file, webhook, email, custom action, or controlled human step for every system boundary?
2. **Identity and security:** Can authentication, secret rotation, least privilege, tenant/workspace scope, and audit requirements be met?
3. **Data semantics:** Are schemas, identifiers, transformations, volume, retention, and error records understood?
4. **Control flow:** Are retries, timeouts, idempotency, compensation, approvals, and manual exception paths designed?
5. **Operations:** Can owners observe, replay, support, and change the automation safely?
6. **Economics:** Does the measured workload and operating effort beat credible alternatives?

A single blocked mandatory dimension makes the current design infeasible. It may still be feasible with a changed boundary or an external component.

## Prioritization

Prefer a first automation with:

- high business impact and frequency;
- stable inputs and outputs;
- clear process owner;
- observable success;
- bounded failure cost;
- available test data;
- few unresolved external dependencies.

Do not automate an undocumented process merely because it is repetitive. Map current reality, exception paths, and ownership first.

## Recommendation levels

- **Proceed:** critical boundaries are proven and a representative test is available.
- **Spike:** one or two material uncertainties can be resolved cheaply.
- **Redesign:** goal is valid but the proposed integration/control boundary is wrong.
- **Do not proceed yet:** mandatory access, compliance, data, ownership, or economics is unresolved.
