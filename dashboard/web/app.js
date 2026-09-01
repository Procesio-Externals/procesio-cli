// Core SPA: load inventory, render capability cards, drive live validation.
// Setup/test interactions live in actions.js (attached to window.Actions).
(function () {
  const state = { inv: null, tab: "tools", filter: "", onlyNeedsSetup: false, val: {} };
  const $ = (s, r = document) => r.querySelector(s);
  const content = $("#content");

  // ---- tiny DOM builder --------------------------------------------------
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) {
      if (k === "class") n.className = v;
      else if (k === "html") n.innerHTML = v;
      else if (k.startsWith("data-")) n.setAttribute(k, v);
      else if (k === "onclick") n.addEventListener("click", v);
      else if (v !== null && v !== undefined) n.setAttribute(k, v);
    }
    for (const kid of kids.flat()) {
      if (kid == null || kid === false) continue;
      n.appendChild(typeof kid === "string" ? document.createTextNode(kid) : kid);
    }
    return n;
  }

  function toast(msg, kind) {
    const t = el("div", { class: "toast " + (kind || "") }, msg);
    $("#toasts").appendChild(t);
    setTimeout(() => t.remove(), 5000);
  }

  function valKey(item) { return item.kind + ":" + item.name; }

  // ---- setup action bridge ----------------------------------------------
  function act(name, data) {
    if (window.Actions && typeof window.Actions[name] === "function") {
      window.Actions[name](data, { state, refresh, rerender, toast, el, validateOne });
    } else {
      toast("action unavailable: " + name, "bad");
    }
  }

  // Shown when the API returns 401 - the tab has no valid token (opened the base
  // URL, a new tab, or the server restarted with a new token). Let the user paste it.
  function renderTokenGate() {
    const inp = el("input", { type: "text", placeholder: "paste the access token from your terminal" });
    const connect = () => {
      const v = inp.value.trim();
      if (!v) { toast("paste the token first", "bad"); return; }
      API.setToken(v); refresh();
    };
    const btn = el("button", { class: "btn", onclick: connect }, "Connect");
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") connect(); });
    content.innerHTML = "";
    content.appendChild(el("div", { class: "banner" },
      el("h3", null, "Enter your access token"),
      el("p", { class: "sub" }, "This dashboard is protected by a one-time token. Open the URL that "
        + "'python dashboard/serve.py' printed in your terminal, or copy just the token and paste it here:"),
      el("div", { class: "rowflex" }, inp, btn)));
    setTimeout(() => inp.focus(), 30);
  }

  // ---- data --------------------------------------------------------------
  async function refresh() {
    content.innerHTML = '<div class="loading">Loading inventory...</div>';
    try {
      state.inv = await API.get("/api/inventory");
    } catch (e) {
      content.innerHTML = "";
      if (e.status === 401) return renderTokenGate();
      content.appendChild(el("div", { class: "banner" },
        el("h3", null, "Cannot reach the dashboard API"),
        el("p", { class: "sub" }, String(e.message || e))));
      return;
    }
    renderSummary();
    renderBanner();
    rerender();
    validateAll();
  }

  // ---- summary + fresh-start banner -------------------------------------
  function renderSummary() {
    const s = state.inv.summary;
    const u = state.inv.userdata || {};
    $("#basePath").textContent = (u.base || "") + (u.overridden ? "  (AAT_USERDATA_DIR)" : "");
    const box = $("#summary"); box.innerHTML = "";
    const tile = (n, l, sub, cls) => el("div", { class: "stat" },
      el("div", { class: "n " + (cls || "") }, String(n)),
      el("div", { class: "l" }, l),
      sub ? el("div", { class: "sub2 meta" }, sub) : null);
    box.appendChild(tile(s.tools.ready + "/" + s.tools.total, "Tools ready to use",
      s.tools.needs_setup + " need setup" + (s.tools.errored ? ", " + s.tools.errored + " errored" : "")));
    box.appendChild(tile(s.agents.ready + "/" + s.agents.total, "Agents ready to use",
      s.agents.needs_setup + " need setup"));
    box.appendChild(tile(s.skills.total, "Skills", "no setup needed"));
    box.appendChild(tile(s.llm_ready ? "yes" : "no", "AI model connected",
      s.llm_ready ? "tests + copilot enabled" : "connect one to enable tests",
      s.llm_ready ? "" : "warn"));
    const st = state.inv.store || {};
    box.appendChild(tile(st.records != null ? st.records : "-", "Things it remembers",
      (st.runs != null ? st.runs + " past runs" : "")));
  }

  function renderBanner() {
    const b = $("#freshBanner");
    if (!state.inv.fresh_start) { b.classList.add("hidden"); return; }
    b.classList.remove("hidden"); b.innerHTML = "";
    const ob = state.inv.onboarding || {};
    b.appendChild(el("h3", null, "Fresh install - let's get you set up"));
    b.appendChild(el("p", { class: "sub" }, ob.message || ""));
    const ol = el("ol");
    (ob.steps || []).forEach(s => ol.appendChild(el("li", null, s)));
    b.appendChild(ol);
    b.appendChild(el("button", { class: "btn", onclick: () => act("bootstrap", { withTemplates: true }) },
      "Initialize (copy config templates)"));
  }

  // ---- tab render --------------------------------------------------------
  function matches(item) {
    if (state.onlyNeedsSetup && !item.needs_setup && !item.error) return false;
    if (!state.filter) return true;
    const f = state.filter.toLowerCase();
    return (item.name || "").toLowerCase().includes(f) ||
      (item.description || "").toLowerCase().includes(f);
  }

  function rerender() {
    content.innerHTML = "";
    const t = state.tab;
    if (t === "providers") return renderProviders();
    if (t === "context") return renderContext();
    const list = (state.inv[t] || []).filter(matches);
    if (!list.length) {
      const msg = state.onlyNeedsSetup ? "Nothing needs setup here - all good." : "Nothing matches.";
      content.appendChild(el("div", { class: "loading" }, msg));
      return;
    }
    const grid = el("div", { class: "grid" });
    const render = t === "tools" ? renderTool : t === "agents" ? renderAgent : renderSkill;
    list.forEach(i => grid.appendChild(render(i)));
    content.appendChild(grid);
  }

  function readinessDot(item) {
    if (item.error) return el("span", { class: "dot red", title: item.error });
    if (item.needs_setup) return el("span", { class: "dot amber", title: "needs setup" });
    return el("span", { class: "dot green", title: "ready to use" });
  }

  // The one plain-language status a newcomer reads first.
  function setupLabel(item) {
    if (item.error) return { t: "Not working (failed to load)", c: "bad" };
    if (item.kind === "agent" && item.needs_setup && !(item.missing_secrets || []).length)
      return { t: "A tool it uses needs setup", c: "warn" };
    if (item.needs_setup) {
      if (item.web_session_status && !item.web_session_status.present)
        return { t: "Needs a browser login", c: "warn" };
      if ((item.actions || []).some(a => a.name === "auth-login"))
        return { t: "Needs Google/LinkedIn sign-in", c: "warn" };
      return { t: "Needs a credential", c: "warn" };
    }
    return { t: "Ready to use", c: "ok" };
  }
  function statusPill(item) {
    const s = setupLabel(item);
    return el("div", { class: "setup " + s.c }, s.t);
  }

  function head(item) {
    return el("div", { class: "card-head" },
      el("div", { class: "card-title" }, readinessDot(item),
        el("span", { class: "name" }, item.name)),
      el("span", { class: "badge" }, item.kind));
  }
  function desc(item) {
    return el("p", { class: "card-desc clamp", title: item.description || "" },
      item.description || "");
  }

  function valSlot(item) {
    const v = state.val[valKey(item)];
    const wrap = el("div", { class: "row", "data-valslot": valKey(item) });
    wrap.appendChild(el("div", { class: "k" }, "live check"));
    wrap.appendChild(valPill(v, item));
    return wrap;
  }
  function valPill(v, item) {
    const rc = el("div", { class: "v" });
    if (!v) rc.appendChild(el("span", { class: "pill unknown" }, "not checked"));
    else if (v.status === "checking") rc.appendChild(el("span", { class: "pill warn" },
      el("span", { class: "dot amber pulse" }), " checking..."));
    else if (v.status === "connected") rc.appendChild(el("span", { class: "pill ok" }, "connected"));
    else if (v.status === "invalid") rc.appendChild(el("span", { class: "pill bad", title: v.detail || "" }, "not working"));
    else rc.appendChild(el("span", { class: "pill unknown", title: v.detail || "" }, "-"));
    if (item.probe) rc.appendChild(el("button",
      { class: "btn ghost sm", onclick: () => validateOne(item) }, "re-check"));
    if (v && v.status === "invalid")
      rc.appendChild(el("button", { class: "btn ghost sm", title: "Ask the AI why this is failing",
        onclick: () => act("explainProbe", { kind: item.kind, name: item.name }) }, "Explain"));
    return rc;
  }

  function secretRows(item) {
    if (!item.secrets_status || !item.secrets_status.length) return null;
    const rows = el("div", { class: "rows" });
    item.secrets_status.forEach(s => {
      const present = s.present;
      rows.appendChild(el("div", { class: "row" },
        el("div", { class: "k", title: s.description }, s.name),
        el("div", { class: "v" },
          el("span", { class: "pill " + (present ? "ok" : "bad") }, present ? "present" : "missing"),
          el("button", { class: "btn ghost sm", onclick: () => act("setCred", { tool: item.name, secret: s.name, hasNs: s.name.includes(":") }) },
            present ? "update" : "Add"),
          present ? el("button", { class: "btn danger sm", title: "Delete this credential from Windows Credential Manager", onclick: () => act("delCred", { tool: item.name, secret: s.name }) }, "Delete") : null)));
    });
    return rows;
  }

  // A tool that logs in via a saved browser session (no API key).
  function webSessionRow(item) {
    const ws = item.web_session_status;
    if (!ws) return null;
    return el("div", { class: "rows" }, el("div", { class: "row" },
      el("div", { class: "k", title: "browser login captured via the web tool" },
        "web login: " + ws.name),
      el("div", { class: "v" },
        el("span", { class: "pill " + (ws.present ? "ok" : "bad") },
          ws.present ? "connected" : "not connected"),
        el("button", { class: "btn ghost sm", onclick: () => act("webConnect", ws) },
          ws.present ? "reconnect" : "Connect"))));
  }

  function renderTool(item) {
    if (item.error) return el("div", { class: "card err" }, head(item),
      statusPill(item), el("p", { class: "errmsg" }, item.error));
    const hasOauth = (item.actions || []).some(a => a.name === "auth-login");
    const isGoogle = (item.secrets || []).some(s => (s.name || "").startsWith("google:"));
    const kids = [head(item), statusPill(item), desc(item),
      secretRows(item), webSessionRow(item)];
    if (item.probe) kids.push(valSlot(item));  // only show a live check when there is one
    const foot = [el("span", { class: "meta" }, (item.actions ? item.actions.length + " actions" : "flat tool"))];
    if (hasOauth && isGoogle) foot.push(el("button", { class: "btn", title: "Manage the Google accounts (profiles) this login can use", onclick: () => act("googleAccounts", { tool: item.name }) }, "Manage accounts"));
    else if (hasOauth) foot.push(el("button", { class: "btn", title: "Sign in (OAuth)", onclick: () => act("oauthLogin", { tool: item.name }) }, "Connect"));
    if (item.name === "procesio") foot.push(el("button", { class: "btn", title: "Manage PROCESIO environments (switch/add) and credentials per environment", onclick: () => act("procesioEnvironments", { tool: item.name }) }, "Environments"));
    foot.push(el("button", { class: "btn ghost sm", onclick: () => act("details", { kind: "tool", name: item.name }) }, "Details"));
    kids.push(el("div", { class: "card-foot" }, ...foot));
    return el("div", { class: "card" }, ...kids);
  }

  function renderAgent(item) {
    if (item.error) return el("div", { class: "card err" }, head(item),
      statusPill(item), el("p", { class: "errmsg" }, item.error));
    const kids = [head(item), statusPill(item), desc(item), secretRows(item)];
    if (item.probe) kids.push(valSlot(item));
    const ts = item.tool_status || {};
    if (Object.keys(ts).length) {
      const rows = el("div", { class: "rows" });
      Object.entries(ts).forEach(([tn, st]) => rows.appendChild(el("div", { class: "row" },
        el("div", { class: "k" }, "uses: " + tn),
        el("div", { class: "v" }, el("span", { class: "pill " + (st.ready ? "ok" : st.present ? "bad" : "warn") },
          st.ready ? "ready" : st.present ? "needs setup" : "not found")))));
      kids.push(el("div", { class: "section-title" }, el("h2", null, "tools it uses"), el("span", { class: "line" })));
      kids.push(rows);
    }
    kids.push(el("div", { class: "card-foot" },
      el("button", { class: "btn ghost sm", onclick: () => act("details", { kind: "agent", name: item.name }) }, "Details")));
    return el("div", { class: "card" }, ...kids);
  }

  function renderSkill(item) {
    return el("div", { class: "card" }, head(item),
      el("div", { class: "setup ok" }, "Always available"),
      desc(item),
      item.warning ? el("p", { class: "errmsg" }, item.warning) : null);
  }

  function renderProviders() {
    const p = state.inv.providers || {};
    const wrap = el("div");
    wrap.appendChild(el("p", { class: "card-desc" },
      "Connect an AI model here (OpenAI, Azure, a local model, or Anthropic). It powers the Test buttons, the context summary, and the copilot. This is the only place the dashboard itself uses AI - and it works with any provider."));
    wrap.appendChild(el("div", { class: "card-foot" },
      el("button", { class: "btn", onclick: () => act("editConfig", { component: "llm", name: "providers" }) },
        "Edit providers"),
      el("span", { class: "meta" }, "default: " + (p.default || "none"))));
    if (p.error) wrap.appendChild(el("div", { class: "banner" },
      el("h3", null, "No AI model connected yet"),
      el("p", { class: "sub" }, "Edit providers, then add a key below to enable the Test buttons, context summary, and copilot.")));
    const grid = el("div", { class: "grid" });
    (p.providers || []).forEach(pr => grid.appendChild(el("div", { class: "card" },
      el("div", { class: "card-head" },
        el("div", { class: "card-title" },
          el("span", { class: "dot " + (pr.key_present ? "green" : "amber") }),
          el("span", { class: "name" }, pr.name)),
        pr.is_default ? el("span", { class: "badge" }, "default") : null),
      el("div", { class: "setup " + (pr.key_present ? "ok" : "warn") },
        pr.key_present ? "Ready" : "Needs an API key"),
      el("p", { class: "card-desc" }, (pr.adapter || "") + " - " + (pr.model || "")),
      el("div", { class: "rows" }, el("div", { class: "row" },
        el("div", { class: "k" }, "api key"),
        el("div", { class: "v" },
          el("span", { class: "pill " + (pr.key_present ? "ok" : "bad") }, pr.key_present ? "present" : "missing"),
          el("button", { class: "btn ghost sm", onclick: () => act("setCred", { tool: "llm", secret: pr.name }) },
            pr.key_present ? "update" : "Add")))),
      el("div", { class: "card-foot" },
        el("button", { class: "btn ghost sm", onclick: () => act("testProvider", { provider: pr.name }) }, "Test connection")))));
    wrap.appendChild(grid);
    content.appendChild(wrap);
  }

  function renderContext() {
    const st = state.inv.store || {};
    const u = state.inv.userdata || {};
    const wrap = el("div");
    wrap.appendChild(el("p", { class: "card-desc" },
      "This is the memory your assistant builds up over time - facts, preferences, and past work. It lives on this machine only and is safe to wipe."));
    wrap.appendChild(el("div", { class: "card" },
      el("div", { class: "card-title" }, "Memory store"),
      el("p", { class: "card-desc" }, u.base || ""),
      el("div", { class: "rows" },
        row2("things remembered", st.records != null ? st.records : "-"),
        row2("past runs", st.runs != null ? st.runs : "-"),
        row2("runs still open", st.open_runs != null ? st.open_runs : "-"),
        row2("storage created", String(!!(u.scan && u.scan.store_db_exists))),
        row2("config files", u.scan ? u.scan.config_files : "-")),
      el("div", { class: "card-foot" },
        el("button", { class: "btn ghost sm", onclick: () => act("inspectContext", {}) }, "Summarize with AI"))));
    content.appendChild(wrap);
  }
  function row2(k, v) {
    return el("div", { class: "row" }, el("div", { class: "k" }, k),
      el("div", { class: "v" }, el("span", { class: "meta" }, String(v))));
  }

  // ---- live validation ---------------------------------------------------
  function setVal(key, status, detail) {
    state.val[key] = { status, detail };
    const slot = document.querySelector('[data-valslot="' + CSS.escape(key) + '"]');
    if (slot) {
      const item = findItem(key);
      slot.replaceChildren(el("div", { class: "k" }, "live check"), valPill(state.val[key], item));
    }
  }
  function findItem(key) {
    const [kind] = key.split(":");
    const bucket = kind === "tool" ? "tools" : kind === "agent" ? "agents" : "skills";
    return (state.inv[bucket] || []).find(i => valKey(i) === key) || { probe: null };
  }

  function validateAll() {
    if (state.stream) { try { state.stream.close(); } catch (_) {} }
    ["tools", "agents"].forEach(b => (state.inv[b] || []).forEach(i => {
      if (i.probe) setVal(valKey(i), "checking");
    }));
    state.stream = API.stream("/api/validate/all", {
      result: (d) => setVal(d.kind + ":" + d.name, d.status, d.detail),
      done: (_d, es) => es.close(), // stop EventSource auto-reconnect
      error: (d) => toast("validation stream error: " + (d.message || ""), "bad"),
    });
  }

  async function validateOne(item) {
    setVal(valKey(item), "checking");
    try {
      const d = await API.post("/api/validate/one", { kind: item.kind, name: item.name });
      setVal(item.kind + ":" + item.name, d.status, d.detail);
    } catch (e) { setVal(valKey(item), "invalid", String(e.message || e)); }
  }

  // ---- wiring ------------------------------------------------------------
  $("#tabs").addEventListener("click", (e) => {
    const b = e.target.closest(".tab"); if (!b) return;
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    b.classList.add("active"); state.tab = b.dataset.tab;
    $("#toolbar").style.display = (state.tab === "context") ? "none" : "flex";
    rerender();
  });
  $("#filterInput").addEventListener("input", (e) => { state.filter = e.target.value; rerender(); });
  $("#onlyNeedsSetup").addEventListener("change", (e) => { state.onlyNeedsSetup = e.target.checked; rerender(); });
  $("#reloadBtn").addEventListener("click", refresh);
  $("#recheckBtn").addEventListener("click", validateAll);

  window.App = { state, el, toast, refresh, rerender, validateOne };
  refresh();
})();
