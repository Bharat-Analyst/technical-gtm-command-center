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
  { file: "how-this-works.html", nav: "How this works", role: "How this works" },
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
    GTM.renderCredit();
    const [accounts, content, glossary, jd, decisions, faq] = await Promise.all(
      ["accounts", "content", "glossary", "jd_mapping", "decisions", "faq"].map(GTM.load));
    const vars = GTM.metaVars(accounts);
    GTM.data = { accounts, content, glossary, jd, decisions, faq, vars };
    GTM._byLabel = Object.fromEntries(Object.entries(glossary).filter(([k]) => !k.startsWith("_")).map(([k, g]) => [g.label, k]));
    GTM.decorateTerms(document);
    GTM.renderFaqSlots(document);
    GTM.setupTooltips();
    return GTM.data;
  },

  // Numbers that text templates may use, e.g. "{capacity}". All come from the
  // pipeline's accounts.json so explanations never drift from the data.
  metaVars(accounts) {
    const m = accounts.meta, t = m.thresholds, w = m.weights, win = m.signal_windows, c = m.capacity;
    return {
      total_accounts: accounts.accounts.length,
      score_high: t.score_high, pool_high: GTM.usd(t.pool_of_funds_high),
      car_pace: GTM.pct(t.commit_at_risk_max_pace), car_min_elapsed: GTM.pct(t.commit_at_risk_min_elapsed),
      renewal_days: t.renewal_coming_days, surge_min: t.builder_surge_min,
      spike_min: GTM.pct(t.usage_spike_min), drop_max: GTM.pct(-t.usage_drop_max),
      on_track_good: GTM.pct(t.on_track_good), on_track_warn: GTM.pct(t.on_track_warn),
      sprint_min_unused: GTM.usd(t.sprint_min_unused),
      ps_starter: GTM.usd(t.ps_starter_below), ps_standard: GTM.usd(t.ps_standard_below),
      w_usage: GTM.pct(w.usage_growth), w_builders: GTM.pct(w.new_builders), w_eng: GTM.pct(w.engagement), w_breadth: GTM.pct(w.product_breadth),
      win_usage: win.usage_growth_months, win_builders: win.new_builders_days, win_eng: win.engagement_days, win_newprod: win.new_product_days,
      holdout_share: GTM.pct(m.holdout_share),
      sas: c.sas, fdes: c.fdes, sa_load: c.sa_load, fde_load: c.fde_load, sa_slots: c.sa_slots, fde_slots: c.fde_slots,
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

  // Ownership credit, shown at the top of every page right under the header.
  renderCredit() {
    const header = document.querySelector(".site-header");
    if (!header || document.querySelector(".credit-bar")) return;
    const bar = document.createElement("div");
    bar.className = "credit-bar";
    bar.innerHTML = `<div class="inner"><strong>Built with AI</strong> · Owned and reviewed by Bharat · Coded using AI (Claude Code)</div>`;
    header.after(bar);
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

  // ---------- Questions (faq.json) ----------
  // Small expandable "?" items placed next to the chart or table they explain.
  faqMini(ids) {
    const items = ids.map((id) => GTM.data.faq.find((q) => q.id === id)).filter(Boolean);
    return `<div class="faq-mini">${items.map((q) => `
      <details><summary><span class="q-mark" aria-hidden="true">?</span>${GTM.esc(q.question)}</summary>
        <p>${GTM.esc(GTM.fill(q.answer))}</p>
      </details>`).join("")}</div>`;
  },
  // Fill every element marked <div data-faq="id1,id2"></div>.
  renderFaqSlots(root = document) {
    root.querySelectorAll("[data-faq]").forEach((el) => { el.outerHTML = GTM.faqMini(el.dataset.faq.split(",")); });
  },

  // ---------- "Why this account?" ----------
  // One plain-English summary built from the account's real data, worded
  // differently for each type of help.
  whyThisAccount(a) {
    const m = GTM.data.accounts.meta, win = m.signal_windows.new_builders_days;
    const [DEEP, BET, SCALED, DIGITAL] = m.quadrants;
    const usd = GTM.usd, pct = GTM.pct;
    const builders = `${a.new_builders_60d} new builder${a.new_builders_60d === 1 ? "" : "s"} in ${win} days`;
    const pool = `${usd(a.pool_of_funds)} pool of funds (${GTM.poolBreakdown(a)})`;
    const growth = `usage ${a.usage_growth_3m >= 0 ? "up" : "down"} ${pct(Math.abs(a.usage_growth_3m))} in 3 months`;
    const commit = `${pct(a.commit_used_share)} of its ${usd(a.annual_commit_usd)} commit used with ${pct(a.contract_elapsed_share)} of the year gone`;
    const alerts = a.flags.length ? `${a.flags.length} active alert${a.flags.length === 1 ? "" : "s"} (${a.flags.join(", ")})` : "no active alerts";
    const lead = a.override_reason
      ? `${a.account_name} was moved from ${a.model_quadrant} to ${a.quadrant} by a logged override: ${a.override_reason}. `
      : "";
    let text;
    if (a.quadrant === DEEP) {
      text = `${lead}${a.override_reason ? "It" : a.account_name} gets ${DEEP}: a propensity score of ${a.propensity_score} (${builders}; ${growth}), a ${pool}, and ${alerts}. ` +
        `It has ${commit} and renews in ${a.days_to_renewal} days, so an SA leading the design and an FDE building with its developers is the fastest way to get a workload live.`;
    } else if (a.quadrant === SCALED) {
      text = `${lead}${a.account_name} gets ${SCALED}: it is likely to grow (propensity score ${a.propensity_score}; ${builders}; ${growth}), ` +
        `but its ${pool} doesn't justify dedicated engineers. Office hours, workshops and reference architectures keep the momentum going at low cost.`;
    } else if (a.quadrant === BET) {
      text = `${lead}${a.account_name} is a ${BET}: a ${pool} is in play, but the propensity score is only ${a.propensity_score} (${builders}; ${a.meetings_90d ? `${a.meetings_90d} meetings and calls` : "no meetings or calls"} in 90 days). ` +
        `Big money with little activity needs discovery first: the SA works with the account team to find the first use case; an FDE joins only if a real project appears.`;
    } else {
      text = `${lead}${a.account_name} is ${DIGITAL}: a propensity score of ${a.propensity_score} and a ${pool} mean SA or FDE time wouldn't change the outcome. ` +
        `Docs, templates and product emails keep it moving, and alerts watch for change; today it has ${a.flags.length ? `${a.flags.length === 1 ? "one alert" : `${a.flags.length} alerts`}: ${a.flags.join(", ")}` : "no alerts"}.`;
    }
    return text;
  },

  whyThisAccountBox(a) {
    return `<div class="why-account"><strong>Why this account?</strong> ${GTM.esc(GTM.whyThisAccount(a))}</div>`;
  },

  // ---------- "Why?" links to the decision log ----------
  // Labelled with the decision's title, so two links side by side stay distinct.
  why(id) {
    const d = GTM.data.decisions.find((x) => x.id === id);
    return `<a class="why" href="how-this-works.html#${d ? d.section : id}">Why: ${GTM.esc(d ? d.title : id)}</a>`;
  },

  // ---------- Formatting ----------
  // The one money formatter for the whole site:
  //   millions → up to two decimals, trailing zeros dropped ($1.31M, $1.06M, $1.2M)
  //   thousands → whole thousands ($860K, $47K); smaller → whole dollars ($950)
  usd(n) {
    const sign = n < 0 ? "-" : "", abs = Math.abs(n);
    const millions = (v) => `${sign}$${parseFloat((v / 1e6).toFixed(2))}M`;
    if (abs >= 1e6) return millions(abs);
    if (abs >= 1e3) {
      const k = Math.round(abs / 1e3);
      return k >= 1000 ? millions(k * 1e3) : `${sign}$${k}K`;   // $999.6K rounds up to $1M, not "$1000K"
    }
    return `${sign}$${Math.round(abs)}`;
  },
  // Exact dollars, for raw-data tables ($1,200,000).
  usdFull(n) {
    return `${n < 0 ? "-" : ""}$${Math.round(Math.abs(n)).toLocaleString("en-US")}`;
  },

  pct(x, digits = 0) {
    return `${(x * 100).toFixed(digits)}%`;
  },

  // On-track % (burn pace) always comes with its status band and a link to the
  // assumption behind the bands.
  onTrackStatus(pace) {
    const t = GTM.data.accounts.meta.thresholds;
    const [cls, label] = pace >= t.on_track_good ? ["green", "On track"]
      : pace >= t.on_track_warn ? ["yellow", "Slightly behind"] : ["red", "Behind"];
    return `<span class="chip status status-${cls}"><span class="dot" aria-hidden="true"></span>${label}</span>`;
  },
  onTrack(a, withWhy = true) {
    return `${GTM.pct(a.burn_pace)} ${GTM.onTrackStatus(a.burn_pace)}${withWhy ? GTM.why("on-track-bands") : ""}`;
  },

  // Team capacity: the same slot-filling rule as pipeline.assign_capacity, so the
  // sliders can show what a bigger or smaller team would cover.
  //   FDE slots → top Deep engagement accounts (alerts first, then opportunity value);
  //   remaining SA slots → Deep engagement and Strategic bet queues merged by opportunity value.
  assignCapacity(accounts, sas, fdes) {
    const m = GTM.data.accounts.meta, c = m.capacity, [DEEP, BET] = m.quadrants;
    const order = [...accounts].sort((a, b) =>
      (b.flags.length > 0) - (a.flags.length > 0) || b.expected_value_usd - a.expected_value_usd || a.account_id.localeCompare(b.account_id));
    const fdeSlots = fdes * c.fde_load, saSlots = sas * c.sa_load;
    const deepQ = order.filter((a) => a.quadrant === DEEP), betQ = order.filter((a) => a.quadrant === BET);
    const fde = new Set(deepQ.slice(0, fdeSlots).map((a) => a.account_id));
    const sa = new Set(fde);
    const deepRest = deepQ.slice(fdeSlots);
    while (sa.size < saSlots && (deepRest.length || betQ.length)) {
      const takeDeep = !betQ.length || (deepRest.length && deepRest[0].expected_value_usd >= betQ[0].expected_value_usd);
      sa.add((takeDeep ? deepRest : betQ).shift().account_id);
    }
    return { fde, sa };
  },

  // Straight-line On-track % assumes even spending all year. Seasonal
  // industries (retail peaks in Q4) can look further behind than they are.
  SEASONAL_INDUSTRIES: ["Retail & eCommerce"],
  seasonalNote(a) {
    if (!GTM.SEASONAL_INDUSTRIES.includes(a.industry)) return "";
    return `<p class="note">Seasonality: On-track % assumes even spending all year, so it can overstate risk for retail, where spend peaks in Q4. Possibly we can adjust it using spending curves from similar customers.</p>`;
  },

  // Pool of funds is always shown with its breakdown.
  poolBreakdown(a) {
    return `${GTM.usd(a.unused_commit)} unused commit + ${GTM.usd(a.open_pipeline_usd)} open pipeline`;
  },

  // Escape text before putting it into innerHTML.
  esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },

  // Chips for alerts / types of help; each known term gets its ⓘ.
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
