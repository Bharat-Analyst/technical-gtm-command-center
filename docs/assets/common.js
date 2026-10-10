// Shared helpers for every page: data loading, number formatting, chips,
// and chart colors read from the CSS tokens (so charts match light/dark mode).

const GTM = {
  // Load a precomputed JSON file from docs/data/.
  async load(name) {
    const res = await fetch(`data/${name}.json`);
    if (!res.ok) throw new Error(`Could not load data/${name}.json (${res.status})`);
    return res.json();
  },

  // $1.3M / $860K / $25K — compact money for cards and tables.
  usd(n) {
    const abs = Math.abs(n);
    if (abs >= 1e6) return `$${(n / 1e6).toFixed(abs >= 1e7 ? 0 : 1)}M`;
    if (abs >= 1e3) return `$${Math.round(n / 1e3)}K`;
    return `$${Math.round(n)}`;
  },

  pct(x, digits = 0) {
    return `${(x * 100).toFixed(digits)}%`;
  },

  // Escape text before putting it into innerHTML.
  esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },

  chips(items) {
    return items.map((t) => `<span class="chip">${GTM.esc(t)}</span>`).join("");
  },

  // Status always shows shape + word, never color alone.
  status(s) {
    const label = { green: "On track", yellow: "At risk", red: "Blocked" }[s] || s;
    return `<span class="chip status status-${GTM.esc(s)}"><span class="dot" aria-hidden="true"></span>${label}</span>`;
  },

  // Chart colors pulled from CSS custom properties.
  colors() {
    const css = getComputedStyle(document.documentElement);
    const v = (name) => css.getPropertyValue(name).trim();
    return {
      surface: v("--surface"), text: v("--text"), text2: v("--text-2"), muted: v("--muted"),
      grid: v("--grid"), axis: v("--axis"), accent: v("--accent"), highlight: v("--highlight"), out: v("--out"),
    };
  },

  // Re-run a render function when the OS switches light/dark.
  onThemeChange(fn) {
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", fn);
  },

  // ---------- Cross-page state ----------
  // All state lives in the URL query string: ?account=<slug>&step=<1-8>.
  // No cookies or storage, so any view can be bookmarked or shared as a link.
  params() {
    return new URLSearchParams(window.location.search);
  },

  // Resolve ?account= to an account. Accepts the full slug ("northwind-commerce"),
  // a Salesforce Id, or a unique slug prefix ("northwind").
  findAccount(accounts, key) {
    if (!key) return null;
    key = key.toLowerCase();
    const exact = accounts.find((a) => a.slug === key || a.account_id.toLowerCase() === key);
    if (exact) return exact;
    const prefix = accounts.filter((a) => a.slug.startsWith(key));
    return prefix.length === 1 ? prefix[0] : null;
  },

  // Selected account for this page: from the URL, else the default (Northwind).
  selectedAccount(accounts, fallbackName = "Northwind Commerce") {
    return GTM.findAccount(accounts, GTM.params().get("account"))
      || accounts.find((a) => a.account_name === fallbackName);
  },

  // Build a link to another page carrying the account (and optionally the step).
  link(page, slug, step, hash = "") {
    const q = new URLSearchParams({ account: slug });
    if (step) q.set("step", step);
    return `${page}?${q}${hash}`;
  },

  // Keep the selected account when moving between pages via the top nav.
  carryAccountInNav(slug) {
    document.querySelectorAll("nav a").forEach((a) => {
      const page = a.getAttribute("href").split("?")[0];
      a.setAttribute("href", GTM.link(page, slug));
    });
  },

  // Arriving from a lifecycle step: show a way back to exactly that step.
  backToLifecycle(account) {
    const step = Number(GTM.params().get("step"));
    if (!step) return;
    const p = document.createElement("p");
    p.className = "small back-link";
    p.innerHTML = `<a href="${GTM.link("index.html", account.slug, step)}">← Back to lifecycle step ${step} for ${GTM.esc(account.account_name)}</a>`;
    document.querySelector("main").prepend(p);
  },

  // Content is drawn after data loads, so the browser's own #anchor jump
  // happens too early. Call this after rendering.
  scrollToHash() {
    const el = window.location.hash && document.querySelector(window.location.hash);
    if (el) el.scrollIntoView({ block: "start" });
  },

  showError(el, err) {
    el.innerHTML = `<div class="card">Could not load data. If you opened this file directly,
      run a local server instead (see README). <span class="muted small">${GTM.esc(err.message)}</span></div>`;
  },
};
