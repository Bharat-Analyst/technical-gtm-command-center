# Technical GTM Command Center — project guide for Claude

## What this is
A portfolio proof-of-concept for a **Strategy Manager, Technical Programs** role on
Cloudflare's Developer GTM Strategy & Incubation team. It shows how I would:
- decide where **Solutions Architects (SAs)** and **Forward Deployed Engineers (FDEs)** spend their time,
- run the engagement end to end, and
- prove ROI to leadership.

Personal project. **Not affiliated with Cloudflare.** All data is synthetic.

## Role responsibilities → modules (every module must map to one)
| # | Responsibility | Module / output |
|---|----------------|-----------------|
| 1 | Prioritization & visibility | Propensity × pool of funds matrix, account flags, SA/FDE capacity view |
| 2 | Strategic customer engagement | Engagement tracker (stages, owners, next steps, health) |
| 3 | Technical onsites | Onsite planning model (who goes, agenda, expected outcome, cost) |
| 4 | Technical programs | Repeatable proactive SA program playbook (triggers → plays → exit criteria) |
| 5 | Professional Services packaging | Packaged PS offer + business case (scope, price, margin, payback) |
| 6 | Leadership visibility / ROI | Executive view with **holdout-based** ROI (treated vs. control accounts) |

## The story: Northwind Commerce
A fictional customer, **Northwind Commerce**, flows through every stage: flagged by the
matrix → engaged → onsite → enrolled in the program → offered a PS package → counted in ROI.
Each page should show where Northwind sits at that stage.

## Technical constraints (do not deviate without asking)
- **Python 3.11**, **pandas**, **scikit-learn**. Nothing else heavy.
- **No database, no dbt.** CSV files in folders that mirror warehouse layers:
  - `data/raw/` — source-system extracts (Salesforce objects, usage telemetry)
  - `data/processed/` — staging + marts (cleaned, joined, scored)
  - `data/output/` — Salesforce write-back files (fields we'd push back to CRM)
- Synthetic data modeled on **Salesforce objects** (Account, Opportunity, Contact,
  User, Task/Event, custom Engagement object) + **product usage telemetry**.
- **Fixed random seed = 42** everywhere (numpy, random, sklearn) for reproducibility.
- **Front end:** static site in `/docs` (plain HTML/CSS/JS + Plotly.js from a CDN,
  pinned version, no build tools) that reads **precomputed JSON** in `docs/data/`.
  Hosted on GitHub Pages (serve from `/docs` on `main`).
- **All company names fictional.** No Cloudflare logos, colors-as-branding, or trademarks.
- **Every page** shows the banner: `Personal project, not affiliated with Cloudflare.`
  (Owner decision 2026-10-10: don't label data as synthetic on the site; the owner states it themselves.)

## Code style
- Simple, readable code. Small functions. Prefer clarity over cleverness.
- Comments explain the **business logic** (why a threshold, why a weight), not just the Python.
- Business assumptions (weights, thresholds, costs, rates) live in one config file,
  not scattered as magic numbers.
- Pipeline is runnable end to end with one command; outputs are deterministic.

## Working rules
- The owner is learning: briefly explain each decision and what each new file does.
- Work in **small steps**. After each step, **commit locally** with a clear message.
- **Never push to GitHub or publish anything** (Pages, artifacts, etc.) without asking first.
- Ask before adding dependencies or changing the constraints above.

## Current files
- `generate_data.py` → `data/raw/accounts.csv` (synthetic, seed 42, 499 random + 4 planted featured accounts)
- `pipeline.py` → scorecard, pool of funds/EV, holdout, flags, quadrants, capacity; writes
  `data/processed/account_scores.csv`, `data/output/salesforce_writeback.csv`,
  `docs/data/accounts.json`, and updates only the count fields in `docs/data/content.json`
- `docs/data/content.json` — hand-edited copy (owner edits it; never overwrite wording)
- `docs/*.html` + `docs/assets/` — static site; preview with `python3 -m http.server 8000 -d docs`
- `docs/assets/lifecycle.js` — the 8 lifecycle steps + per-account sentences, shared by all pages
- Cross-page state is URL-only: `?account=<slug>&step=<1-8>` (helpers in `docs/assets/common.js`)
- `docs/data/jd_mapping.json` (JD keyword mapping, user-supplied wording — don't reword), `glossary.json` (ⓘ tooltips), `decisions.json` (Decision Log); `{placeholders}` in glossary/decisions are filled from accounts.json meta
- Wording: collaborative ("we could", "possibly we can"), never "I'd"; "pool of funds" not "headroom"
- Featured accounts (one per quadrant): Northwind Commerce, Contoso Media, Fabrikam Health, Tailspin Games
