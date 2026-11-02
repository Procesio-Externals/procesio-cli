"""Generated CSS for the form kit's effects (effects.js, FORM-DEV-GUIDE/05 §7).

gates(css) takes a form's whole stripped CSS and returns two generated rule sets, so a new
animation is covered the day it is written, with no list to keep:

- loop: every rule whose `animation` has a repeating part gets a twin under
  html[data-<prefix>-fx-loop="0"] that keeps only its finite parts (an entrance keeps
  running), or `none`. Loops that tell the viewer something is happening stay: pass their
  keyframe names as `functional` (spinners, skeletons, a progress bar).
- motion: the rules inside every `@media (prefers-reduced-motion: reduce)` block, again
  under html[data-<prefix>-fx-motion="0"], so the lowest tier is exactly the form's own
  reduced motion.

The twins sit in the same @media as their source. Append both to the CSS you ship.
"""
import re


def _blocks(css, i=0):
    """Yield (prelude, body) at one nesting level; body is the raw text between braces."""
    n = len(css)
    start = i
    while i < n:
        c = css[i]
        if c in '"\'':
            j = css.index(c, i + 1)
            i = j + 1
            continue
        if c == ';':
            start = i + 1
        elif c == '{':
            prelude = css[start:i].strip()
            depth, j = 1, i + 1
            while depth:
                d = css[j]
                if d in '"\'':
                    j = css.index(d, j + 1)
                elif d == '{':
                    depth += 1
                elif d == '}':
                    depth -= 1
                j += 1
            yield prelude, css[i + 1:j - 1]
            i = j
            start = i
            continue
        i += 1


def _split(s, sep=','):
    """Split on `sep` outside parentheses and quotes."""
    out, depth, cur, q = [], 0, [], None
    for c in s:
        if q:
            cur.append(c)
            if c == q:
                q = None
            continue
        if c in '"\'':
            q = c
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        elif c == sep and depth == 0:
            out.append(''.join(cur).strip())
            cur = []
            continue
        cur.append(c)
    if ''.join(cur).strip():
        out.append(''.join(cur).strip())
    return out


def _prefix(selectors, attr_html):
    attr = attr_html[len('html'):]
    out = []
    for s in _split(selectors):
        if re.match(r'html(?![\w-])', s):
            out.append('html' + attr + s[4:])
        elif s.startswith(':root'):
            out.append(':root' + attr + s[5:])
        else:
            out.append(attr_html + ' ' + s)
    return ','.join(out)


def _keyframes(css):
    return set(re.findall(r'@(?:-webkit-)?keyframes\s+([\w-]+)', css))


def _loop_twin(selector, body, names, keep_running, loop_attr):
    for decl in _split(body, ';'):
        m = re.match(r'animation\s*:\s*(.+)$', decl, flags=re.S)
        if not m:
            continue
        value = re.sub(r'\s*!important\s*$', '', m.group(1).strip())
        parts = _split(value)
        keep, dropped = [], False
        for p in parts:
            tokens = re.findall(r'[\w-]+', p)
            name = next((t for t in tokens if t in names), None)
            if 'infinite' in tokens and name not in keep_running:
                dropped = True
            else:
                keep.append(p)
        if dropped:
            return _prefix(selector, loop_attr) + '{animation:' + (','.join(keep) or 'none') + '!important}'
    return ''


def _walk(css, names, loop, motion, keep_running, loop_attr, motion_attr):
    for prelude, body in _blocks(css):
        if prelude.startswith('@'):
            low = prelude.lower()
            if low.startswith('@media') and 'prefers-reduced-motion' in low and 'reduce' in low:
                for sel, decls in _blocks(body):
                    if not sel.startswith('@'):
                        motion.append(_prefix(sel, motion_attr) + '{' + decls + '}')
            elif low.startswith('@media') or low.startswith('@supports'):
                inner = []
                _walk(body, names, inner, motion, keep_running, loop_attr, motion_attr)
                if inner:
                    loop.append(prelude + '{' + ''.join(inner) + '}')
            continue
        if 'animation' in body and 'infinite' in body:
            twin = _loop_twin(prelude, body, names, keep_running, loop_attr)
            if twin:
                loop.append(twin)


def gates(css, *, prefix='kit', functional=('kit-spin', 'kit-skel')):
    """Return (loop_css, motion_css) for the given stripped CSS."""
    loop, motion = [], []
    _walk(css, _keyframes(css), loop, motion, set(functional),
          f'html[data-{prefix}-fx-loop="0"]', f'html[data-{prefix}-fx-motion="0"]')
    return ''.join(loop), ''.join(motion)
