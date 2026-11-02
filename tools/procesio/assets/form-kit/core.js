// =====================================================================================
//  PROCESIO form kit, CORE. The spine of a form runtime: helpers, a network monitor that
//  follows the form's process calls, toasts, the clipboard, the CSS scope fix, and a reader
//  for "the latest run of a process". Pasted by your build INSIDE the runtime function, at
//  the /*@@KIT@@*/ marker of runtime.template.js, after W, D, HTML and CRITICAL_CSS exist and
//  before schedule() is defined. FORM-DEV-GUIDE/10-REDESIGN-METHOD.md says why each part is
//  here; 06 §3c documents the wire this reads.
// =====================================================================================
  /* ---------------------------------------------------------------- helpers */
  function q(s, r) { return (r || D).querySelector(s); }
  function all(s, r) { return Array.prototype.slice.call((r || D).querySelectorAll(s)); }
  function now() { return W.performance && W.performance.now ? W.performance.now() : Date.now(); }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function byId(id) { return q('[data-element-id="' + id + '"]'); }
  function make(html) { var t = D.createElement('template'); t.innerHTML = html.trim(); return t.content.firstChild; }
  function setText(el, txt) { if (el && el.textContent !== txt) { el.textContent = txt; } }
  function setAttr(el, k, v) { if (el && el.getAttribute(k) !== v) { el.setAttribute(k, v); } }
  function shown(el) { return !!(el && el.getClientRects().length); }
  function vh() { return W.innerHeight || HTML.clientHeight; }
  function inView(el, frac) {
    if (!el) { return false; }
    var r = el.getBoundingClientRect();
    var visible = Math.min(r.bottom, vh()) - Math.max(r.top, 0);
    return visible > Math.min(r.height, vh()) * (frac || 0.35);
  }
  function fmtBytes(b) {
    if (!b) { return '0 kB'; }
    if (b < 1024 * 1024) { return (b / 1024).toLocaleString('ro-RO', { maximumFractionDigits: 1 }) + ' kB'; }
    return (b / 1048576).toLocaleString('ro-RO', { maximumFractionDigits: 2 }) + ' MB';
  }
  function scroller() { return q('.form-builder-view--content'); }

  /* ================================================================ network monitor
     Wraps the page's XHR and fetch so the loader can follow the real requests. */
  var NET = { list: [] };
  var KEEP_BODY = { publish: 1, launch: 1, result: 1 };   // small JSON answers the runtime reads
  function classify(url) {
    url = String(url || '');
    if (/notifications\.|\/hub\//i.test(url)) { return 'hub'; }
    if (/\/formProcess\/[^?]*\/publish/i.test(url)) { return 'publish'; }
    if (/\/formProcess\/[^?]*\/upload/i.test(url)) { return 'upload'; }
    if (/\/formProcess\/[^?]*\/launch/i.test(url)) { return 'launch'; }
    if (/\/formProcess\/[^?]*\/variables/i.test(url)) { return 'result'; }
    if (/download/i.test(url)) { return 'download'; }
    if (/webapi/i.test(url)) { return 'api'; }
    return 'asset';
  }
  function netAdd(url, method, t0) {
    var r = { url: String(url || ''), method: method || 'GET', kind: classify(url), t0: t0 || now(), t1: 0, loaded: 0, total: 0, up: 0, upTotal: 0 };
    NET.list.push(r);
    if (NET.list.length > 600) { NET.list.shift(); }
    schedule();
    return r;
  }
  function netEnd(r, status) { if (!r.t1) { r.t1 = now(); r.status = status; keepNewestBody(r); schedule(); } }
  // an address asked again (a polled /variables) keeps only its newest answer: the readers take the
  // last one, and the old copies of a large answer would stay in memory for the whole session
  function keepNewestBody(r) {
    if (!r.body) { return; }
    for (var i = NET.list.length - 1; i >= 0; i--) { var x = NET.list[i]; if (x !== r && x.body && x.url === r.url && x.t0 < r.t0) { x.body = ''; } }
  }
  NET.first = function (kind, since) {
    for (var i = 0; i < NET.list.length; i++) { var r = NET.list[i]; if (r.kind === kind && r.t0 >= since) { return r; } }
    return null;
  };
  NET.since = function (since, kinds) {
    return NET.list.filter(function (r) { return r.t0 >= since && (!kinds || kinds.indexOf(r.kind) > -1); });
  };
  (function patchNet() {
    if (W.__formKitNetPatched) { return; }
    W.__formKitNetPatched = true;
    try {
      var XP = W.XMLHttpRequest && W.XMLHttpRequest.prototype;
      if (XP) {
        var open = XP.open, send = XP.send;
        XP.open = function (method, url) { this.__met = { method: method, url: url }; return open.apply(this, arguments); };
        XP.send = function () {
          try {
            var m = this.__met || {};
            var r = netAdd(m.url, m.method);
            if (KEEP_BODY[r.kind] && typeof arguments[0] === 'string') { r.reqBody = arguments[0].slice(0, 4000); }
            var x = this;
            x.addEventListener('progress', function (e) { r.loaded = e.loaded; if (e.lengthComputable) { r.total = e.total; } schedule(); });
            if (x.upload) {
              x.upload.addEventListener('progress', function (e) { r.up = e.loaded; if (e.lengthComputable) { r.upTotal = e.total; } schedule(); });
            }
            x.addEventListener('loadend', function () {
              if (!r.total && r.loaded) { r.total = r.loaded; }
              if (KEEP_BODY[r.kind]) { try { if (!x.responseType || x.responseType === 'text') { r.body = String(x.responseText || '').slice(0, 600000); } else if (x.responseType === 'json') { r.body = JSON.stringify(x.response); } } catch (e2) { /* opaque */ } }
              netEnd(r, x.status);
            });
          } catch (e) { /* never break the platform's request */ }
          return send.apply(this, arguments);
        };
      }
      if (W.fetch) {
        var F = W.fetch;
        W.fetch = function (input, init) {
          var url = typeof input === 'string' ? input : (input && input.url) || '';
          var method = (init && init.method) || (input && input.method) || 'GET';
          var r = netAdd(url, method);
          if (KEEP_BODY[r.kind] && init && typeof init.body === 'string') { r.reqBody = init.body.slice(0, 4000); }
          return F.apply(this, arguments).then(function (res) {
            try {
              var len = +(res.headers && res.headers.get('content-length')) || 0;
              r.total = len;
              if (KEEP_BODY[r.kind] && res.clone) {
                res.clone().text().then(function (t) { r.body = String(t || '').slice(0, 600000); r.loaded = r.loaded || t.length; netEnd(r, res.status); }, function () { netEnd(r, res.status); });
              } else if (len && res.body && res.clone && r.kind !== 'hub') {
                var reader = res.clone().body.getReader();
                var pump = function () {
                  return reader.read().then(function (c) {
                    if (c.done) { netEnd(r, res.status); return; }
                    r.loaded += c.value ? c.value.length : 0; schedule(); return pump();
                  });
                };
                pump().catch(function () { netEnd(r, res.status); });
              } else { netEnd(r, res.status); }
            } catch (e) { netEnd(r, 0); }
            return res;
          }, function (err) { netEnd(r, 0); throw err; });
        };
      }
    } catch (e) { /* leave the page as it was */ }
  })();
  // Requests that finished before this runtime arrived are still in the timing buffer.
  (function backfill() {
    try {
      (W.performance.getEntriesByType('resource') || []).forEach(function (e) {
        if (e.initiatorType !== 'xmlhttprequest' && e.initiatorType !== 'fetch') { return; }
        var r = { url: e.name, method: 'GET', kind: classify(e.name), t0: e.startTime, t1: e.responseEnd || e.startTime, loaded: e.transferSize || 0, total: e.transferSize || 0, up: 0, upTotal: 0 };
        NET.list.push(r);
      });
    } catch (e) { /* no timing buffer */ }
  })();

  /* ================================================================ toasts */
  var toastBox = null;
  function toast(msg, kind, ms) {
    if (!toastBox) { toastBox = make('<div class="kit-ui kit-toasts" role="status" aria-live="polite"></div>'); D.body.appendChild(toastBox); }
    var ico = kind === 'err' ? '!' : kind === 'warn' ? '!' : kind === 'ok' ? '✓' : 'i';
    var t = make('<div class="kit-toast kit-toast--' + (kind || 'info') + '"><span class="kit-toast__ico">' + ico + '</span><span></span></div>');
    t.lastChild.textContent = msg;
    toastBox.appendChild(t);
    W.setTimeout(function () { t.classList.add('is-in'); }, 20);
    W.setTimeout(function () { t.classList.remove('is-in'); W.setTimeout(function () { t.remove(); }, 500); }, ms || 5200);
  }

  function copyText(txt) {
    if (W.navigator.clipboard && W.isSecureContext) { return W.navigator.clipboard.writeText(txt); }
    return new Promise(function (ok, ko) {
      try {
        var ta = D.createElement('textarea'); ta.value = txt; ta.setAttribute('readonly', '');
        ta.style.position = 'fixed'; ta.style.opacity = '0'; D.body.appendChild(ta); ta.select();
        var done = D.execCommand('copy'); ta.remove(); if (done) { ok(); } else { ko(); }
      } catch (e) { ko(e); }
    });
  }

  function propagateScope() {
    if (HTML.hasAttribute('data-form-css-scope')) { return; }
    var host = q('[data-form-css-scope]');
    if (host) { HTML.setAttribute('data-form-css-scope', host.getAttribute('data-form-css-scope')); }
  }
  function ensureCritical() {
    try {
      if (!W.getComputedStyle(HTML).getPropertyValue('--kit-critical') && !D.getElementById('kit-critical-fallback')) {
        var st = D.createElement('style'); st.id = 'kit-critical-fallback'; st.textContent = CRITICAL_CSS; D.head.appendChild(st);
      }
    } catch (e) { /* the scoped sheet still styles the card */ }
  }

  /* ---------------------------------------------------------------- small helpers */
  function parseJson(s) { try { return JSON.parse(s); } catch (e) { return null; } }
  function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }
  function fold(s) { return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase(); }
  function hhmm(ms) { var d = new Date(ms), z = function (n) { return (n < 10 ? '0' : '') + n; }; return z(d.getHours()) + ':' + z(d.getMinutes()); }
  function btnOf(id) { var h = byId(id); return h ? q('button.pds-c-button', h) : null; }

  /* ---------------------------------------------------------------- network: runs
     A form process call is POST .../{processId}/publish (no instance id), then
     POST .../{instanceId}/launch with {"flowTemplateId": processId} in the body, then (async)
     GET .../{processId}/{instanceId}/variables until status 50 / 40. */
  var LAUNCH_ID = /\/formProcess\/[^/]+\/([0-9a-f-]{36})\/launch/i;
  function launchesOf(key, since) {
    return NET.list.filter(function (r) {
      return r.kind === 'launch' && r.t0 >= since && String(r.reqBody || '').toLowerCase().indexOf(key) > -1;
    });
  }
  // the latest run of a process started after `since`: {pub, inst, la, res, failed, done, sync}
  function runOf(pid, since) {
    var key = pid.toLowerCase(), pub = null, la = null, res = null, inst = '';
    for (var i = NET.list.length - 1; i >= 0; i--) {
      var r = NET.list[i];
      if (r.kind === 'publish' && r.t0 >= since && r.url.toLowerCase().indexOf(key) > -1) { pub = r; break; }
    }
    var las = launchesOf(key, since);
    if (las.length) { la = las[las.length - 1]; }
    if (!la) {
      for (var j = NET.list.length - 1; j >= 0; j--) {
        var v = NET.list[j], m = new RegExp(key + '/([0-9a-f-]{36})/variables', 'i').exec(v.url);
        if (v.kind === 'result' && v.t0 >= since && m) { inst = m[1]; break; }
      }
      if (inst) { NET.list.forEach(function (x) { if (x.kind === 'launch' && x.url.toLowerCase().indexOf(inst.toLowerCase()) > -1) { la = x; } }); }
    }
    if (!pub && !la && !inst) { return null; }
    if (la && !inst) { var lm = LAUNCH_ID.exec(la.url); inst = lm ? lm[1] : ''; }
    if (inst) {
      var ik = inst.toLowerCase();
      NET.list.forEach(function (x) { if (x.kind === 'result' && x.url.toLowerCase().indexOf(ik) > -1) { res = x; } });
    }
    var bad = function (x) { return x && x.t1 && (x.status === 0 || x.status >= 400); };
    var failed = !!(bad(pub) || bad(la) || bad(res));
    var sync = !!(la && /runSynchronous=true/i.test(la.url));
    var done = !!((sync && la.t1) || (!sync && res && res.t1 && /"status"\s*:\s*(50|40)\b/.test(res.body || '')) || failed);
    return { pub: pub, inst: inst, la: la, res: res, failed: failed, done: done, sync: sync };
  }
