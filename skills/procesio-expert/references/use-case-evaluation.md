> Last verified: March 2026

# Use Case Evaluation Framework

When a user presents a use case or asks "can PROCESIO do X?", this file defines
the structured evaluation approach. Read this file whenever a use case evaluation
is requested, or when the user wants to understand feasibility for a given scenario.

**Core principle:** PROCESIO is an integration and orchestration platform — it is the
glue between systems. If a task cannot be done natively, it is almost always solvable
by integrating an external tool, with PROCESIO managing the flow before and after.
The answer is almost never "PROCESIO can't do that" — it is "here is how PROCESIO
orchestrates the solution."

---

## Step 0: Prioritization (Run Before Feasibility)

Before evaluating *how* to build something, help the client confirm it's the *right*
thing to build first. Use the CSF priority filter from `automation-philosophy.md`:

1. Reduces a critical business risk? → **Automate first**
2. Creates an audit trail where none exists? → **Second priority**
3. Time-sensitive (must trigger within minutes)? → **High priority**
4. Directly generates revenue? → **High priority**
5. Core, repeated daily operation? → **Medium priority**
6. Primarily cost-reduction? → **Lowest priority**

Only proceed to feasibility evaluation after confirming priority is appropriate.

---

## Evaluation Dimensions (ELVT)

Assess each component of the use case against four dimensions:

| Dimension | Label | What it means |
|-----------|-------|---------------|
| **Execution** | E | Can PROCESIO execute this step natively? (API calls, data transforms, file ops, scripting, scheduling, SQL, etc.) |
| **Language** | L | Does it require NLP, text processing, or language understanding? → Use external LLMs via `Call API` |
| **Vision** | V | Does it require image recognition, OCR, or computer vision? → Use external CV/OCR APIs |
| **Thinking & Learning** | T&L | Does it require AI reasoning, ML predictions, or decision intelligence? → Use external AI/ML APIs |

Most use cases are 100% E (pure execution). L, V, and T&L components are always
solvable via external API integration — PROCESIO orchestrates around them.

---

## Evaluation Output Structure

### 1. Feasibility Breakdown
- List key tasks in the use case
- For each task: which PROCESIO module handles it (Process Designer, Forms & Tasks, Document Designer, on-prem agent, scripting)
- Tag each task with its dimension: (E), (L), (V), (T&L)
- Note any HITL components → handled by Forms & Tasks module
- Identify limitations per task and how they are bridged

### 2. Required External Tools
- List all third-party integrations needed
- Tag each with its dimension: (E), (L), (V), or (T&L)
- Explain the integration method (REST API, sFTP, webhook, etc.)

### 3. New Platform Actions / Features Suggested (if any)
- What new Custom Actions or Platform Actions would streamline this use case?
- Flag for PROCESIO roadmap consideration

### 4. Recommendation
- Confirm: PROCESIO + integrations = 100% achievable (or note genuine blockers)
- Summarize the integration pattern used (Hub & Spoke, HITL, AI Orchestration, etc.)

### 5. Summary Table
- % Achievable with PROCESIO (+ integrations): **100%** (or note genuine blockers)
- Required Third-Party Tools: [list]
- Elements Requiring Third-Party Tools: (E) / (L) / (V) / (T&L)

---

## Output Format

**Default: HTML** — use the template in `scripts/eval-template.html`.
Load and fill in the template placeholders with the evaluation content.

**Use plain text or markdown instead when:**
- The user explicitly requests it
- Context is non-web (terminal, email draft, document)
- It's a quick feasibility check, not a formal deliverable

---

## Limitations Quick-Check (Before Saying "No")

| Limitation | Native | Workaround |
|-----------|--------|------------|
| RPA / desktop UI automation | ❌ (Y5 2030) | External RPA → results via API/storage |
| Web scraping behind login | ❌ | Puppeteer/Selenium → pass results via API |
| Native AI/ML/OCR | ❌ | OpenAI, Azure AI, Google AI, AWS AI via `Call API` |
| DOCX/Word output | ❌ | HTML→DOCX via Custom Action or third-party API |
| JS-heavy dynamic pages | ❌ | Puppeteer/Selenium → pass result to PROCESIO |
| Native ERP connectors (SAP, Oracle) | ❌ | REST API, sFTP, CSV/XML, email |
| BI dashboards | ❌ | Export to Power BI, Tableau, Google Data Studio |
| Files in scripting actions | Partial | Base64 conversion; chunk large files |

**On-prem agent power note:** Runs on Linux/Windows, forwards shell commands to the local
machine, no inbound ports needed. Covers virtually any local automation task.

**Custom Actions (C#) fill any remaining gap.** Always check before declaring impossible:
(a) Custom Action buildable? (b) external tool integrable? (c) on roadmap?

---

## Integration Patterns Reference

| Pattern | Trigger | Typical Use |
|---------|---------|-------------|
| Hub and Spoke | Webhook / Schedule | PROCESIO as central orchestrator; fans out to multiple systems |
| Event-Driven Pipeline | Webhook | Real-time sync on external event |
| Human-in-the-Loop (HITL) | Form / API | Approvals, onboarding, contract sign-off |
| File Exchange | Schedule / sFTP | EDI, bank files, ERP imports/exports |
| Polling Loop | Schedule | Check system state on interval; act on condition |
| Document Factory | Webhook / Form | Invoice generation, contract creation, reports |
| AI Orchestration | Webhook / Form | CV screening, contract analysis, email classification |
| Compliance Filing | Schedule / Webhook | eFactura, eTransport, SAF-T, Peppol |

*Cross-reference: for use case examples by industry and category, see `use-cases.md`.
For prioritization frameworks, see `automation-philosophy.md`.*