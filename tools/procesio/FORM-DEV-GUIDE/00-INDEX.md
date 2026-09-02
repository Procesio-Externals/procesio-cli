# PROCESIO Form Development — the complete guide

Everything needed to build a **professional-grade** PROCESIO form: how the DTO is
shaped, how form-level CSS and JavaScript actually execute, what the runtime DOM
looks like, how to read and write field values, how to build a custom animated
stepper, how to hide and reveal controls, how to wire a control to a process and
get data back into fields, and how to deploy all of it without destroying the
form.

Everything here was **verified against a live form and against the renderer's own
source** (`docs_info/ui-builder-main`). Where something was learned by breaking
the live form, the symptom is recorded next to the rule — see
[08-PITFALLS.md](08-PITFALLS.md), which is the fastest way to avoid repeating a
day of debugging.

## The files, and when to attach which

| File | Attach it when you need to… |
|---|---|
| [01-ANATOMY.md](01-ANATOMY.md) | understand the FormTemplate DTO: elements, configs, sections, the data model, value paths, steppers |
| [02-CODE-INJECTION.md](02-CODE-INJECTION.md) | write ANY form-level JavaScript — this is the one non-negotiable prerequisite |
| [03-DOM-CONTRACT.md](03-DOM-CONTRACT.md) | write CSS or query the DOM — the selector reference and what the renderer guarantees |
| [04-INTERACTION-RECIPES.md](04-INTERACTION-RECIPES.md) | read/write a field, hide a field, gate a button, build a custom control, validate, toast |
| [05-STEPPER-AND-MOTION.md](05-STEPPER-AND-MOTION.md) | build a custom stepper, a step transition, a loader veil, entrance animations |
| [06-PROCESS-INTEGRATION.md](06-PROCESS-INTEGRATION.md) | trigger a process from the form and land its results back in fields |
| [07-DEPLOY-WORKFLOW.md](07-DEPLOY-WORKFLOW.md) | actually ship the CSS/JS to a live form, and test before you do |
| [08-PITFALLS.md](08-PITFALLS.md) | anything — read it once, then keep it attached |

**Minimum viable attachment set** for "add an animation / behaviour to an existing
form": `02` + `03` + `05` + `08`.

## The five-sentence version

1. A form is a **flat list of elements**, each a bag of `configs`, plus a mirrored
   **data model** whose attribute ids must equal the elements' config ids.
2. Form-level CSS and JS live **AES-encrypted in `Data.code`** and are edited with
   `form-get-code` / `form-set-code`, never with `form-edit`.
3. The CSS is injected as a `<style>` into the real page; **the JS is replayed in a
   throwaway sandbox iframe**, so anything that must survive is injected once into
   `window.parent.document`.
4. The renderer destroys and rebuilds controls on every step change (`v-if`), so
   **all state is recomputed from a MutationObserver**, never stored on a node.
5. Behaviour is layered ON TOP of the platform's own — you click the platform's
   real control rather than setting values behind its back, because it is Vue-bound.

## Vocabulary

| Term | Meaning |
|---|---|
| **element** | one control in `Data.elements` — input, paragraph, column, stepper, step… |
| **config** | one `{id, key, value}` entry on an element; `label`, `name`, `visible`, `onClickEvents`… are all configs |
| **value path** | `{dmRootId}.{FIELDS_NS}.{elementId}.{valueConfigId}` — how a process addresses a form field |
| **`Data.code`** | the designer's "Switch to code" editor: the form-level `{CSS, JAVASCRIPT}` pair, stored encrypted |
| **runtime layer** | the JS you inject into the parent document; it outlives individual script runs |
| **veil** | a full-card loader overlay that masks the renderer rebuilding controls |
| **rail** | a custom step indicator drawn by your own JS, replacing the platform's nav |
| **gating** | hiding a control with `display: none` so it also leaves the tab order |

## Related framework notes

- [../dto/form/FORM-STYLING-NOTES.md](../dto/form/FORM-STYLING-NOTES.md) — the four
  styling surfaces (theme, per-element style, element-event JS, form-level code)
- [../PROCESIO-RESOURCE-MODEL-NOTES.md](../PROCESIO-RESOURCE-MODEL-NOTES.md) — the
  export DTO for every resource type, including the flow graph
- [../PROCESIO-API-NOTES.md](../PROCESIO-API-NOTES.md) — auth, endpoints, casing
- [../PROCESIO-FE-VALIDATION-NOTES.md](../PROCESIO-FE-VALIDATION-NOTES.md) — what the
  save-time validation gate rejects
