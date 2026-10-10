# Technical GTM Command Center

Solutions Architects and Forward Deployed Engineers are scarce, and their time often goes to whoever asks loudest rather than where it moves revenue most.
This project is a working command center that scores every account on Propensity score and Pool of funds, raises alerts on risk and opportunity, decides the right type of help for each account, and packages repeatable programs and services.
It shows how technical GTM team capacity can be run as a ranked, measurable investment that leadership can see and defend, with an interactive lifecycle walkthrough that takes any account from CRM data to measured impact.

**Live demo:** _coming soon_ — `https://<github-username>.github.io/technical-gtm-command-center/`

![Lifecycle walkthrough: account picker, color-coded lifecycle steps, metric cards and the step detail for Northwind Commerce](docs/assets/screenshot.png)

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

- **Propensity score (0–100):** how likely a customer is to grow soon if we invest technical time. Usage growth, new builders, SA meetings and On-track % are each turned into a percentile against all accounts, then weighted. The three biggest contributors become **top reasons** in plain English.
- **Pool of funds** = unused commit + open pipeline: money available to unlock.
- **Opportunity value** = Propensity score ÷ 100 × Pool of funds: which customers are worth the most time.
- **On-track %** = share of commit used ÷ share of the contract year passed, shown with a status (On track / Slightly behind / Behind). **Monthly spend**, **Needed monthly spend** and **Behind by** show the gap in dollars.
- **Alerts:** Commit at Risk, Days to renewal, Usage Spike, New builders.
- **Type of help:** Deep engagement (SA + FDE), Scaled SA programs, Strategic Bet, Digital / self-serve, set by Propensity score and Pool of funds. People can override it, but only with a logged reason (`data/raw/overrides.csv`).
- **Team capacity:** the top accounts by Opportunity value get dedicated help.

Every weight, threshold and cut-off is an assumption recorded in the site's **Decision Log** (decision / why / possibly we can), with the values defined once at the top of [`pipeline.py`](pipeline.py).

**Featured accounts**, one per type of help: Northwind Commerce (Deep engagement), Contoso Media (Scaled SA programs), Fabrikam Health (Strategic Bet), Tailspin Games (Digital / self-serve). `pipeline.py` fails if any of them lands elsewhere.

## How it's built

```
generate_data.py      → data/raw/accounts.csv                 sample Salesforce + usage extract (seed 42)
data/raw/overrides.csv                                         human overrides of type of help, each with a reason
pipeline.py           → data/processed/account_scores.csv      scored table
                      → data/output/salesforce_writeback.csv   fields pushed back to Salesforce (GTM_*__c)
                      → docs/data/accounts.json               read by every page
validate.py           (last pipeline step) recomputes every number from raw data and fails loudly on any mismatch
docs/data/*.json      content, glossary (ⓘ tooltips), decisions (Decision Log), faq (inline "?" items), jd_mapping
docs/                 static site (HTML/CSS/JS + Plotly.js), hosted on GitHub Pages
```

Python 3.11 + pandas. No database, no build tools.

### Pages

Lifecycle · Prioritization · Engagement · Programs & PS · Executive · Decision Log.
Every metric, column and term has an ⓘ from one shared glossary; every chart, slider and table has a "How to read this" caption; "Why:" links point to the Decision Log; and 2–3 common questions sit next to the chart or table they explain.

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

## How this was built

Built with AI: I designed the approach, made the GTM decisions and reviewed every output, and used Claude Code (Anthropic's AI coding assistant) to write the code, generate the data pipeline and build the site, step by step with a commit after each step.

## Next steps with real Salesforce data

1. **Replace the scorecard with a model** trained on which accounts actually grew after help, and keep the top reasons.
2. **Real usage data** from the warehouse, refreshed on a schedule, with On-track % adjusted for seasonal industries.
3. **Run the comparison group for real** and report Impact and ROI once outcomes arrive.
4. **Close the loop in Salesforce:** load the write-back fields and feed outcomes and overrides back into the weights.
