# Technical GTM Command Center

**Designed and built by Bharat with AI.** I defined the problem, the scoring model and every GTM decision, and reviewed every number; Claude Code (Anthropic's AI coding assistant) wrote the code alongside me, step by step, with a commit after each step.

Solutions Architects and Forward Deployed Engineers are scarce, and their time often goes to whoever asks loudest rather than where it moves revenue most.
This project is a working command center that scores every account on Propensity score and Pool of funds, raises alerts on risk and opportunity, decides the right type of help for each account, and packages repeatable programs and services.
It shows how technical GTM team capacity can be run as a ranked, measurable investment that leadership can see and defend, with an interactive lifecycle walkthrough that takes any account from CRM data to measured impact.

**Live demo:** https://bharat-analyst.github.io/technical-gtm-command-center/

![Lifecycle walkthrough for Northwind Commerce: propensity score 81, $1.31M pool of funds, $1.06M opportunity value, Deep engagement (SA + FDE)](docs/assets/screenshot.png)

## Job responsibility → page

| Responsibility | What we built | Page |
|---|---|---|
| Prioritization & visibility | Propensity score × Pool of funds matrix, alerts, team capacity slider, ranked table with top reasons | Prioritization |
| Strategic customer engagement | Engagement tracker: goal, owner, status, blocker, next step | Engagement |
| Technical onsites | Onsite plan from intake to measurement | Engagement |
| Technical programs | "Commit Burn Sprint" SA program, triggered by the Commit at Risk alert, with a handoff plan | Programs & PS |
| Professional Services packaging | "Workers Migration Accelerator" tiers + business case | Programs & PS |
| Leadership visibility / ROI | Money in play, coverage, engagement health, comparison-group ROI plan | Executive |

## How the score works

- **Propensity score (0–100):** how likely an account is to grow in the next 90 days. Four signals are bucketed to 0–100 and weighted: usage growth over 3 months (35%), new builders in 60 days (30%), meetings and calls in 90 days (15%), product breadth (20%). The three signals that add the most points become **top reasons**.
- **Pool of funds** = unused commit + open pipeline, always shown with both parts.
- **Opportunity value** = propensity score ÷ 100 × pool of funds; used to rank accounts.
- **Commit health:** Monthly spend, On-track % (On track 90%+ / Slightly behind 70–89% / Behind), Behind by, Needed monthly spend.
- **Six alerts:** Commit at risk, Renewal coming, Builder surge, Usage spike, New product, Usage drop, each with an owner, an action and a time to respond.
- **Type of help:** Deep engagement (SA + FDE), Strategic bet, Scaled SA programs, Digital / self-serve, from propensity score 60+ and pool of funds $250K+. Overrides need a logged reason (`data/raw/overrides.csv`).
- **Team capacity:** 10 SAs × 3 accounts = 30 SA slots; 4 FDEs × 2 = 8 FDE slots, filled in a published order.
- **Comparison group:** a random share of qualifying accounts gets normal service only, so impact is measured fairly.

Every weight, threshold and cut-off is an assumption, defined once at the top of [`pipeline.py`](pipeline.py) and explained on the site's **How this works** page (with a decision log at the bottom).

**Featured accounts**, one per type of help: Northwind Commerce (Deep engagement), Contoso Media (Scaled SA programs), Fabrikam Health (Strategic bet), Tailspin Games (Digital / self-serve). `pipeline.py` fails if any of them lands elsewhere.

## How it's built

```
generate_data.py      → data/raw/*.csv                        Salesforce-style extracts (accounts, contracts, opportunities,
                                                               activities), monthly usage and signups (seed 42), messy on purpose
data/raw/overrides.csv                                         human overrides of type of help, each with a reason
pipeline.py           → data/processed/account_month.csv       clean and combine: one row per account per month
                      → data/processed/account_scores.csv      scored table
                      → data/output/salesforce_writeback.csv   fields pushed back to Salesforce (GTM_*__c)
                      → docs/data/accounts.json               read by every page
validate.py           (last pipeline step) recomputes every number from raw data and fails loudly on any mismatch
content/how_this_works.md   the written method (source of truth for the How this works page)
docs/data/*.json      content, glossary (ⓘ tooltips), decisions (decision log), faq (inline "?" answers), jd_mapping
docs/                 static site (HTML/CSS/JS + Plotly.js), hosted on GitHub Pages
```

Python 3.11 + pandas. No database, no build tools.

### Pages

Lifecycle · Prioritization · Engagement · Programs & PS · Executive · How this works.
Every metric, column and term has an ⓘ from one shared glossary; every chart, slider and table has a "How to read this" caption; "Why:" links point to the matching section of How this works; and 2–3 common questions sit next to the chart or table they explain.

### How pages share state

The selected account and lifecycle step live in the URL, e.g. `prioritization.html?account=contoso-media&step=3#selected`. No cookies or browser storage, so any view can be bookmarked or shared. Every page reads `account` on load, highlights it, and carries it through the nav; `step` adds a "Back to lifecycle step N" link.

### Run it

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python generate_data.py   # creates data/raw/accounts.csv
.venv/bin/python pipeline.py        # scores, exports, validates, prints the Northwind check table
python3 -m http.server 8000 -d docs # then open http://localhost:8000
```

## Next steps with real Salesforce data

1. **Replace the scorecard with a model** trained on which accounts actually grew after help, and keep the top reasons.
2. **Real usage data** from the warehouse, refreshed on a schedule, with On-track % adjusted for seasonal industries.
3. **Run the comparison group for real** and report Impact and ROI once outcomes arrive.
4. **Close the loop in Salesforce:** load the write-back fields and feed outcomes and overrides back into the weights.
