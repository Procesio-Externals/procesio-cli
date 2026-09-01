> Last verified: March 2026

# PROCESIO Best Practices for Implementation

Source: https://docs.procesio.com/best-practices-for-implementing-with-procesio

---

## 1. General Principles

### 1.1 Frame the Work Before Building
- **Start with outcomes**: define one measurable KPI per process (e.g., "reduce onboarding cycle time by 30%")
- **Map as-is → to-be**: capture triggers, systems, data contracts, SLAs, exceptions
- **Define RACI early**: business owner, builder(s), reviewer, approver, operator
  - Roles: Responsible | Accountable | Consulted | Informed

### 1.2 Solution Design Principles

**Modularize — but with trade-offs in mind:**
- One main process + small reusable subprocesses (auth, paging, validation, notifications)
- Too many subprocesses → harder debugging, extra execution time overhead
- No subprocesses → monolithic, hard to debug, forces re-executing unnecessary steps
- Find the right balance per use case

**Stable contracts (DTO-style):**
- Standardize input/output using DTO-style variables
- Avoid passing raw API payloads between steps
- Define Data Model variables (e.g., `Customer`, `OrderLine`, `Address`) and reuse them

**Idempotency:**
- Design so that triggering the process twice has no negative impact on records
- Use external IDs and dedupe keys
- Use Error Ports to capture and handle errors without silent failures

**Stateless core:**
- PROCESIO variables are ephemeral — they only live within a single execution
- Do NOT rely on PROCESIO to "remember" things between runs
- Anything that must persist across runs (checkpoints, last-sync time, job status, idempotency keys, approval states) must live in a **durable system of record** — the CRM/ERP/DB/ticketing tool
- Use PROCESIO variables only for transient orchestration within one execution (tokens, page cursors, correlation IDs, etc.)

**Perceived speed — CRITICAL:**
- Users must feel the UI is fast and responsive — this directly impacts client perception of PROCESIO
- The 1s / 3s rules (see Forms section below) must be followed at all times
- A slow PROCESIO form will always be blamed on PROCESIO, not on bad implementation — this must never happen

**Secrets management:**
- NEVER hardcode secrets or credentials inside processes
- Always use the **Credential Manager** for all secrets
- Bad practice: writing plain text credentials directly in process actions

**Parameter centralization:**
- When the same parameter is used across multiple processes and might change, define it in ONE place
- Changes propagate automatically — no need to update every process
- Bad practice: duplicating the same hardcoded value across 10 processes → guaranteed maintenance problems

---

## 2. Integration Best Practices (1–2 days for first system)

**Wrap each external API in a reusable subprocess:**
- `auth-get-token`
- `<system>-get-by-id`, `<system>-search`, `<system>-upsert`
- Pagination helper
- Rate-limit handler

**Implement retry with exponential backoff + jitter:**
- Attempt 1 → wait ~5s
- Attempt 2 → wait ~10s
- Attempt 3 → wait ~30s
- Attempt 4 → wait ~1 min

**Idempotency keys:**
- Goal: the same logical action runs exactly once, even if the process retries or is triggered twice
- Use external IDs or generated dedupe keys as idempotency keys

**Standard error object:**
- Define a consistent error structure across all integration subprocesses

---

## 3. Data Contracts (ongoing)

- Define DTO variables: `Customer`, `OrderLine`, `Address`, etc.
- Model data structures using PROCESIO **Data Models** — this allows direct attribute access without needing JSON extraction actions
- Reuse Data Model children of the same parent DM where appropriate
- **Anti-pattern**: extracting data from JSON objects using multiple Extract JSON actions → overcomplicated logic, too many actions, poor performance
- **Best practice**: model the JSON structure as a Data Model; use it as `type<DataModel>` in the process → direct attribute access, zero extra actions needed

---

## 4. Robustness

**Error handling via Error Port + Decisional:**
- **Retryable errors**: `retry(max=3, backoff=2^n)`
- **Business errors**: send to queue + notify process owner
- **Hard failures**: alert, capture full context (correlation ID, input data, timestamp), stop

**Correlation IDs:**
- Generate a correlation ID at the start of every main process
- Pass it to all logs, API requests, and subprocesses
- Store the process instance ID of the main process when appropriate
- Set a specific status (success/fail/custom) for traceability

**Alerting:**
- Add alerts on failure thresholds (e.g., if same process fails 3× in a row, notify operations team)

---

## 5. Documentation & Handover

- Write documentation on each process
- Map the order in which processes are triggered (visual map if necessary)
- Think in terms of **SOPs (Standard Operating Procedures)**: someone unfamiliar with the implementation should be able to debug or follow the logic purely from documentation
- Good processes are self-documenting through naming, structure, and inline descriptions

---

## 6. SQL Server Best Practices

> Also available as a dedicated GPT: https://chatgpt.com/g/g-68c3c809729c819183056807a6b51150-sql-server-optimizer-for-procesio

### 6.1 Parameter Injection
- **Always** use action parameters to inject data into SQL statements — never string-concatenate user data
- Centralize all parameters at the beginning of the SQL statement for readability
- Parameters are always on the **RIGHT-hand side** of an operation:
  ```sql
  -- GOOD
  WHERE I.InvoiceId = @Param_InvoiceId

  -- BAD (will error)
  SELECT *, @Param_InvoiceId FROM Invoices
  ```
- Parameters can share names with internal SQL variables — the compiler handles it safely
- Use each parameter only once in the statement, especially when parameter names match internal variable names

### 6.2 Post-Injection Cleaning
- After parameter injection, perform a **cleaning operation** on SQL variables holding injected data
- This ensures the rest of the SQL statement behaves as expected, since the SQL engine doesn't always optimize execution plans

### 6.3 FROM and JOIN Order
- Select from the **smallest table first**, largest last:
  ```sql
  -- GOOD
  SELECT * FROM Invoices INNER JOIN InvoiceArticles

  -- BAD
  SELECT * FROM InvoiceArticles INNER JOIN Invoices
  ```
- Join conditions: apply **most restrictive first**:
  ```sql
  -- GOOD
  ON IA.InvoiceId = I.InvoiceId AND IA.ArticleStatus = 1

  -- BAD
  ON IA.ArticleStatus = 1 AND IA.InvoiceId = I.InvoiceId
  ```
- Use **INNER JOINs before LEFT JOINs** — INNER joins reduce row count for subsequent joins
- **Maximum 5–6 JOINs per statement**: permutations grow factorially (5!=120, 6!=720, 7!=5040, 8!=40320) — more joins = engine can't optimize → defaults to worst-case execution plan

### 6.4 WHERE Clause Optimization
- Apply conditions from **most to least restrictive**:
  ```sql
  -- GOOD: precise filter first
  WHERE I.InvoiceId = 123 AND I.IssueDate >= '2025-04-11'

  -- BAD: date range first
  WHERE I.IssueDate >= '2025-04-11' AND I.InvoiceId = 123
  ```
- **Pre-calculate values** before the SELECT — do not compute per-row inside SELECT or WHERE:
  ```sql
  -- GOOD: pre-calculate once
  SET @calcFixed = CASE WHEN @var IS NULL THEN 1 ELSE 2 END
  SELECT CASE WHEN @calcFixed = 1 THEN I.Col1 ELSE I.Col2 END FROM Invoices

  -- BAD: evaluated for every single row
  SELECT CASE WHEN ISNULL(@var,'') = '' THEN I.Col1 ELSE I.Col2 END FROM Invoices
  ```

### 6.5 Conditional Filters Pattern
- Each optional filter should **only activate when a value is provided**:
  ```sql
  -- GOOD: filter is a no-op when param is NULL
  SET @UIT = CASE WHEN ISNULL(@UIT,'') = '' THEN NULL ELSE @UIT END
  WHERE (@UIT IS NULL OR UC.UIT LIKE '%' + @UIT + '%')

  -- BAD: LIKE '%' scans entire table even when no filter intended
  WHERE UC.UIT LIKE CASE WHEN @UIT = '' OR @UIT IS NULL THEN '%' ELSE '%' + @UIT + '%' END
  ```

---

## 7. Forms & Tasks Performance Rules

### The Three Performance Tiers (non-negotiable)

**Tier 1 — Target: <1s on 90% of user actions**
- Minimize process calls from forms — use built-in form features first
- When a process must be called: aim for **1 action** (good), **3 actions** (acceptable), **5 actions** (bad), **>5 actions** (really bad)
- Limit full-page loading screens — use section-level loading indicators instead
- Implement **pagination + filtering** for any table that might grow large

**Tier 2 — Acceptable: 1–3s on <10% of user actions**
- Apply all Tier 1 rules first
- For complex tasks that still take >1s: **break into sequential sub-steps**, each <3s, update the UI visually after each step completes
- User perceives multiple fast steps as faster than one slow step

**Tier 3 — Never allowed: >3s on any single user action**
- If unavoidable: implement **async processing** — user continues working, gets notified on completion
- A blocking >3s wait is always unacceptable in a form context

### Why This Matters
Users cannot know whether slowness comes from PROCESIO, the network, or the integration. They will always blame PROCESIO. A slow form permanently damages client trust in the platform.

---

## 8. Process Optimization for Speed

**Core principle:** Every action takes ~10ms to execute (platform actions, under normal conditions). External calls (APIs, SQL, FTP) dominate execution time.

**Two levers for speed:**
1. **Reduce action count** — fewer actions = faster process
2. **Optimize external calls** — faster SQL, fewer API calls

**Anti-pattern: chained Decisional actions**
- 5 sequential Decisional actions ≈ ~2s execution time
- **Fix**: consolidate into a single Decisional action with all conditions → <200ms

**Anti-pattern: JSON extraction chains**
- Multiple JSON extraction actions to parse a nested object → many actions, poor performance, messy design
- **Fix**: model the JSON as a **Data Model**, reference attributes directly → zero extraction actions needed

**Best pattern: scripting actions for complex logic**
- A single NodeJS/Python/JavaScript/Ruby action replacing 10+ chained actions is almost always faster and cleaner
- Use scripting when the logic is complex enough that visual actions become a bottleneck

**Best pattern: CSV for large Excel files**
- For large Excel files (>10,000 rows), use **Read Range from CSV** and **Split Workbook to CSV** actions
- CSV processing is significantly faster than Excel native operations
- Workflow: Split Excel → process CSVs → reassemble if needed
- This pattern dramatically reduces processing time for data-heavy workflows

**Speed:** PROCESIO's current benchmark is ~10ms/action for platform actions. The strategic goal is to maintain this benchmark as the platform scales.

---

## 9. Platform Tricks

Reference: https://docs.procesio.com/platform-tricks
(A curated collection of non-obvious platform capabilities and shortcuts — consult when a user asks about advanced usage patterns)

---

## 10. On-Prem Agent Integration Patterns

The on-prem agent is more powerful than most implementors realize. Use it whenever:
- The target system lives inside a private network with no public API
- You need to run shell/command-line scripts on a local machine
- You need to access local databases (SQL Server, file system, local services)
- Security policy prohibits exposing any inbound ports

**Agent capabilities:**
- Runs on Linux and Windows
- Executes shell commands and local scripts
- Connects to local DBs and file systems
- Initiates outbound-only connections — no firewall rule changes required
- Available on Business+ plans

**Common on-prem agent patterns:**

| Pattern | How it works |
|---------|-------------|
| Local DB access | Agent runs SQL against a DB inside the private network → returns results to cloud PROCESIO process |
| File system watch | Schedule triggers agent to check a local folder → pickup → process → move/archive |
| Legacy system CLI | Agent calls a command-line interface of a legacy app that has no API |
| Hybrid cloud/on-prem | Cloud PROCESIO orchestrates the flow; agent handles the private network steps |
| Local script execution | Agent runs a Python/PowerShell script and returns output to the process |

**Key principle**: The on-prem agent effectively extends PROCESIO's reach into any private environment. Before declaring a local system "unreachable," always check if the agent can bridge the gap.

---

## 11. Common Anti-Patterns to Avoid

| Anti-pattern | Problem | Fix |
|-------------|---------|-----|
| Hardcoding credentials in process variables | Security risk; breaks on rotation | Always use Credential Manager |
| Storing state in process variables across runs | Variables are ephemeral — lost when process ends | Use external DB, sFTP, or (soon) Data Store |
| Chaining 5+ Decisional actions sequentially | ~2s execution time; hard to debug | Consolidate into one Decisional with all conditions |
| JSON extraction chains (multiple Extract JSON) | Many actions, slow, fragile | Model JSON as Data Model; use attribute access |
| Monolithic 100-action processes | Hard to debug, test, reuse | Break into modular subprocesses |
| Building without idempotency | Duplicate processing on retry | Add idempotency keys for all state-changing operations |
| Hardcoding URLs/values across 10 processes | Maintenance nightmare | Centralize in a config process or Data Model |
| Not using Error Port | Silent failures | Every critical section needs Error Port + alerting |
| Triggering full process on every form field input | Performance degradation | Use built-in form validation; trigger process on submit only |
| Not testing with production-volume data | Performance surprises at go-live | Always load-test before launch |