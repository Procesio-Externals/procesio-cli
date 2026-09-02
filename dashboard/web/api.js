// Thin fetch layer. Grabs the one-time token from the launch URL (or a prior
// session, or a manual paste) and attaches it to every call. The token is kept
// in the URL so a reload keeps working; a 401 shows a paste box (app.js).
(function () {
  const params = new URLSearchParams(location.search);
  let TOKEN = params.get("token") || sessionStorage.getItem("aat_token") || "";
  if (TOKEN) sessionStorage.setItem("aat_token", TOKEN);

  function setToken(t) {
    TOKEN = (t || "").trim();
    sessionStorage.setItem("aat_token", TOKEN);
    // Reflect it in the URL so a reload keeps working.
    try {
      const u = new URL(location.href);
      u.searchParams.set("token", TOKEN);
      history.replaceState({}, "", u);
    } catch (_) {}
  }

  function headers() {
    return { "Content-Type": "application/json", "X-Dashboard-Token": TOKEN };
  }

  function netError(e) {
    // fetch() rejects with a TypeError ("Failed to fetch") when the server is
    // unreachable - almost always because the dashboard server was stopped.
    const err = new Error("Dashboard server is not responding. Is it still "
      + "running? Restart it with: python dashboard/serve.py");
    err.cause = e;
    return err;
  }

  async function get(path) {
    let r;
    try { r = await fetch(path, { headers: headers() }); }
    catch (e) { throw netError(e); }
    return unwrap(r);
  }

  async function post(path, body) {
    let r;
    try {
      r = await fetch(path, {
        method: "POST", headers: headers(),
        body: JSON.stringify(body || {}),
      });
    } catch (e) { throw netError(e); }
    return unwrap(r);
  }

  async function unwrap(r) {
    let data = null;
    try { data = await r.json(); } catch (e) { data = { error: "bad_response" }; }
    if (!r.ok) {
      const msg = (data && (data.message || data.error)) || r.statusText;
      const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      err.status = r.status; err.payload = data;
      throw err;
    }
    return data;
  }

  // Server-Sent Events via EventSource (token goes in the query - loopback only).
  function stream(path, handlers) {
    const url = path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(TOKEN);
    const es = new EventSource(url);
    for (const [evt, fn] of Object.entries(handlers)) {
      es.addEventListener(evt, (e) => {
        let d = {};
        try { d = JSON.parse(e.data); } catch (_) {}
        fn(d, es);
      });
    }
    es.onerror = () => es.close();
    return es;
  }

  window.API = { get, post, stream, setToken };
})();
