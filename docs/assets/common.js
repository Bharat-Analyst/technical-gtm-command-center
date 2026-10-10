// Shared helpers for every page: data loading, nav, glossary tooltips (ⓘ),
// "Why:" links to the decision log, number formatting, and chart colors read
// from the CSS tokens.

// Every page in the site. `role` matches the "page" field in jd_mapping.json
// (used to link mapping rows to their page).
const PAGES = [
  { file: "index.html", nav: "Lifecycle", role: "Lifecycle" },
  { file: "prioritization.html", nav: "Prioritization", role: "Prioritization" },
  { file: "engagement.html", nav: "Engagement", role: "Engagement and onsite" },
  { file: "programs.html", nav: "Programs & PS", role: "Programs and PS offer" },
  { file: "executive.html", nav: "Executive", role: "Executive view" },
  { file: "methodology.html", nav: "Methodology", role: "Methodology" },
  { file: "decisions.html", nav: "Decision Log", role: "Decision log" },
];

const GTM = {
  data: null, // { accounts, content, glossary, jd, decisions, vars } once init() runs

  // Load a precomputed JSON file from docs/data/.
  async load(name) {
    const res = await fetch(`data/${name}.json`);
    if (!res.ok) throw new Error(`Could not load data/${name}.json (${res.status})`);
    return res.json();
  },

  // Every page calls this first: renders the nav, loads all data, fills the
  // static ⓘ terms. Returns the loaded data.
  async init(pageFile) {
    GTM.renderNav(pageFile);
    const [accounts, content, glossary, jd, decisions] = await Promise.all(
      ["accounts", "content", "glossary", "jd_mapping", "decisions"].map(GTM.load));
    const vars = GTM.metaVars(accounts);
    GTM.data = { accounts, content, glossary, jd, decisions, vars };
    GTM._byLabel = Object.fromEntries(Object.entries(glossary).filter(([k]) => !k.startsWith("_")).map(([k, g]) => [g.label, k]));
    GTM.decorateTerms(document);
    GTM.setupTooltips();
    return GTM.data;
  },

  // Numbers that text templates may use, e.g. "{capacity}". All come from the
  // pipeline's accounts.json so explanations never drift from the data.
  metaVars(accounts) {
    const m = accounts.meta, t = m.thresholds, w = m.weights, win = m.signal_windows_days;
    return {
      total_accounts: accounts.accounts.length,
      score_high: t.score_high, pool_high: GTM.usd(t.pool_of_funds_high), capacity: t.capacity_top_n,
      car_pace: GTM.pct(t.commit_at_risk_max_pace), renewal_days: t.renewal_window_days,
      spike: t.usage_spike_ratio, newdev_min: t.new_developers_min,
      ps_assess: GTM.usd(t.ps_assess_below), ps_migrate: GTM.usd(t.ps_migrate_below),
      w_usage: GTM.pct(w.usage_growth), w_newdev: GTM.pct(w.new_developers), w_eng: GTM.pct(w.engagement), w_burn: GTM.pct(w.commit_burn),
      win_usage: win.usage_growth, win_eng: win.engagement, win_newdev: win.new_developers,
      holdout_share: GTM.pct(m.holdout_share),
    };
  },

  // Replace {placeholders} in a text template with values from metaVars.
  fill(text) {
    return text.replace(/\{(\w+)\}/g, (m, k) => (k in GTM.data.vars ? GTM.data.vars[k] : m));
  },

  // ---------- Nav ----------
  renderNav(current) {
    const nav = document.getElementById("nav");
    if (!nav) return;
    nav.innerHTML = `<ul>${PAGES.map((p) =>
      `<li><a href="${p.file}"${p.file === current ? ' aria-current="page"' : ""}>${p.nav}</a></li>`).join("")}</ul>`;
  },

  pageFileFor(roleName) {
    return (PAGES.find((p) => p.role === roleName) || {}).file;
  },

  // ---------- Glossary tooltips (ⓘ) ----------
  // term("pool_of_funds") → "Pool of funds ⓘ"; pass a label to override the text shown.
  // Also accepts a glossary label, e.g. term("Commit at Risk").
  term(keyOrLabel, label) {
    const g = GTM.data.glossary;
    const key = g[keyOrLabel] ? keyOrLabel : GTM._byLabel[keyOrLabel];
    if (!key) return GTM.esc(label ?? keyOrLabel);
    const entry = g[key];
    const shown = label ?? entry.label;
    return `<span class="term">${GTM.esc(shown)}<button type="button" class="info" data-tip="${GTM.esc(GTM.fill(entry.text))}" aria-label="What is ${GTM.esc(entry.label)}?">ⓘ</button></span>`;
  },

  // Static HTML can mark a term as <span data-term="key">Label</span>.
  decorateTerms(root) {
    root.querySelectorAll("[data-term]").forEach((el) => {
      el.outerHTML = GTM.term(el.dataset.term, el.textContent);
    });
  },

  // One floating tooltip for the whole page, so tables with sideways scroll
  // never clip it. Hover or focus shows it; tap toggles it; Escape hides it.
  setupTooltips() {
    if (document.getElementById("tip")) return;
    const tip = document.createElement("div");
    tip.id = "tip";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.appendChild(tip);
    let owner = null;
    const show = (btn) => {
      owner = btn;
      tip.textContent = btn.dataset.tip;
      tip.hidden = false;
      btn.setAttribute("aria-describedby", "tip");
      const r = btn.getBoundingClientRect();
      const w = Math.min(280, window.innerWidth - 32);
      tip.style.width = `${w}px`;
      const left = Math.min(Math.max(16, r.left + r.width / 2 - w / 2), window.innerWidth - w - 16);
      const below = r.bottom + 8 + tip.offsetHeight < window.innerHeight;
      tip.style.left = `${left}px`;
      tip.style.top = `${below ? r.bottom + 8 : r.top - tip.offsetHeight - 8}px`;
    };
    const hide = () => {
      if (owner) owner.removeAttribute("aria-describedby");
      owner = null;
      tip.hidden = true;
    };
    const infoFrom = (e) => e.target.closest && e.target.closest("button.info");
    document.addEventListener("mouseover", (e) => { const b = infoFrom(e); if (b) show(b); });
    document.addEventListener("mouseout", (e) => { if (infoFrom(e)) hide(); });
    document.addEventListener("focusin", (e) => { const b = infoFrom(e); if (b) show(b); });
    document.addEventListener("focusout", (e) => { if (infoFrom(e)) hide(); });
    document.addEventListener("click", (e) => {
      const b = infoFrom(e);
      if (b) { e.preventDefault(); owner === b && !tip.hidden ? hide() : show(b); } else hide();
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") hide(); });
    window.addEventListener("scroll", hide, { passive: true });
  },

  // ---------- "Why?" links to the decision log ----------
  // Labelled with the decision's title, so two links side by side stay distinct.
  why(id) {
    const d = GTM.data.decisions.find((x) => x.id === id);
    return `<a class="why" href="decisions.html#${id}">Why: ${GTM.esc(d ? d.title : id)}</a>`;
  },

  // ---------- Formatting ----------
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

  // Pool of funds is always shown with its breakdown.
  poolBreakdown(a) {
    return `${GTM.usd(a.unconsumed_commit_usd)} unused commit + ${GTM.usd(a.open_pipeline_usd)} open pipeline`;
  },

  // Escape text before putting it into innerHTML.
  esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },

  // Chips for flags / quadrants; each known term gets its ⓘ.
  chips(items) {
    return items.map((t) => `<span class="chip">${GTM.term(t)}</span>`).join("");
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
      series2: v("--series-2"),
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
    document.querySelectorAll("#nav a").forEach((a) => {
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
    const el = window.location.hash && document.getElementById(window.location.hash.slice(1));
    if (el) el.scrollIntoView({ block: "start" });
  },

  showError(el, err) {
    el.innerHTML = `<div class="card">Could not load data. If you opened this file directly,
      run a local server instead (see README). <span class="muted small">${GTM.esc(err.message)}</span></div>`;
  },
};
