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

  showError(el, err) {
    el.innerHTML = `<div class="card">Could not load data. If you opened this file directly,
      run a local server instead (see README). <span class="muted small">${GTM.esc(err.message)}</span></div>`;
  },
};
