# RPA vs PROCESIO — Comparison & Decision Guide

Source: RPA_vs_PROCESIO_use_triggers.xlsx (official PROCESIO comparison sheet)

---

## When/What to Choose — Scored Comparison

1 = this option wins / is recommended | 0 = this option loses / not recommended

| Criterion | RPA | PROCESIO | Notes |
|-----------|-----|----------|-------|
| **Affordable** | Starts from €5,000/year | Starts from €1,200/year | PROCESIO significantly cheaper |
| **Flexible pricing** (execution time, business metrics, etc.) | ✗ | ✓ | Processing Time + EE capacity + volume-based models |
| **Low maintenance** (OS, server/machine, infrastructure) | ✗ | ✓ | PROCESIO-hosted = zero infra maintenance |
| **Higher resilience** | ✗ | ✓ | API integrations don't break; RPA breaks on UI changes |
| **Execution speed** | ✗ | ✓ | PROCESIO: ~10ms/action; RPA: seconds per UI interaction |
| **No infrastructure setup** | ✗ | ✓ | PROCESIO cloud: zero setup required |
| **(Near) Real-time system integrations** | ✗ | ✓ | PROCESIO is event/webhook-driven |
| **When you have APIs or direct data access** | ✗ | ✓ | PROCESIO's primary strength |
| **UI automation** | ✓ | ✗ | RPA's core; PROCESIO Y5 (2030) roadmap |
| **Web scraping** | ✓ | ✗ | RPA handles; PROCESIO scrapes public pages only |
| **Attended processes** | ✓ | ✓ | Both support human-in-the-loop workflows |
| **Keep data only on-premise** | ✓ | On-premise available (>€10k/year) | PROCESIO self-hosted covers this requirement |
| **High complexity projects** | Doable, but hard to manage and even harder to scale | ✓ | PROCESIO designed for complexity at scale |
| **Scalability** | Requires additional setup and configuration; growing maintenance needs with scaling | ✓ | PROCESIO auto-scales; no reconfiguration needed |
| **Middleware / Backend for other systems** | Limited | ✓ | PROCESIO is purpose-built for system orchestration |

---

## Summary Verdict

**Choose PROCESIO when:**
- You have APIs or direct data/DB/file access (covers ~70-80% of real automation needs)
- You need near-real-time integrations
- Scalability without growing infrastructure overhead is important
- You want flexible, affordable pricing (from €1,200/year)
- You are building complex multi-system orchestration
- You need a middleware/backend layer for other applications
- Low maintenance and high resilience are priorities

**Choose RPA when:**
- UI automation of a desktop application is strictly required (no API exists, no alternative access path)
- Web scraping of authenticated or JavaScript-heavy pages is needed
- The only access path to a legacy system is through its graphical interface

**Both work well for:**
- Attended processes (human-in-the-loop workflows)
- On-premise data residency requirements (PROCESIO self-hosted >€10k/year)

---

## Full Feature Comparison

| Dimension | PROCESIO | RPA (UiPath, AA, Blue Prism) |
|-----------|----------|------------------------------|
| **Entry price** | From €1,200/year | From €5,000/year |
| **Pricing flexibility** | Processing time, EE capacity, volume-based | Per-bot / per-user licenses |
| **Infrastructure** | Zero setup (cloud); self-hosted option | Requires VMs or physical machines per bot |
| **Maintenance** | Low — API contracts rarely change | High — UI changes break bots |
| **Reliability** | High — stable API contracts | Fragile — dependent on UI stability |
| **Execution speed** | ~10ms per action | Seconds per UI interaction |
| **Scalability** | Unlimited parallel executions, auto-scaled | Additional setup and config required per scale step |
| **Complex projects** | Designed for it | Doable but hard to manage and scale |
| **UI automation (desktop)** | Not supported today (Y5 2030 roadmap) | Core capability |
| **Web scraping (public)** | Yes | Yes |
| **Web scraping (authenticated)** | Requires 3rd-party (Puppeteer/Selenium) + PROCESIO integration | Yes |
| **API / DB / file integration** | Core capability | Limited |
| **Real-time integrations** | Yes (webhooks, event-driven) | Limited |
| **Middleware / backend** | Core capability | Limited |
| **Human-in-the-loop** | Native (Forms & Tasks module) | Possible but complex |
| **Document generation** | Native (Document Designer) | Not native |
| **Data transformation** | Extensive native actions + scripting | Limited |
| **No-code / Low-code** | Yes | Partial (vendor-dependent) |
| **Full-code scripting** | Yes (C#, JS, Python, NodeJS) | Limited |
| **On-premise deployment** | Yes (self-hosted, >€10k/year) | Yes |

---

## The Hybrid Architecture: PROCESIO + RPA

When RPA is genuinely needed for specific UI-only steps, the recommended architecture is:

1. **PROCESIO** orchestrates the entire end-to-end process
2. **PROCESIO** calls the RPA tool via API when a UI-interaction step is required
3. **RPA** executes the desktop UI task and returns the result
4. **PROCESIO** continues the workflow with the returned data

This gives the best of both worlds: PROCESIO handles all orchestration, logic, data
transformation, and human workflows; RPA handles only the unavoidable UI-only steps.

---

## RPA on the PROCESIO Roadmap

**Year 5 (2030)**: Native RPA capabilities are planned.
PROCESIO will eventually handle both API-based automation and desktop UI automation natively —
eliminating the need for a separate RPA tool entirely for most use cases.

---

## Handling the "We Already Use RPA" Sales Objection

**Common objection:** *"We already use UiPath / we need RPA."*

**Response framework:**
1. **Acknowledge**: RPA is right for UI-only systems. PROCESIO doesn't replace it for those today.
2. **Reframe**: What percentage of your automations actually require UI scraping vs. API/DB access? Typically 70–80% can be done via API — those are where PROCESIO wins on cost, speed, reliability, and scalability.
3. **Show the math**: RPA starts at €5,000/year; PROCESIO starts at €1,200/year. For API-based processes, PROCESIO is faster, more reliable, and significantly cheaper.
4. **Complement, don't replace**: For remaining UI-only steps, PROCESIO can orchestrate and call your existing RPA bots — one unified workflow, easier to maintain.
5. **Future-proof**: Year 5 (2030) roadmap includes native RPA. Your team will already be on the platform when that gap closes.