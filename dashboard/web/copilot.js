// Setup copilot chat. Sends the user's question + current state to /api/copilot
// (which routes through the provider-agnostic llm tool) and renders the reply
// plus one-click suggestion buttons that map to the same setup actions.
(function () {
  const App = window.App;
  const el = App.el;

  const MAP = {
    set_credential: (s) => window.Actions.setCred(s.data || {}),
    edit_config: (s) => window.Actions.editConfig(s.data || {}),
    test_tool: (s) => window.Actions.testTool(s.data || {}),
    test_agent: (s) => window.Actions.testAgent(s.data || {}),
    oauth_login: (s) => window.Actions.oauthLogin(s.data || {}),
    web_login: () => window.Actions.webLogin(),
    bootstrap: () => window.Actions.bootstrap({ withTemplates: true }),
  };

  function open() {
    const log = el("div", { class: "copilot-log" });
    const inp = el("input", { placeholder: "Ask how to set something up..." });
    const send = el("button", { class: "btn" }, "Send");

    function addMsg(who, text) {
      log.appendChild(el("div", { class: "cmsg " + who }, text));
      log.scrollTop = log.scrollHeight;
    }
    async function submit() {
      const q = inp.value.trim();
      if (!q) return;
      inp.value = "";
      addMsg("user", q);
      const thinking = el("div", { class: "cmsg bot" }, "thinking...");
      log.appendChild(thinking);
      log.scrollTop = log.scrollHeight;
      try {
        const r = await API.post("/api/copilot", { message: q });
        thinking.remove();
        addMsg("bot", r.reply || "(no reply)");
        (r.suggestions || []).forEach((s) => {
          const b = el("button", { class: "btn ghost sm" }, s.label || s.action);
          b.addEventListener("click", () => {
            const fn = MAP[s.action];
            if (fn) fn(s); else App.toast("unknown suggestion: " + s.action, "bad");
          });
          log.appendChild(el("div", { class: "csugg" }, b));
        });
        log.scrollTop = log.scrollHeight;
      } catch (e) {
        thinking.remove();
        addMsg("bot", "error: " + e.message);
      }
    }
    send.addEventListener("click", submit);
    inp.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });

    const root = document.getElementById("modalRoot");
    root.innerHTML = "";
    const box = el("div", { class: "modal" },
      el("h3", null, "Setup copilot"),
      el("p", { class: "hint" }, "Uses your configured LLM provider. Suggestions are one-click."),
      log,
      el("div", { class: "field" }, el("div", { class: "rowflex" }, inp, send)));
    const bg = el("div", { class: "modal-bg" }, box);
    bg.addEventListener("click", (e) => { if (e.target === bg) root.innerHTML = ""; });
    root.appendChild(bg);
    addMsg("bot", "Ask me what to set up. I can see what is ready and what is missing on this machine.");
    setTimeout(() => inp.focus(), 30);
  }

  const btn = document.getElementById("copilotBtn");
  if (btn) btn.addEventListener("click", open);
})();
