# PROCESIO form styling - RESOLVED & implemented (2026-06-25)

All four styling surfaces are now understood (verified against the ui-builder frontend
source in `docs_info/ui-builder-main`) and buildable via `builder.py`.

> **Building a real form?** This file is the reference for the four *surfaces*. The
> full development guide - execution model, DOM contract, interaction recipes,
> custom steppers and motion, process wiring, deployment, and the pitfall catalogue - 
> is [`tools/procesio/FORM-DEV-GUIDE/`](../../FORM-DEV-GUIDE/00-INDEX.md). Those files
> are written to be attached as chat context.

## 1. Form Theme - ✅ implemented
`Data.theme`: 23 groups, ~270 CSS variables (`{label,types,properties:[{type,label,
value,cssVariable}]}`; the Colors group's `properties` is `{light: [...], dark: [...]}`).
Pass `theme:{"--c-primary":"#0039e3","--h-input":"44px"}` (Colors overrides land on the
light side) and `themeDark:{...}` for the dark side; `_apply_theme` overrides by
`cssVariable`. A variable the theme does not define is reported in `warnings`, never
silently dropped. Form-wide, by control type.

Defaults = the DESIGNER's `getDefaultTheme()`: the theme a form saved in the designer
carries. `dto/form/sync_theme.py` runs ui-builder's `theme.ts` with Node at the tag the
designer pins and writes `data_shell.json` (theme only) plus `theme_source.json` (tag,
hash, groups); `procesio-release ui-builder-sync` calls it, and `fe-pins` reports
`shell_theme_stale` when the designer moves. ⚠ Keep it on the designer's line: the runtime's
line drops a few variables the designer still saves, and a shell older than the designer
loses every override of a newer variable without a word (69 variables and five groups,
including all of Document Signing, until 2026-11). The runtime applies the theme as rules on
the form containers (`getThemeStyleRules`), no longer as one palette stylesheet.

## 2. Element event JavaScript - ✅ implemented
Per-control onClick/onInput/etc → `{action:"RUN_JAVASCRIPT", config:{code}}` (plaintext)
in the element's event config. `events:[{on:"click",do:"js",code:"..."}]`.

## 3. Per-component styling - ✅ implemented
Each element has a `{key:"style", category:"styling"}` config whose value is a
`CSSProperty[]` (`{label,value,cssVariable,type,enabled}`). The runtime
(`useThemable.themeStyle`) applies ONLY `enabled:true` props, overriding
`style[cssVariable]=value` (wrapping in `var(value)` when `type==css-variable-select`).
Build it by passing per-element `style:{cssVariable:value}`:
```json
{"type":"input","label":"Name","style":{"--h-input":"50px","--c-input-background":"--c-neutral--50"}}
```
- Valid vars = the element type's CSS group (frontend `getCssGroupByElementType`: FIRST
  theme group whose `types` include the type - so input/number/datetime/textarea/select all
  use the **Input** group). Unknown var → hard error (lists valid ones). Non-stylable types
  (heading, paragraph, divider, image…) → error.
- For `css-variable-select` vars (colors) pass a theme color VARIABLE (e.g. `--c-neutral--50`),
  NOT a hex - the runtime emits `var(<value>)`. Plain vars (height/padding) take raw values.
- Builder: `_apply_element_style` + `_style_props_for` (reads groups from `data_shell.json`).

## 4. Form-level CSS + JavaScript ("Switch to code") - ✅ implemented
Stored encrypted in `Data.code`. **Scheme (verified by decrypting real exports):**
`code = AES_encrypt( JSON.stringify({"JAVASCRIPT":js,"CSS":css}) )` using CryptoJS
`AES.encrypt(text, passphrase)` = OpenSSL AES-256-CBC, key+IV via EVP_BytesToKey(MD5,1),
output `base64("Salted__"+salt+ct)`. Passphrase = a static key.
- **Key is in Credential Manager**, one per installation, stored per environment as
  `agents-and-tools:procesio:form-code-key@<environment>` (the bare `form-code-key` is
  the default environment's; `tools/procesio/form_code_keys.py`) - NEVER in any file
  (Hard rule 1). Declared in `tool.yaml` secrets.
- Build via `css:"..."` / `javascript:"..."` (or `code:{css,javascript}`) on the form
  config. Empty → `code:""` (forms render fine without it). Impl: `code_cipher.py`
  (`encrypt_code`/`decrypt_code`) + `builder._build_code`.
- The frontend itself only holds `code` as a plaintext `{JAVASCRIPT,CSS}` object and runs
  the JS as a RUN_JAVASCRIPT form event at render; the host webapp does the AES step. There
  is NO plaintext css/js field on the DTO (team confirmed: no unencrypted path).

## 5. Restyling an EXISTING form - use `form-set-code`, never `form-edit`
`form-edit` is a desired-state editor: it rebuilds the whole DTO from a config, so
pointing it at a large hand-authored form to change one field means re-declaring every
element or losing them. Use the surgical pair instead (handlers/form_code.py):
`form-get-code --id <id>` (decrypt) / `form-set-code --id <id> --css-file … --js-file …`
(GET → swap `Data.code` → PUT the same DTO back). Only `Data.code` changes; omitting one
of css/js preserves that side; the overwritten code comes back under `previous`, so a
mistaken overwrite is recoverable from the tool output alone.
- `PUT /api/FormTemplate` wants the PascalCase envelope (`Id/Name/IsPrivate/Type/Status/
  State/Assignees/Data/CustomUrl`) while the GET returns it camelCase - map explicitly.

- **`{"JAVASCRIPT": null, "CSS": null}` is a NORMAL decrypt result, not a corrupt blob.**
  The designer seeds both slots to null, so that is what every form that never opened
  "Switch to code" carries - and a form can also carry a JS slot holding only the
  designer's boilerplate comment. Normalize null → `""` before doing anything with a
  length or a concatenation (`_decode` does; a `len(None)` crash here was a real bug).
- **A wrong passphrase and a corrupt blob are indistinguishable at the API layer**: both
  surface as a `UnicodeDecodeError` after AES runs and emits garbage. Diagnose by
  round-tripping `encrypt_code`/`decrypt_code` with a throwaway key - if that works, the
  blob is fine and the KEY is wrong. Note also that the workspace API key (name + value)
  and the form-code passphrase are DIFFERENT secrets that look alike (short opaque
  tokens); the API key gets you *at* the form, the passphrase gets you *into* `Data.code`.

## 6. What the CSS and the JS can actually reach at runtime
- **CSS is injected as a `<style>` PREPENDED INSIDE the form root, and SCOPED to it**
  (changed in v3.0.0, 2026-10; before, it styled the whole document and page-level
  selectors worked). Every selector is rewritten to
  `sel:where([data-form-css-scope=<id>], ...)`, matching the form root and its
  descendants only. So rules for `body`, `:root`, `html`, the host chrome and the builder
  match nothing, `:root` custom properties no longer reach the form, and tooltips and
  date-picker popups no longer get the form CSS. Comments and unparsable CSS are dropped;
  `@keyframes` / `@font-face` are moved into a layer. Still global: a `<style>` inside
  paragraph/heading HTML, `@import`, and JS that injects a `<style>` into
  `window.parent.document`. JS that renders UI OUTSIDE the form container (appended to
  `document.body`, a modal or overlay, a full-page app) gets no styles, and `:root` /
  `html` / `body` rules stop applying: before mounting, copy the container's
  `data-form-css-scope` value onto `<html>` (inside the wait-for-render loop). Full rules
  and the snippet in `tools/procesio/FORM-DEV-GUIDE/02-CODE-INJECTION.md` §2.
- **The branding class is also filtered** (`js/form-builder/css.ts` replaces that literal
  string with a random number so it cannot be hidden).
- **Form-level JS is replayed as a synthetic RUN_JAVASCRIPT event on mount and on every
  re-trigger, inside a throwaway sandbox iframe whose window is destroyed and rebuilt each
  time.** So anything that must OUTLIVE one run (listeners, MutationObservers, timers)
  cannot live in that scope - it dies with the iframe. The pattern that works: from the
  sandbox, inject a `<script>` ONCE into `window.parent.document`, carrying the real
  runtime (`'(' + fn.toString() + ')();'` avoids escaping). Guard both layers with a
  flag - the installer re-runs, and a second copy means doubled handlers. The platform
  confirms the reach itself: the JS slot's shipped boilerplate reads
  `console.log(window.parent.document); -> to access the DOM`.
- **Controls are re-created, not hidden**: `Element.component.vue` renders under `v-if`,
  so toggling `visible` removes the node from the DOM. Entrance animations therefore fire
  on every step change (good), but exit transitions are impossible (the node is gone), and
  any state you attach to a node must be recomputed from a MutationObserver.
- **Runtime selectors** are two families: `.form-builder--*` (the renderer's own, e.g.
  `--form`, `--form-body`, `--element[data-element-id]`, `--stepper--nav--item`,
  `--stepper--container`, `--stepper--buttons`, `--input`, `--select`, `--checkbox`,
  `--radiobox`, `--file-upload`, `--columns`, `--column`) and `.pds-c-*` from the design
  system (`--input-group--wrapper` / `--wrapper--focused` / `--wrapper--is-error`,
  `--input-group--label`, `--input-group--message--is-error`, `--input-group--square`,
  `pds-c-radiobox--is-checked`, `pds-c-button--solid-primary`, `pds-c-step--header--circle`
  `[--active]`, `pds-c-step-connector`). The `pds-c-*` INTERNALS are not in this repo
  (they ship in `@procesio/procesio-design-system`), so only the ones the renderer's own
  SCSS references are safe to target - anything deeper must be checked against a live
  render first.

## Source of truth
`docs_info/ui-builder-main` is the actual frontend repo. Confirmed: its
`src/js/model/element/mock.ts` is byte-identical to `FormBuilder mock.ts` (our goldens come
from it), and its `src/js/model/config/index.ts` enums match `form-config-enums.ts` exactly.

## Dark theme + element alignment (2026-08)

**Dark theme.** A form carries both a light and a dark palette, swapped at runtime by
`themeMode`/`activeThemeMode`. Since the shell follows the designer (2026-11), every
API-built form carries both sides, as a designer-saved one does; `themeDark` overrides
the dark side and `dark` is kept only for older configs. The builder's 16-var
`_DARK_PALETTE` (`--c-primary` #4663f5 …) now only serves an older flat shell.
`themeMode` and `themeDark` are never saved in `Data`.

**Element alignment.** Container elements accept three flex vars in their per-control
`style`, keyed by an element SCOPE suffix: `--fd-<scope>` (flex-direction / "Inner
direction"), `--jc-<scope>` (justify-content / "Inner main axis"), `--ai-<scope>`
(align-items / "Inner cross axis"). Scopes: section, list-item, column, step, tab,
side-panel (element types section, list, columns, stepper, tabs, side-panel). The shell
now defines them natively (Section, List, Column, Step, Tab, Side Panel groups), with the
designer's dropdown type and options; `_alignment_props` stays as the fallback for an
older shell, and the native definition wins.

## Buttons render LAST inside a section (2026-11)

The runtime moves a section's `button` controls to the end of the section's container, whatever
their position in `Data.elements` (measured on a public form: input, button, paragraph rendered as
input, paragraph, button). The container `.form-builder--section--container` is a flex column, so
put the order back with CSS `order` on its children, using `:has()` for wrappers you cannot class
directly:

```css
.form-builder--section--container > :has(.my-button-class) { order: 3; }
.form-builder--section--container > .my-paragraph-class { order: 4; }
```

`classes` on a paragraph land on its wrapper div (the container's direct child); on a button they
land on the button element, hence `:has()`.

## Readable form URL: the workspace slug (2026-11)

`forms.procesio.app/{masterSlug}/{workspaceSlug}/{formSlug}` needs all three. A workspace with no
slug gets one with `post-customurl-workspace --workspace-id <ws> --body '"<slug>"'`: the body is a
bare JSON string. An object body (`{"Type":2,"Url":...}`) answers 400 "Unexpected character
encountered while parsing value". The form slug is `post-customurl-formtemplate` with
`{"Type":3,"EntityType":1,"EntityId":<formId>,"Url":<slug>}`.
