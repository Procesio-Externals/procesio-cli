// =====================================================================================
//  PROCESIO form kit, a runtime to start from. Copy it next to your form's sources, rename
//  FORM_RUNTIME and the __formRuntime guard, fill CFG and EL, and write your UI in refresh().
//
//  The model (FORM-DEV-GUIDE/02): this file is replayed in a throwaway sandbox iframe and
//  only INSTALLS the runtime once into the real page. The runtime keeps no state on renderer
//  nodes; refresh() recomputes everything from the DOM and the network log, driven by a
//  MutationObserver and a 250 ms tick. Behaviour is layered ON TOP of the platform: processes
//  still run through the form's own RUN_PROCESS events, a hidden button the runtime clicks
//  when it needs one. Every wait has a hard ceiling.
// =====================================================================================

function FORM_RUNTIME() {
  'use strict';
  if (window.__formRuntime) { return; }
  window.__formRuntime = '1.0.0';

  var W = window;
  var D = document;
  var HTML = D.documentElement;
  if (/\/admin\//.test(W.location.pathname)) { return; }   // the designer preview

  var CFG = {
    ONLOAD: '<process id of the form-load check>',
    CHECK_CEILING: 30000,      // no section after this long: say so instead of a skeleton
    FX_KEY: '<site>-fx',       // same key on every form of the site = one choice for all
    FX_TEXT: null              // effects.js TXT overrides, for the form's language
  };
  var EL = {
    main: '<element id of the section only a signed-in user gets>'
  };

  // the same rules as critical.css, for the rare load where the @import did not apply
  var CRITICAL_CSS = '.pds-c-topbar,.skip-link{display:none!important}html,body{background:#0f2433!important}';

  /*@@KIT@@*/

  var S = { phase: 'loading', phaseAt: now(), started: now() };

  /* a place for the effects button; a real form mounts its branded header here */
  var BAR = null;
  function mountBar() {
    if (BAR || !D.body) { return; }
    BAR = make('<div class="kit-ui kit-bar"></div>');
    D.body.appendChild(BAR);
    FX.attach(BAR);
  }

  function detectPhase(T) {
    if (byId(EL.main)) { return 'ready'; }
    var ol = runOf(CFG.ONLOAD, -1);
    if (ol && ol.failed) { return 'blocked'; }
    if (ol && ol.done && T - ((ol.res || ol.la || ol.pub).t1 || T) > 2500) { return 'blocked'; }
    return T - S.started > CFG.CHECK_CEILING ? 'blocked' : 'loading';
  }

  /* total and idempotent: safe to run on every mutation and on the tick */
  var pending = false;
  function schedule() { if (pending) { return; } pending = true; W.setTimeout(refresh, 30); }
  function refresh() {
    pending = false;
    var T = now();
    propagateScope();
    mountBar();
    var phase = detectPhase(T);
    if (phase !== S.phase) { S.phase = phase; S.phaseAt = T; }
    setAttr(HTML, 'data-view', phase);
  }

  var mo = new MutationObserver(function () { schedule(); });
  (function start() {
    var host = D.getElementById('app') || D.body;
    if (!host) { return W.setTimeout(start, 120); }
    mo.observe(host, { childList: true, subtree: true, characterData: true });
    ensureCritical();
    schedule();
  })();
  W.setInterval(schedule, 250);
  // the scope first: UI mounted on <body> before <html> carries it is unstyled and in the flow
  if (D.body) { propagateScope(); mountBar(); }

  // counts and flags only: never log what a visitor typed
  W.FormKit = { toast: toast, state: function () { return { phase: S.phase, requests: NET.list.length, fx: FX.parts() }; } };
}

/* -- installer: put the runtime in the parent page, exactly once -------------------- */
(function () {
  try {
    var W = window.parent && window.parent !== window ? window.parent : window;
    var D = W.document;
    if (!D || !D.body || D.getElementById('form-kit-runtime')) { return; }
    var s = D.createElement('script');
    s.id = 'form-kit-runtime';
    s.textContent = '(' + FORM_RUNTIME.toString() + ')();';
    D.body.appendChild(s);
  } catch (e) {
    // Cross-origin parent or no parent: nothing to install; the CSS still stands.
  }
})();
