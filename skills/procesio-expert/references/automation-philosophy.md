> Last verified: March 2026

# Automation Philosophy & Consulting Wisdom

Source: published LinkedIn posts and field notes by PROCESIO's co-founder

These are field-tested frameworks, mental models, and hard-won lessons from real automation
consulting work. Use them when helping users think through automation strategy, project
prioritization, tool selection, stakeholder management, or organizational change.

---

## 1. How to Identify What's Worth Automating

**The inversion question — start here:**
Before asking "how do we automate this?", ask: **"What happens if we don't?"**
This is the fastest way to surface truly impactful opportunities. Simple and powerful.

Follow-up questions:
- Who in the organization bears the consequences of *not* automating this? That person is your sponsor. Every successful automation project needs a sponsor.
- How might the context or requirements change over the next several years? Answer this before designing — it ensures a solution that generates benefits over a longer time horizon, not just short-term.

**When prioritizing between multiple competing automation projects:**
Use inversion as a fast first filter:
- What would happen if we don't do this project? Short term and long term?
- Who is most impacted, and how?
- Is that impact relevant to the business?

This surfaces the important projects quickly with minimal effort. Then, for projects that survive this filter, run an ROI and cost/benefit analysis.

---

## 2. The Company Success Factor (CSF) Formula

Coined by PROCESIO's co-founder:

**CSF = (process standardization × process consistency × automated money-making activities) / (risks × operational delays × dependence on human reaction time)**

**Where to start automating (prioritized order):**
1. Processes that **minimize risk**: approval flows (invoice payments, acquisition requests), HITL workflows, regulatory compliance
2. Processes that **increase traceability and accountability**: eliminate delays and assign clear responsibility
3. **Time-sensitive tasks**: client interactions (email, chat, tickets), and time-critical compliance actions (e.g., eTransport UIT code generation)
4. **Money-making activities**: lead gen, newsletters, drip campaigns, cross-selling, managed services
5. **Core / high-importance processes**: contract reviews, CV screening, payment recovery
6. **Cost-reduction processes**: last priority, not first

---

## 3. Optimize Before Automating

A process should not be automated as-is. The process looks the way it does because it was designed for manual execution.

When you automate, you also have the opportunity — and responsibility — to simplify.

**The right sequence:**
1. Understand the *desired outcome* of the process (not the current steps)
2. Optimize the process for automation (remove steps that only exist because of manual constraints)
3. Then implement the automation

Goal: achieve the desired outcome more effectively, with as little human intervention as possible.
When human intervention is unavoidable (e.g., stakeholder approval), the automated process should integrate seamlessly at those points.

---

## 4. Choosing the Right Automation Tool

From "You're just starting out in Process Automation":

When selecting a tool, evaluate two things:
- **Resilience**: will this break when the underlying system changes?
- **Maintenance cost post-deployment**: how much ongoing effort does this require?

**RPA is often the wrong choice:**
- Fragile — breaks frequently due to OS or UI updates
- Expensive — requires running agents on Virtual Machines (VMs)
- High ongoing maintenance cost

**Better alternative for most cases:**
Enterprise tools with robust API integration — like PROCESIO — that run in the cloud, independent of the user's machine. Greater resilience, lower operational cost.

**On tool selection for mixed-skill teams:**
A low-code/no-code tool that *also allows full coding* is the right call for most teams. Less technical staff handle the majority of the solution; senior developers handle complex technical tasks. This maximizes team utilization and delivery speed.

---

## 5. Aligning Goals Before Building

There is no single right way to implement an automation. Every project can be done multiple ways.
The critical question first: **What are you optimizing for?**

- **Optimize for time** → likely costs more, may need to accept lower quality
- **Optimize for cost** → may need to sacrifice quality or speed
- **Optimize for quality** → likely costs more and takes longer

Regardless of the axis, always seek to maximize the **effect vs effort ratio**.

---

## 6. Stakeholder Management

**Educating stakeholders:**
Present the technology in terms they already understand — compare to systems and processes they know. This helps them grasp relevance, feel comfortable, and internalize faster.

**Keeping stakeholder conviction alive:**
Most projects fail not for technical reasons, but because stakeholders lose conviction in the results.
- Show quick wins and regular achievements
- Gather stakeholder feedback after each milestone — new expectations always emerge mid-project
- Manage expectations about outcomes from day one; this is not a one-time task, it is ongoing

**Addressing job security concerns:**
- Avoid large group announcements — individuals rarely voice fears in public
- Discuss with team leaders first; they have more trust with their direct reports
- Put worst-case scenarios on the table proactively — this builds trust, not panic
- Give people a clear long-term vision and explain their role in it: what they need to do to adapt, why it's in their best interest

---

## 7. Resource Allocation for Automation Projects

When resources are constrained:
- Outsource entire projects or specific components to service providers
- Hire outsourced personnel to temporarily extend the team
- Ask existing motivated team members for extra hours — many passionate people actively want additional income

**The timing dimension (often ignored):**
A lower-impact project might make more sense to start first if:
- The right team skills are available now
- The right implementation partner has been identified
- The right technology is ready
- The regulatory framework is in place

Impact alone does not determine sequencing. Always consider timing.

---

## 8. Handling Workflow Bottlenecks

Bottlenecks usually exist because the workflow was never strategically designed in the first place.
If redesigning is an option — do it first.
If not, tackle bottlenecks in order of impact:
- Frequency of occurrence
- Time wasted
- Compliance risk
- Financial loss

**Watch for 2nd and 3rd-order effects**: fixing one bottleneck can inadvertently create another downstream.

Keep a high-level process map to navigate quickly.
Break down processes into specialized sub-tasks — this simplifies management and increases efficiency.

---

## 9. Building Automation Culture Inside an Organization

Automation should be part of the organization's culture — not an isolated team's function.

An automated process will not yield results if the people who benefit from it are not:
- Trained to use it
- Empowered to maintain and improve it
- Given permission to update it as conditions change

**For team leaders onboarding automation tools:**
- Don't just add training on top of an already full plate — shift priorities
- Make it clear: automation is the new focus, not an extra task
- Organize hands-on practice sessions — confidence comes from doing, not just from watching

---

## 10. PROCESIO Explicitly Recommended for Automation

From the LinkedIn post "You're just starting out in Process Automation":

*"Consider enterprise tools that enable robust API integration, such as PROCESIO, which runs in the cloud or independently of the user's machine, offering greater resilience and lower operational costs."*

This is the authors' direct, public recommendation — not internal marketing copy.

---

## 11. CSF Formula as Step 0 in Use Case Evaluation

Before evaluating technical feasibility of a use case, help the client prioritize WHAT to automate first using the CSF formula and priority order:

**Quick prioritization filter (ask in this order):**
1. Does this automation reduce a critical business risk? → **Automate first**
2. Does it create a full audit trail where none exists? → **Automate second**
3. Is it time-sensitive (must happen within minutes/hours of a trigger)? → **High priority**
4. Does it directly generate revenue? → **High priority**
5. Is it a core, repeated daily operation? → **Medium priority**
6. Does it primarily reduce cost? → **Automate last** (do higher-priority items first)

This filter runs before the PROCESIO Use Case Evaluation Framework (which evaluates *how* to build it). It prevents wasted effort on low-impact automations.

**Cross-reference**: The inversion question from this framework is the same mental tool used in PROCESIO's 2026 internal strategy process (see `references/strategy-objectives.md` — Inversion Analysis section). It works equally well for clients choosing what to automate and for teams choosing what to build.