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
- **No banner, footer or disclaimer labels on the site** (owner decision 2026-10-10:
  no "synthetic", "illustrative", "simulated" or "not affiliated" labels; the owner states this themselves).

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
- `generate_data.py` → `data/raw/*.csv`: Salesforce-style extracts (accounts incl. duplicates/child accounts,
  contracts, opportunities, activities), monthly usage by product, self-serve signups. Seed 42; 4 featured accounts planted.
- `data/raw/overrides.csv` — hand-written type-of-help overrides; each needs reason, owner, date.
- `pipeline.py` → clean and combine, bucket propensity score, pool of funds, six alerts, type of help, slot-based team capacity,
  programs, comparison group; writes `data/processed/*`, `data/output/salesforce_writeback.csv`, `docs/data/accounts.json`,
  and only the count fields in `docs/data/content.json`. Ends by running `validate.py`, which must pass.
- `docs/data/content.json` (hand-edited copy), `glossary.json` (ⓘ), `decisions.json` (decision log on How this works),
  `faq.json` (inline "?" answers), `jd_mapping.json` (JD keywords — keep exact). `{placeholders}` are filled from accounts.json.
- Pages: index (Lifecycle), prioritization, engagement, programs, executive, how-this-works. Preview: `python3 -m http.server 8000 -d docs`.
- Shared JS: `docs/assets/common.js` (one money formatter `GTM.usd`, tooltips, capacity fill mirroring the pipeline), `lifecycle.js`.
- Cross-page state is URL-only: `?account=<slug>&step=<1-8>`.

## Model (source of truth: the "How this works" text the owner supplied)
- Propensity weights 35/30/15/20 with bucket scores; cut-offs score 60+, pool of funds $250K+.
- Types of help: Deep engagement (SA + FDE), Strategic bet, Scaled SA programs, Digital / self-serve.
- Team capacity: 10 SAs × 3, 4 FDEs × 2. Six alerts. On-track bands 90% / 70%.

## Wording rules (owner decisions 2026-10-10)
- Plain on-screen labels; keep "Propensity score" and "Pool of funds" exactly; never "headroom"; never "I'd".
- Collaborative phrasing ("we could", "possibly we can"). Built-with-AI credit stays at the top.
