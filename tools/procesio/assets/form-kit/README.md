# Form kit: the spine of a form runtime

Neutral, tested pieces to start a form-level runtime from, so nobody retypes them. They were
extracted from a family of production forms and stripped of the client's brand. The reasoning
is in [FORM-DEV-GUIDE/10](../../FORM-DEV-GUIDE/10-REDESIGN-METHOD.md).

| File | What it is |
|---|---|
| `runtime.template.js` | Start here: installer, boot order, `refresh()` / `schedule()`, the account-check phases. Copy it beside your form's sources. |
| `core.js` | Helpers, the network monitor (XHR + fetch, keeps the answers of the form's process calls), `runOf()` to read the latest run of a process, toasts, clipboard, the CSS scope fix. |
| `effects.js` | Effects tiers (full / lite / min), the automatic choice, the frame monitor, the viewer's switch panel. |
| `effects.css` | `--kit-*` tokens, toasts, the switch button and panel. Change the tokens, not the rules. |
| `effects_gate.py` | Build step: generates the CSS that stops decorative loops and copies the reduced-motion rules under the tier attributes. |
| `critical.css` | The unscoped first-frame layer. |

**Not in the kit, on purpose:** the visual layer (card, header, loader, background, documents). That
is one client's design, so it stays with that client's sources. The rules that make those parts
cheap are in [08](../../FORM-DEV-GUIDE/08-PITFALLS.md) and [10](../../FORM-DEV-GUIDE/10-REDESIGN-METHOD.md) §10.

## Compose a form

Keep the sources per form in the user-data area, never in the framework
([07](../../FORM-DEV-GUIDE/07-DEPLOY-WORKFLOW.md) §5). A build is about twenty lines:

```python
import base64, re, sys
sys.path.insert(0, KIT)                       # tools/procesio/assets/form-kit
import effects_gate

def strip(css):
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    css = re.sub(r'\s+', ' ', css)
    return re.sub(r'\s*([{};,>])\s*', r'\1', css).replace(';}', '}').strip()

critical = strip(read(KIT + '/critical.css'))
main = strip(read(KIT + '/effects.css')) + strip(read('src/form.css'))
main += ''.join(effects_gate.gates(main, functional=('kit-spin', 'kit-skel', 'my-progress')))
css = '@import url("data:text/css;base64,' + base64.b64encode(critical.encode()).decode() + '");\n' + main

js = read('src/form.js').replace('/*@@KIT@@*/', read(KIT + '/core.js') + read(KIT + '/effects.js'))
```

Minify the JS (`npx terser form.js -c -m`), test the minified file, and ship with
`procesio form-set-code`. Element ids that exist only after a deploy go in an `ids.json` and are
filled in at build time, so the source never holds a literal id of one environment.

## What to fill in

- `CFG` and `EL` in the template. `CFG.FX_KEY`: the same key on every form of a site makes one
  viewer's choice hold across all of them. `CFG.FX_TEXT`: the panel's text in the form's language.
- `functional` in the gate: the keyframes of every loop that reports progress.
- Your own background, if any: `FX.on('bg')`, `FX.listen(fn)`, and call `FX.frame(ts)` from its
  animation loop. Without one, the automatic tier rests on the hardware hints alone.

## Checked

`tests/test_form_kit_asset.py` covers the gate and composes the script. In a browser (2026-10-30, a
minimal page with the renderer's structure): tiers, panel, a saved manual choice, toasts, the
network log. The full runtime this came from has run on live forms.
