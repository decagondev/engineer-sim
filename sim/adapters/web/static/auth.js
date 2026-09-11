/* Shared token + API helpers for firebase / fake auth modes. */
window.SimAuth = (function () {
  const KEY = "simToken";
  function token() { return sessionStorage.getItem(KEY) || ""; }
  function setToken(t) { if (t) sessionStorage.setItem(KEY, t); else sessionStorage.removeItem(KEY); }
  function headers(extra) {
    const h = Object.assign({}, extra || {});
    const t = token();
    if (t) h.Authorization = "Bearer " + t;
    return h;
  }
  async function config() {
    return (await fetch("/api/auth/config")).json();
  }
  async function me() {
    const r = await fetch("/api/auth/me", { headers: headers() });
    if (!r.ok) return null;
    return r.json();
  }
  function signOut(next) {
    setToken("");
    location.href = next || "/login";
  }
  function requireToken(next) {
    if (!token()) {
      location.href = "/login?next=" + encodeURIComponent(next || location.pathname + location.hash);
      return false;
    }
    return true;
  }
  const _fetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    opts = opts || {};
    const t = token();
    if (t) {
      const headers = new Headers(opts.headers || {});
      if (!headers.has("Authorization")) headers.set("Authorization", "Bearer " + t);
      opts = Object.assign({}, opts, { headers });
    }
    return _fetch(url, opts);
  };
  return { token, setToken, headers, config, me, signOut, requireToken };
})();
