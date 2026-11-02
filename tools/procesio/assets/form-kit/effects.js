// =====================================================================================
//  PROCESIO form kit, EFFECTS. How much motion this device can afford, and the switch that
//  lets the viewer overrule it. Pasted right after core.js. Sets on <html>: data-kit-fx =
//  full | lite | min | custom, and data-kit-fx-<part> = 1 | 0 for bg, blur, loop, motion.
//  effects.css draws the button and panel; effects_gate.py generates the CSS that stops the
//  loops; your own background listens with FX.listen(fn), asks FX.on('bg'), and calls
//  FX.frame(ts) from its animation loop so the frame monitor has something to measure.
//  With no animation loop the choice rests on the hints alone. FORM-DEV-GUIDE/05 §7.
// =====================================================================================
  /* ================================================================ effects (FX)
     Four parts, each on or off:
       bg      the animated canvas background (off: one still frame of it)
       blur    backdrop blur under the header, the loader and the veils (off: solid tints)
       loop    decorative animations that repeat (pulses, sheens, the logo wave)
       motion  entrance motion and transitions (off: the form's reduced-motion rules)
     Tiers: full = all on; lite = motion only; min = all off.
     Auto picks the tier BEFORE the background mounts, from, in order: prefers-reduced-motion
     (min), Save-Data (lite), the last measurement on this browser, hardware hints (cores,
     memory, a GPU that would draw in software), then frame times while the background runs.
     During a visit auto only steps down, so the page never flips back and forth. A manual
     choice wins over all of it and is shared by every form on this site (localStorage,
     best effort: without storage it lasts the page). */
  var FX = (function () {
    var KEY = (typeof CFG !== 'undefined' && CFG.FX_KEY) || 'form-kit-fx';
    var PARTS = ['bg', 'blur', 'loop', 'motion'];
    var TIER = { full: { bg: 1, blur: 1, loop: 1, motion: 1 }, lite: { bg: 0, blur: 0, loop: 0, motion: 1 }, min: { bg: 0, blur: 0, loop: 0, motion: 0 } };
    var MEASURE_TTL = 7 * 864e5;   // a measurement is trusted for a week, then taken again
    var TXT = {
      button: 'Display and animation', title: 'Display', close: 'Close',
      auto: ['Automatic', 'Effects follow how fast this device is.'],
      all: ['Animation', 'Turn every effect on or off.'],
      parts: {
        bg: ['Animated background', 'The moving layer behind the form.'],
        blur: ['Glass effect', 'The blurred backdrop under the header and dialogs.'],
        loop: ['Repeating animation', 'Pulses and sheens that keep running.'],
        motion: ['Transitions', 'Elements appear and move smoothly.']
      },
      stepDown: 'Effects were reduced so the form stays smooth. Turn them back on from the button at the top right.',
      why: {
        reduced: 'Your system asks for less motion, so animation is off.',
        savedata: 'Data saver is on, so only light effects remain.',
        slow: 'Effects were slowing the page on this device, so they were reduced.',
        hardware: 'This device has modest resources, so only light effects remain.',
        gpu: 'The browser draws without the graphics card, so only light effects remain.',
        fast: 'This device keeps up with every effect.',
        manual: 'Your own settings. They apply to every form on this site in this browser.'
      }
    };
    // CFG.FX_TEXT replaces any of these (the language of the form)
    if (typeof CFG !== 'undefined' && CFG.FX_TEXT) { Object.keys(CFG.FX_TEXT).forEach(function (k) { TXT[k] = CFG.FX_TEXT[k]; }); }
    var st = { mode: 'auto', tier: 'full', why: 'fast', manual: null, gpu: '', listeners: [], mon: null };

    function mq(s) { try { return !!(W.matchMedia && W.matchMedia(s).matches); } catch (e) { return false; } }
    function load() { try { var v = JSON.parse(W.localStorage.getItem(KEY) || 'null'); return v && v.v === 1 ? v : null; } catch (e) { return null; } }
    function save(patch) {
      try {
        var v = load() || { v: 1 };
        for (var k in patch) { if (patch[k] === null) { delete v[k]; } else { v[k] = patch[k]; } }
        W.localStorage.setItem(KEY, JSON.stringify(v));
      } catch (e) { /* private mode or blocked storage: the choice lasts this page */ }
    }

    // A WebGL context that refuses a "major performance caveat" means this browser would draw
    // in software, so every canvas frame and every blur costs CPU. Asked once per browser.
    function gpu() {
      var saved = load();
      if (saved && saved.gpu) { return saved.gpu; }
      var res = 'unknown';
      try {
        var gl = D.createElement('canvas').getContext('webgl', { failIfMajorPerformanceCaveat: true });
        if (gl) {
          res = 'hw';
        } else {
          gl = D.createElement('canvas').getContext('webgl');
          res = gl ? 'sw' : 'none';
        }
        var lose = gl && gl.getExtension('WEBGL_lose_context');
        if (lose) { lose.loseContext(); }
      } catch (e) { res = 'unknown'; }
      save({ gpu: res });
      return res;
    }

    function decide() {
      if (mq('(prefers-reduced-motion: reduce)')) { return ['min', 'reduced']; }
      var n = W.navigator || {}, c = n.connection || {};
      if (c.saveData) { return ['lite', 'savedata']; }
      var saved = load();
      if (saved && saved.measured && Date.now() - saved.measured.at < MEASURE_TTL) {
        return saved.measured.tier === 'full' ? ['full', 'fast'] : ['lite', 'slow'];
      }
      var cores = n.hardwareConcurrency || 0, mem = n.deviceMemory || 0;
      if ((cores && cores <= 2) || (mem && mem <= 2) || (cores && cores <= 4 && mem && mem <= 4)) { return ['lite', 'hardware']; }
      st.gpu = gpu();
      if (st.gpu === 'sw' || st.gpu === 'none') { return ['lite', 'gpu']; }
      return ['full', 'fast'];
    }

    function parts() { return st.mode === 'manual' && st.manual ? st.manual : TIER[st.tier]; }
    function on(p) { return !!parts()[p]; }
    function apply() {
      var P = parts();
      PARTS.forEach(function (p) { setAttr(HTML, 'data-kit-fx-' + p, P[p] ? '1' : '0'); });
      setAttr(HTML, 'data-kit-fx', st.mode === 'manual' ? 'custom' : st.tier);
      st.listeners.forEach(function (f) { try { f(P); } catch (e) { /* one listener never blocks the others */ } });
      paintPanel();
    }
    function listen(f) { st.listeners.push(f); }

    /* -- frame monitor: fed by the background's own animation frames (no loop of its own).
       The first window starts 2 s after the background does (the boot has spikes of its own)
       and lasts 3 s; its verdict is remembered for a week. Afterwards every 4 s window is a
       watchdog: two slow ones in a row step down too. Slow = under ~40 fps on the median, or
       more than a third of the frames past 34 ms. */
    function frame(ts) {
      if (st.mode !== 'auto' || st.tier !== 'full') { st.mon = null; return; }
      var m = st.mon || (st.mon = { from: ts + 2000, gaps: [], last: 0, first: true, strikes: 0 });
      if (ts < m.from) { m.last = ts; return; }
      var gap = m.last ? ts - m.last : 0;
      m.last = ts;
      if (gap > 0 && gap < 1000) { m.gaps.push(gap); }   // a hidden tab pauses frames: that pause is not jank
      if (ts - m.from < (m.first ? 3000 : 4000)) { return; }
      var g = m.gaps.sort(function (a, b) { return a - b; }), n = g.length;
      var slow = n >= 20 && (g[n >> 1] > 25 || g.filter(function (x) { return x > 34; }).length / n > 0.34);
      var verdict = n >= 20;
      m.from = ts; m.gaps = [];
      if (m.first) {
        m.first = false;
        if (verdict) { save({ measured: { tier: slow ? 'lite' : 'full', at: Date.now() } }); }
        if (slow) { stepDown(); }
        return;
      }
      m.strikes = slow ? m.strikes + 1 : 0;
      if (m.strikes >= 2) { save({ measured: { tier: 'lite', at: Date.now() } }); stepDown(); }
    }
    function stepDown() {
      st.tier = 'lite'; st.why = 'slow'; st.mon = null;
      apply();
      toast(TXT.stepDown, 'info', 7000);
    }

    function setManual(P) {
      st.mode = 'manual'; st.manual = P;
      save({ mode: 'manual', parts: P });
      apply();
    }
    function setAuto() {
      st.mode = 'auto'; st.manual = null;
      save({ mode: null, parts: null });
      var d = decide(); st.tier = d[0]; st.why = d[1];
      apply();
    }

    /* -- the header button and its panel ------------------------------------------------ */
    var btn = null, panel = null;
    var GEAR = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/></svg>';
    var ROWS = PARTS.map(function (p) { return [p, TXT.parts[p][0], TXT.parts[p][1]]; });
    function sw(key, title, sub, cls) {
      return '<label class="kit-fx__row' + (cls ? ' ' + cls : '') + '"><span class="kit-fx__txt"><b>' + title + '</b><small>' + sub + '</small></span>' +
        '<input type="checkbox" role="switch" data-fx="' + key + '"><i class="kit-fx__sw" aria-hidden="true"></i></label>';
    }
    function attach(hdr) {
      if (!hdr || btn) { return; }
      btn = make('<button type="button" class="kit-fx-btn" aria-haspopup="dialog" aria-expanded="false" aria-controls="kit-fx-panel" title="' + TXT.button + '" aria-label="' + TXT.button + '">' + GEAR + '</button>');
      var side = q('.kit-hdr__side', hdr) || q('.kit-hdr__in', hdr) || hdr;
      side.appendChild(btn);
      panel = make(
        '<div class="kit-ui kit-fx" id="kit-fx-panel" role="dialog" aria-label="' + TXT.button + '" hidden>' +
          '<div class="kit-fx__head"><b>' + TXT.title + '</b><button type="button" class="kit-fx__x" data-fx-close aria-label="' + TXT.close + '">×</button></div>' +
          sw('auto', TXT.auto[0], TXT.auto[1], 'kit-fx__row--auto') +
          '<div class="kit-fx__sep"></div>' +
          sw('all', TXT.all[0], TXT.all[1], 'kit-fx__row--all') +
          '<div class="kit-fx__sub">' + ROWS.map(function (r) { return sw(r[0], r[1], r[2]); }).join('') + '</div>' +
          '<p class="kit-fx__note" aria-live="polite"></p>' +
        '</div>');
      D.body.appendChild(panel);
      btn.addEventListener('click', function (e) { e.preventDefault(); e.stopPropagation(); toggle(); });
      panel.addEventListener('change', onSwitch);
      panel.addEventListener('click', function (e) { if (e.target.closest('[data-fx-close]')) { close(true); } });
      D.addEventListener('pointerdown', function (e) {
        if (panel.hidden || panel.contains(e.target) || btn.contains(e.target)) { return; }
        close(false);
      }, true);
      D.addEventListener('keydown', function (e) { if (e.key === 'Escape' && !panel.hidden) { close(true); } }, true);
      W.addEventListener('resize', function () { close(false); }, { passive: true });
      paintPanel();
    }
    function toggle() { if (panel.hidden) { open(); } else { close(true); } }
    function open() {
      var r = btn.getBoundingClientRect();
      panel.style.top = Math.round(r.bottom + 10) + 'px';
      panel.style.right = Math.max(12, Math.round(W.innerWidth - r.right - 6)) + 'px';
      panel.hidden = false;
      btn.setAttribute('aria-expanded', 'true');
      paintPanel();
      W.requestAnimationFrame(function () { panel.classList.add('is-in'); var f = q('input', panel); if (f) { f.focus({ preventScroll: true }); } });
    }
    function close(focusBack) {
      if (!panel || panel.hidden) { return; }
      panel.classList.remove('is-in');
      panel.hidden = true;
      btn.setAttribute('aria-expanded', 'false');
      if (focusBack) { btn.focus({ preventScroll: true }); }
    }
    function onSwitch(e) {
      var k = e.target.getAttribute('data-fx');
      if (!k) { return; }
      if (k === 'auto') { if (e.target.checked) { setAuto(); } else { setManual(copy(parts())); } return; }
      var P = copy(parts());
      if (k === 'all') { PARTS.forEach(function (p) { P[p] = e.target.checked ? 1 : 0; }); } else { P[k] = e.target.checked ? 1 : 0; }
      setManual(P);
    }
    function copy(P) { var o = {}; PARTS.forEach(function (p) { o[p] = P[p] ? 1 : 0; }); return o; }
    function paintPanel() {
      if (!panel) { return; }
      var P = parts(), any = PARTS.some(function (p) { return P[p]; });
      var set = function (k, v) { var i = q('input[data-fx="' + k + '"]', panel); if (i && i.checked !== !!v) { i.checked = !!v; } };
      set('auto', st.mode === 'auto'); set('all', any);
      PARTS.forEach(function (p) { set(p, P[p]); });
      panel.classList.toggle('is-off', !any);
      setText(q('.kit-fx__note', panel), st.mode === 'manual' ? TXT.why.manual : TXT.why[st.why] || '');
      if (btn) { btn.classList.toggle('is-reduced', st.mode === 'auto' ? st.tier !== 'full' : !P.bg); }
    }

    /* -- boot: decide before anything paints -------------------------------------------- */
    (function init() {
      var saved = load();
      if (saved && saved.mode === 'manual' && saved.parts) { st.mode = 'manual'; st.manual = copy(saved.parts); }
      var d = decide(); st.tier = d[0]; st.why = d[1];
      apply();
      try {
        var m = W.matchMedia('(prefers-reduced-motion: reduce)');
        var follow = function () { if (st.mode === 'auto') { setAuto(); } };
        if (m.addEventListener) { m.addEventListener('change', follow); } else if (m.addListener) { m.addListener(follow); }
      } catch (e) { /* old engine: the choice made at load stands */ }
    })();

    W.FormKitFx = {
      state: function () { return { mode: st.mode, tier: st.tier, why: st.why, parts: copy(parts()), gpu: st.gpu || (load() || {}).gpu || '', saved: load() }; },
      set: function (x) { if (x === 'auto') { setAuto(); } else if (TIER[x]) { setManual(copy(TIER[x])); } else if (x && typeof x === 'object') { setManual(copy(x)); } return this.state(); }
    };
    return { on: on, listen: listen, frame: frame, attach: attach, parts: parts };
  })();
