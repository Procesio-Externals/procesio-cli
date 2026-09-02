// Google multi-account (profile) manager. Lists connected Google profiles and
// lets you add, re-connect, or remove one. All operations run through google-mail
// (the shared account surface); tokens are shared by every Google tool.
(function () {
  const App = window.App;
  const el = App.el;
  const toast = App.toast;
  const LABEL_RE = /^[a-z0-9._-]+$/;

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
    shell("Google accounts",
      "One login can hold several Google accounts, each under a short label (e.g. 'default', 'personal'). Every Google tool shares these.",
      body, [el("button", { class: "btn ghost", onclick: closeModal }, "Close")]);
    await renderList(body);
  }

  async function renderList(body) {
    body.innerHTML = "";
    body.appendChild(el("div", { class: "meta" }, "loading accounts..."));
    let data;
    try { data = await API.get("/api/google/accounts"); }
    catch (e) { body.innerHTML = ""; body.appendChild(el("div", { class: "errmsg" }, String(e.message || e))); return; }
    body.innerHTML = "";

    if (!data.ok) {
      if (!data.has_client) {
        body.appendChild(el("div", { class: "banner" },
          el("h3", null, "Add the Google OAuth client first"),
          el("p", { class: "sub" }, "Store the Google Cloud desktop-client JSON as the google:oauth-client credential (the client-key row on any Google tool's card). Then you can add accounts here.")));
      } else {
        body.appendChild(el("div", { class: "errmsg" },
          "Could not list accounts: " + ((data.error && data.error.message) || "unknown")));
      }
      return;
    }

    const rows = el("div", { class: "rows" });
    (data.accounts || []).forEach(a => {
      const emailSpan = el("span", { class: "meta", style: "margin-left:8px" },
        a.has_token ? "resolving email..." : "");
      rows.appendChild(el("div", { class: "row" },
        el("div", { class: "k" },
          el("span", { class: "dot " + (a.has_token ? "green" : "amber") }),
          " " + a.account + (a.active ? " (active)" : ""),
          emailSpan),
        el("div", { class: "v" },
          el("button", { class: "btn ghost sm", onclick: () => doLogin(body, a.account) }, "Re-connect"),
          el("button", { class: "btn danger sm", onclick: () => doRemove(body, a.account) }, "Remove"))));
      // Fill the email in lazily so the list is instant.
      if (a.has_token) {
        API.get("/api/google/email?account=" + encodeURIComponent(a.account))
          .then(r => { emailSpan.textContent = r.email ? "  " + r.email : ""; })
          .catch(() => { emailSpan.textContent = ""; });
      }
    });
    body.appendChild(rows);

    // Add-account row
    const labelIn = el("input", { placeholder: "new label, e.g. work (not an email)" });
    const addBtn = el("button", { class: "btn" }, "Add account");
    addBtn.addEventListener("click", () => {
      const label = (labelIn.value || "").trim().toLowerCase();
      if (!LABEL_RE.test(label)) { toast("use a short label like 'work' - lowercase, no @", "bad"); return; }
      if ((data.accounts || []).some(a => a.account === label)) { toast("that label already exists - use Re-connect", "bad"); return; }
      doLogin(body, label);
    });
    body.appendChild(el("div", { class: "field", style: "margin-top:12px" },
      el("label", null, "Add another Google account"),
      el("div", { class: "rowflex" }, labelIn, addBtn)));
  }

  async function doLogin(body, account) {
    body.innerHTML = "";
    body.appendChild(el("div", { class: "meta" }, "Opening a browser for " + account + "..."));
    let job;
    try { job = await API.post("/api/google/login", { account }); }
    catch (e) { toast("could not start sign-in: " + e.message, "bad"); return renderList(body); }
    const logbox = el("pre", { class: "log" }, "A browser window opened. Sign in to the Google account you want, then this updates automatically.");
    body.innerHTML = ""; body.appendChild(logbox);
    const poll = setInterval(async () => {
      let s;
      try { s = await API.get("/api/job/get?id=" + job.id); } catch (e) { return; }
      if ((s.logs || []).length) logbox.textContent = s.logs.join("\n");
      if (s.status === "done" || s.status === "failed") {
        clearInterval(poll);
        toast(s.status === "done" ? "account '" + account + "' connected" : "sign-in failed: " + (s.error || ""),
          s.status === "done" ? "ok" : "bad");
        App.refresh();
        renderList(body);
      }
    }, 2000);
  }

  async function doRemove(body, account) {
    if (!confirm("Remove the Google account '" + account + "'? This deletes its token for ALL Google tools.")) return;
    try {
      const r = await API.post("/api/google/remove", { account });
      toast(r.ok ? "removed '" + account + "'" : "remove failed: " + ((r.error && r.error.message) || ""), r.ok ? "ok" : "bad");
    } catch (e) { toast("remove failed: " + e.message, "bad"); }
    App.refresh();
    renderList(body);
  }

  if (window.Actions) window.Actions.googleAccounts = () => open();
})();
