// Setup + verification interactions: modals and API calls. Attached to
// window.Actions; app.js routes card buttons here via App.act(name, data).
(function () {
  const App = window.App;
  const el = App.el;
  const toast = App.toast;

  // ---- modal plumbing ---------------------------------------------------
  function closeModal() { document.getElementById("modalRoot").innerHTML = ""; }
  function modal(title, hint, bodyNodes, footNodes) {
    const root = document.getElementById("modalRoot");
    root.innerHTML = "";
    const box = el("div", { class: "modal" },
      el("h3", null, title),
      hint ? el("p", { class: "hint" }, hint) : null,
      ...bodyNodes,
      el("div", { class: "modal-foot" }, ...footNodes));
    const bg = el("div", { class: "modal-bg" }, box);
    bg.addEventListener("click", (e) => { if (e.target === bg) closeModal(); });
    root.appendChild(bg);
    return box;
  }
  function field(labelText, inputNode) {
    return el("div", { class: "field" }, el("label", null, labelText), inputNode);
  }
  function input(attrs) { return el("input", attrs || {}); }

  async function withBtn(btn, fn) {
    const old = btn.textContent; btn.disabled = true; btn.textContent = "working...";
    try { await fn(); } finally { btn.disabled = false; btn.textContent = old; }
  }

  // ---- credentials ------------------------------------------------------
  function setCred(data) {
    const ns = data.secret.includes(":");
    const valIn = input({ type: "password", placeholder: "paste the secret value", autocomplete: "off" });
    const save = el("button", { class: "btn" }, "Store");
    save.addEventListener("click", () => withBtn(save, async () => {
      const value = valIn.value;
      if (!value || value.length < 4) { toast("value looks too short", "bad"); return; }
      const r = await API.post("/api/credential/set",
        { tool: data.tool, secret: data.secret, value });
      if (r.ok) { toast("stored " + data.secret, "ok"); closeModal(); App.refresh(); }
      else { toast(r.message || "failed", "bad"); }
    }));
    modal("Store credential",
      data.tool + " / " + data.secret + (ns ? "  (shared namespace secret)" : "") +
      "  -  written straight to Windows Credential Manager, never to disk.",
      [field("Value", valIn)],
      [el("button", { class: "btn ghost", onclick: closeModal }, "Cancel"), save]);
    setTimeout(() => valIn.focus(), 30);
  }

  async function delCred(data) {
    if (!confirm("Delete credential " + data.secret + " for " + data.tool + "?")) return;
    const r = await API.post("/api/credential/delete", { tool: data.tool, secret: data.secret });
    if (r.ok) { toast("deleted", "ok"); App.refresh(); } else toast(r.message || "failed", "bad");
  }

  // ---- bootstrap --------------------------------------------------------
  async function bootstrap(data) {
    toast("initializing user-data folder...", "");
    try {
      const r = await API.post("/api/bootstrap", { with_templates: !!data.withTemplates });
      toast("bootstrap done: " + (r.templates_copied ? r.templates_copied.length : 0) +
        " templates copied", "ok");
      App.refresh();
    } catch (e) { toast("bootstrap failed: " + e.message, "bad"); }
  }

  // ---- config editor ----------------------------------------------------
  async function editConfig(data) {
    let cfg;
    try { cfg = await API.get("/api/config/get?component=" + encodeURIComponent(data.component) +
      "&name=" + encodeURIComponent(data.name)); }
    catch (e) { toast("cannot load config: " + e.message, "bad"); return; }
    const start = cfg.data != null ? cfg.data : (cfg.template != null ? cfg.template : {});
    const ta = el("textarea", { spellcheck: "false" });
    ta.value = JSON.stringify(start, null, 2);
    const msg = el("div", { class: "field" });
    const showVerdict = (v) => {
      msg.innerHTML = "";
      (v.errors || []).forEach(e2 => msg.appendChild(el("div", { class: "err" }, "error: " + e2)));
      (v.warnings || []).forEach(w => msg.appendChild(el("div", { class: "err", style: "color:var(--amber)" }, "warn: " + w)));
      if (!(v.errors || []).length && !(v.warnings || []).length)
        msg.appendChild(el("div", { class: "meta" }, "looks valid"));
    };
    const parse = () => { try { return [JSON.parse(ta.value), null]; } catch (e) { return [null, e.message]; } };
    const validate = el("button", { class: "btn ghost" }, "Validate");
    validate.addEventListener("click", async () => {
      const [obj, err] = parse();
      if (err) { showVerdict({ errors: ["invalid JSON: " + err] }); return; }
      const v = await API.post("/api/config/validate", { component: data.component, name: data.name, data: obj });
      showVerdict(v);
    });
    const save = el("button", { class: "btn" }, "Save");
    save.addEventListener("click", () => withBtn(save, async () => {
      const [obj, err] = parse();
      if (err) { showVerdict({ errors: ["invalid JSON: " + err] }); return; }
      try {
        const r = await API.post("/api/config/set", { component: data.component, name: data.name, data: obj });
        toast("saved " + data.component + "/" + data.name, "ok");
        if (r.warnings && r.warnings.length) showVerdict({ warnings: r.warnings });
        else { closeModal(); App.refresh(); }
      } catch (e) {
        showVerdict({ errors: (e.payload && e.payload.errors) || [e.message] });
      }
    }));
    modal("Edit config - " + data.component + "/" + data.name,
      cfg.has_schema ? "This config is schema-validated." :
        "Saved to context-state-knowledge/config/" + data.component + "/" + data.name + ".json",
      [field("JSON", ta), msg],
      [el("button", { class: "btn ghost", onclick: closeModal }, "Cancel"), validate, save]);
  }

  // ---- web session capture ---------------------------------------------
  // data (optional prefill from a tool card): {name, login_url, persistent, channel, label, present}
  function webLogin(data) {
    data = data || {};
    const prefilled = !!data.name;
    const isReconnect = !!data.present;
    const nameIn = input({ placeholder: "session name (e.g. ryver, whatsapp)" });
    nameIn.value = data.name || "";
    const urlIn = input({ placeholder: "https://login-url" });
    urlIn.value = data.login_url || data.url || "";
    const persist = input({ type: "checkbox" });
    persist.checked = !!data.persistent;
    const channel = el("select", null,
      el("option", { value: "" }, "bundled Chromium"),
      el("option", { value: "chrome" }, "chrome (real Chrome, for Google sign-in)"),
      el("option", { value: "msedge" }, "msedge"));
    channel.value = data.channel || "";

    // The 3-step flow, spelled out so a first-timer knows exactly what to do.
    const steps = el("ol", { class: "steps" },
      el("li", null, "Click ", el("b", null, "Open browser"), " below - a real browser window opens at the login page."),
      el("li", null, "Log in there the way you normally would (username, password, 2FA)."),
      el("li", null, "Come back here and click ", el("b", null, "I have logged in"), "."));

    const fields = [field("Session name", nameIn), field("Login URL", urlIn),
      el("div", { class: "field" }, el("label", null, "Browser channel"), channel),
      el("label", { class: "chk" }, persist, " Persistent profile (needed for WhatsApp)")];
    // When opened from a card these are already correct - tuck them away so a
    // first-time user isn't unsure whether to change them.
    const fieldBlock = prefilled
      ? el("details", { class: "advanced" },
          el("summary", null, "Advanced - already set for this tool, no need to change"), ...fields)
      : el("div", null, ...fields);

    const status = el("div", { class: "field" });
    const startBtn = el("button", { class: "btn" }, "Open browser");
    startBtn.addEventListener("click", () => withBtn(startBtn, async () => {
      if (!nameIn.value || !urlIn.value) { toast("session name and login URL are required", "bad"); return; }
      const job = await API.post("/api/session/start", {
        name: nameIn.value.trim(), url: urlIn.value.trim(),
        persistent: persist.checked, channel: channel.value || null });
      status.innerHTML = "";
      status.appendChild(el("div", { class: "meta" },
        "Browser opened. Finish logging in there, then click below."));
      const commit = el("button", { class: "btn" }, "I have logged in - save");
      commit.addEventListener("click", () => withBtn(commit, async () => {
        const res = await API.post("/api/session/commit", { job_id: job.id });
        if (res.status === "done") { toast("login saved for " + nameIn.value, "ok"); closeModal(); App.refresh(); }
        else { toast("save failed: " + (res.error || res.status), "bad"); }
      }));
      status.appendChild(commit);
    }));

    const hint = isReconnect
      ? "You're already connected. Only re-connect if the login stopped working or you want to switch the logged-in account - nothing to change here, just:"
      : "This tool has no API - it signs in through your browser. Your login is saved locally on this machine; the dashboard never sees your password. To connect:";

    modal(prefilled ? (isReconnect ? "Re-connect " : "Connect ") + (data.label || data.name) + " login"
                    : "Capture a web login",
      hint, [steps, status, fieldBlock],
      [el("button", { class: "btn ghost", onclick: closeModal }, "Close"), startBtn]);
  }
  const webConnect = webLogin;  // card "Connect"/"reconnect" passes the tool's prefill

  // ---- OAuth ------------------------------------------------------------
  async function oauthLogin(data) {
    toast("starting OAuth for " + data.tool + "...", "");
    let job;
    try { job = await API.post("/api/oauth/start", { tool: data.tool }); }
    catch (e) { toast("oauth start failed: " + e.message, "bad"); return; }
    const logbox = el("pre", { class: "log" }, "launching browser...");
    modal("OAuth login - " + data.tool,
      "A browser opened for consent. It completes automatically on redirect.",
      [logbox], [el("button", { class: "btn ghost", onclick: closeModal }, "Close")]);
    const poll = setInterval(async () => {
      let s;
      try { s = await API.get("/api/job/get?id=" + job.id); } catch (e) { return; }
      logbox.textContent = (s.logs || []).join("\n") || s.status;
      if (s.status === "done" || s.status === "failed") {
        clearInterval(poll);
        toast(s.status === "done" ? "OAuth complete" : "OAuth failed: " + (s.error || ""),
          s.status === "done" ? "ok" : "bad");
        App.refresh();
      }
    }, 1500);
  }

  // ---- details ----------------------------------------------------------
  function details(data) {
    const list = (data.kind === "tool" ? App.state.inv.tools :
      data.kind === "agent" ? App.state.inv.agents : App.state.inv.skills) || [];
    const item = list.find(i => i.name === data.name);
    if (!item) { toast("not found", "bad"); return; }
    const body = [el("p", { class: "card-desc" }, item.description || "")];
    const hasOauth = (item.actions || []).some(a => a.name === "auth-login");
    if (hasOauth) {
      const b = el("button", { class: "btn" }, "Run OAuth login");
      b.addEventListener("click", () => { closeModal(); oauthLogin({ tool: item.name }); });
      body.push(el("div", { class: "card-foot" }, b));
    }
    if (item.actions && item.actions.length) {
      body.push(el("div", { class: "section-title" }, el("h2", null, "actions"), el("span", { class: "line" })));
      const rows = el("div", { class: "rows" });
      item.actions.forEach(a => rows.appendChild(el("div", { class: "row" },
        el("div", { class: "k" }, a.name),
        el("div", { class: "v meta" }, (a.args || []).map(x => x.name).join(", ")))));
      body.push(rows);
    }
    modal(item.name, item.kind, body, [el("button", { class: "btn ghost", onclick: closeModal }, "Close")]);
  }

  // ---- M4 verification (endpoints land in M4) ---------------------------
  async function testProvider(data) {
    toast("testing provider " + data.provider + "...", "");
    try {
      const r = await API.post("/api/llm/provider/test", { provider: data.provider });
      toast(r.ok ? "provider OK (" + (r.model || "") + ")" : "failed: " + (r.detail || ""), r.ok ? "ok" : "bad");
    } catch (e) { toast("test failed: " + e.message, "bad"); }
  }
  async function testTool(data) { runTest("/api/test/tool", { name: data.name }, "tool " + data.name); }
  async function testAgent(data) { runTest("/api/test/agent", { name: data.name }, "agent " + data.name); }
  async function runTest(path, body, label) {
    const logbox = el("pre", { class: "log" }, "running...");
    modal("Test " + label, "Runs a live check and, if a provider is configured, an LLM judgement.",
      [logbox], [el("button", { class: "btn ghost", onclick: closeModal }, "Close")]);
    try {
      const r = await API.post(path, body);
      logbox.textContent = JSON.stringify(r, null, 2);
      toast(r.ok ? label + " works" : label + ": " + (r.summary || "issue"), r.ok ? "ok" : "bad");
    } catch (e) { logbox.textContent = "error: " + e.message; }
  }
  async function explainProbe(data) {
    const path = data.kind === "agent" ? "/api/test/agent" : "/api/test/tool";
    const box = el("pre", { class: "log" }, "asking the AI why this is failing...");
    modal("Why isn't " + data.name + " working?",
      "The live check plus a plain-language explanation from your AI model.",
      [box], [el("button", { class: "btn ghost", onclick: closeModal }, "Close")]);
    try {
      const r = await API.post(path, { name: data.name });
      box.textContent = r.llm || r.summary || JSON.stringify(r, null, 2);
    } catch (e) { box.textContent = "error: " + e.message; }
  }

  async function inspectContext() {
    const logbox = el("pre", { class: "log" }, "inspecting...");
    modal("Context & state inspection", "Summarized via the configured LLM provider.",
      [logbox], [el("button", { class: "btn ghost", onclick: closeModal }, "Close")]);
    try { const r = await API.get("/api/context/inspect"); logbox.textContent = r.summary || JSON.stringify(r, null, 2); }
    catch (e) { logbox.textContent = "error: " + e.message; }
  }

  const wlBtn = document.getElementById("webLoginBtn");
  if (wlBtn) wlBtn.addEventListener("click", webLogin);

  window.Actions = {
    setCred, delCred, bootstrap, editConfig, details, webLogin, webConnect, oauthLogin,
    testProvider, testTool, testAgent, explainProbe, inspectContext,
  };
})();
