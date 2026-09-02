// PROCESIO environments panel. Switch the default environment, add a client
// environment, and see credentials grouped by the environment they authenticate.
// Every operation calls an existing procesio tool action via /api/procesio/* -
// the dashboard adds no logic of its own, so this stays a thin, maintainable shell.
(function () {
  const App = window.App;
  const el = App.el;
  const toast = App.toast;
  const NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

  function closeModal() { document.getElementById("modalRoot").innerHTML = ""; }

  function shell(title, hint, body, foot) {
    const root = document.getElementById("modalRoot");
    root.innerHTML = "";
    const box = el("div", { class: "modal" },
      el("h3", null, title),
      hint ? el("p", { class: "hint" }, hint) : null,
      body,
      el("div", { class: "modal-foot" }, ...foot));
    const bg = el("div", { class: "modal-bg" }, box);
    bg.addEventListener("click", (e) => { if (e.target === bg) closeModal(); });
    root.appendChild(bg);
    return box;
  }

  async function open() {
    const body = el("div");
    shell("PROCESIO environments",
      "An environment is one PROCESIO installation (<Client>-<ENV>) with its own hosts and credentials. Switching the default moves every action - and the credential bound to it - onto that installation. Unbound credentials stay on Internal-PROD.",
      body, [el("button", { class: "btn ghost", onclick: closeModal }, "Close")]);
    await render(body);
  }

  async function render(body) {
    body.innerHTML = "";
    body.appendChild(el("div", { class: "meta" }, "loading environments..."));
    let data;
    try { data = await API.get("/api/procesio/state"); }
    catch (e) { body.innerHTML = ""; body.appendChild(el("div", { class: "errmsg" }, String(e.message || e))); return; }
    body.innerHTML = "";

    if (data.environments_error) {
      body.appendChild(el("div", { class: "errmsg" },
        "Could not read environments: " + (data.environments_error.message || "unknown")
        + ". Is a procesio credential set up?"));
    }
    renderEnvironments(body, data.environments);
    renderCredentials(body, data.credentials, data.environments);
  }

  // -- environments ---------------------------------------------------------

  function renderEnvironments(body, env) {
    if (!env) return;
    const def = env.default_environment;
    const rows = el("div", { class: "rows" });
    (env.environments || []).forEach(e => {
      const isDef = e.name === def;
      const badge = el("span", { class: "meta", style: "margin-left:8px" },
        (e.builtin ? "built-in" : "custom") + " · " + (e.web_base || ""));
      const controls = el("div", { class: "v" });
      if (isDef) controls.appendChild(el("span", { class: "dot green", title: "active default" }));
      else controls.appendChild(el("button", { class: "btn ghost sm",
        onclick: () => switchTo(body, e.name) }, "Make default"));
      if (!e.builtin) controls.appendChild(el("button", { class: "btn danger sm",
        onclick: () => removeEnv(body, e.name) }, "Remove"));
      rows.appendChild(el("div", { class: "row" },
        el("div", { class: "k" },
          el("span", { class: "dot " + (isDef ? "green" : "amber") }),
          " " + e.name + (isDef ? " (default)" : ""),
          (e.credentials && e.credentials.length)
            ? el("span", { class: "meta", style: "margin-left:8px" }, e.credentials.length + " cred(s)")
            : el("span", { class: "meta", style: "margin-left:8px; color:var(--warn,#b26a00)" }, "no credential"),
          badge),
        controls));
    });
    body.appendChild(el("h4", { style: "margin:6px 0 4px" }, "Environments"));
    body.appendChild(rows);
    body.appendChild(addEnvForm(body));
  }

  function addEnvForm(body) {
    const name = el("input", { placeholder: "Client-ENV, e.g. Delgaz-PROD" });
    const web = el("input", { placeholder: "web API host, https://webapi.<host>" });
    const app = el("input", { placeholder: "front-end host, https://<host>" });
    const forms = el("input", { placeholder: "forms host, https://forms.<host>" });
    const makeDefault = el("input", { type: "checkbox" });
    const add = el("button", { class: "btn" }, "Add environment");
    add.addEventListener("click", async () => {
      const payload = {
        name: (name.value || "").trim(),
        web_base: (web.value || "").trim(),
        app_base: (app.value || "").trim(),
        forms_base: (forms.value || "").trim(),
        make_default: makeDefault.checked,
      };
      if (!NAME_RE.test(payload.name)) { toast("name must look like Client-ENV (letters/digits/.-_)", "bad"); return; }
      if (!payload.web_base || !payload.app_base || !payload.forms_base) { toast("all three host URLs are required", "bad"); return; }
      add.disabled = true;
      try {
        const r = await API.post("/api/procesio/add-environment", payload);
        if (r.ok) { toast("added '" + payload.name + "'", "ok"); if (payload.make_default) App.refresh(); await render(body); }
        else toast("add failed: " + ((r.error && r.error.message) || "unknown"), "bad");
      } catch (e) { toast("add failed: " + e.message, "bad"); }
      finally { add.disabled = false; }
    });
    return el("details", { class: "field", style: "margin-top:12px" },
      el("summary", null, "Add a client environment"),
      el("div", { class: "col", style: "margin-top:8px" },
        name, web, app, forms,
        el("label", { class: "chk" }, makeDefault, " make it the default now"),
        el("div", { class: "rowflex" }, add)));
  }

  async function switchTo(body, name) {
    try {
      const r = await API.post("/api/procesio/set-environment", { name });
      if (r.ok) {
        toast("switched to " + name, "ok");
        App.refresh();
        if (App.validateOne) App.validateOne({ kind: "tool", name: "procesio" });
      } else toast("switch failed: " + ((r.error && r.error.message) || "unknown"), "bad");
    } catch (e) { toast("switch failed: " + e.message, "bad"); }
    await render(body);
  }

  async function removeEnv(body, name) {
    if (!confirm("Remove the environment '" + name + "'? This only deletes its URL entry - credentials are untouched.")) return;
    try {
      const r = await API.post("/api/procesio/remove-environment", { name });
      toast(r.ok ? "removed '" + name + "'" : "remove failed: " + ((r.error && r.error.message) || ""), r.ok ? "ok" : "bad");
      if (r.ok) App.refresh();
    } catch (e) { toast("remove failed: " + e.message, "bad"); }
    await render(body);
  }

  // -- credentials ----------------------------------------------------------

  function renderCredentials(body, creds, env) {
    body.appendChild(el("h4", { style: "margin:16px 0 4px" }, "Credentials by environment"));
    if (!creds) { body.appendChild(el("div", { class: "meta" }, "no credentials readable")); return; }
    const def = creds.default;
    const rows = el("div", { class: "rows" });
    (creds.profiles || []).forEach(p => {
      const isDef = p.is_default;
      const controls = el("div", { class: "v" });
      if (!isDef) controls.appendChild(el("button", { class: "btn ghost sm",
        onclick: () => makeDefaultCred(body, p.name) }, "Make default"));
      controls.appendChild(el("button", { class: "btn danger sm",
        onclick: () => removeCred(body, p.name) }, "Remove"));
      rows.appendChild(el("div", { class: "row" },
        el("div", { class: "k" },
          el("span", { class: "dot " + (isDef ? "green" : "amber") }),
          " " + p.name + (isDef ? " (default)" : ""),
          el("span", { class: "meta", style: "margin-left:8px" },
            (p.type || "") + " · " + (p.environment || "Internal-PROD")
            + (p.workspace ? " · " + p.workspace : ""))),
        controls));
    });
    body.appendChild(rows);
    body.appendChild(el("p", { class: "hint", style: "margin-top:8px" },
      "To add a credential bound to an environment (it needs a secret), run: "
      + "run-tool procesio add-credential --name <label> --type userpass --username <you> --environment <Client-ENV>"));
  }

  async function makeDefaultCred(body, name) {
    try {
      const r = await API.post("/api/procesio/set-default-credential", { name });
      if (r.ok) { toast("default credential -> " + name, "ok"); App.refresh(); if (App.validateOne) App.validateOne({ kind: "tool", name: "procesio" }); }
      else toast("failed: " + ((r.error && r.error.message) || "unknown"), "bad");
    } catch (e) { toast("failed: " + e.message, "bad"); }
    await render(body);
  }

  async function removeCred(body, name) {
    if (!confirm("Remove the credential profile '" + name + "'? This deletes it from Windows Credential Manager.")) return;
    try {
      const r = await API.post("/api/procesio/remove-credential", { name });
      toast(r.ok ? "removed '" + name + "'" : "remove failed: " + ((r.error && r.error.message) || ""), r.ok ? "ok" : "bad");
      if (r.ok) App.refresh();
    } catch (e) { toast("remove failed: " + e.message, "bad"); }
    await render(body);
  }

  if (window.Actions) window.Actions.procesioEnvironments = () => open();
})();
