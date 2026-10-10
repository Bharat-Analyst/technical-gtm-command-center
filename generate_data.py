"""
generate_data.py — creates the synthetic "CRM extract" that pipeline.py reads.

Think of this as a stand-in for a nightly export from Salesforce (Account,
Opportunity, Contract fields) joined with product usage telemetry. Output:
    data/raw/accounts.csv

Everything is synthetic and seeded (42) so every run produces identical data.
Company names are made up. One account, Northwind Commerce, is deliberately
planted with a specific profile because it is the story customer for the POC.
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
# 499 random accounts + 4 hand-planted featured accounts (one per quadrant) = 503.
N_RANDOM_ACCOUNTS = 499
# "Today" for the snapshot. Fixed (not the real date) so results never drift.
AS_OF_DATE = pd.Timestamp("2026-10-01")
OUT_PATH = Path(__file__).parent / "data" / "raw" / "accounts.csv"

rng = np.random.default_rng(SEED)

# --- Fictional company names: prefix + suffix combos ----------------------
PREFIXES = [
    "Acme", "Bluefin", "Cobalt", "Driftwood", "Ember", "Fernhill", "Granite",
    "Harbor", "Ironleaf", "Juniper", "Kestrel", "Lumen", "Maple", "Nimbus",
    "Orchard", "Pinecrest", "Quarry", "Redwood", "Saltmarsh", "Tidewater",
    "Upland", "Vantage", "Willow", "Yellowstone", "Zephyr", "Brightpath",
    "Copperline", "Duneview", "Evergreen", "Foxglove",
]
SUFFIXES = [
    "Retail", "Labs", "Health", "Logistics", "Media", "Finance", "Games",
    "Travel", "Foods", "Software", "Mobility", "Energy", "Insurance",
    "Analytics", "Apparel", "Studios", "Systems", "Networks", "Markets",
    "Learning",
]
INDUSTRIES = {
    "Retail": "Retail & eCommerce", "Apparel": "Retail & eCommerce",
    "Markets": "Retail & eCommerce", "Foods": "Retail & eCommerce",
    "Health": "Healthcare", "Finance": "Financial Services",
    "Insurance": "Financial Services", "Media": "Media & Gaming",
    "Games": "Media & Gaming", "Studios": "Media & Gaming",
}  # anything not listed → "Technology"

all_names = [f"{p} {s}" for p in PREFIXES for s in SUFFIXES]
names = list(rng.choice(all_names, size=N_RANDOM_ACCOUNTS, replace=False))

# --- Segment drives size: Enterprise commits are much bigger ---------------
segment = rng.choice(["Enterprise", "Mid-Market", "Commercial"],
                     size=N_RANDOM_ACCOUNTS, p=[0.2, 0.4, 0.4])
commit_median = {"Enterprise": 600_000, "Mid-Market": 150_000, "Commercial": 40_000}
dev_median = {"Enterprise": 120, "Mid-Market": 35, "Commercial": 10}
meetings_rate = {"Enterprise": 3.0, "Mid-Market": 1.5, "Commercial": 0.5}

n = N_RANDOM_ACCOUNTS
commit = np.array([rng.lognormal(np.log(commit_median[s]), 0.5) for s in segment])
commit = np.round(commit, -3)

# 12-month contracts that started 0–12 months ago.
days_into_contract = rng.integers(10, 360, size=n)
contract_start = AS_OF_DATE - pd.to_timedelta(days_into_contract, unit="D")
contract_end = contract_start + pd.DateOffset(years=1)

# Burn pace: 1.0 = consuming commit exactly on schedule. <1 = behind.
burn_pace = np.clip(rng.normal(1.0, 0.25, size=n), 0.2, 1.6)
elapsed_share = days_into_contract / 365
commit_consumed = np.round(commit * elapsed_share * burn_pace, -2)

# Usage telemetry.
usage_growth_90d = np.clip(rng.normal(8, 20, size=n), -50, 200).round(1)
usage_4wk_avg = np.round(commit / 52 * rng.uniform(0.6, 1.3, size=n), -1)
spike_ratio = np.clip(rng.lognormal(0, 0.22, size=n), 0.5, 3.0)
usage_last_7d = np.round(usage_4wk_avg * spike_ratio, -1)

active_devs = np.array([max(2, int(rng.lognormal(np.log(dev_median[s]), 0.6)))
                        for s in segment])
new_devs_30d = rng.poisson(active_devs * 0.05)

sa_meetings_90d = np.array([rng.poisson(meetings_rate[s]) for s in segment])

# About half of accounts have an open expansion opportunity.
has_pipeline = rng.random(n) < 0.5
open_pipeline = np.where(has_pipeline, np.round(commit * rng.uniform(0.1, 0.8, size=n), -3), 0)

accounts = pd.DataFrame({
    "account_name": names,
    "industry": [INDUSTRIES.get(nm.split()[-1], "Technology") for nm in names],
    "region": rng.choice(["AMER", "EMEA", "APAC", "LATAM"], size=n, p=[0.45, 0.3, 0.18, 0.07]),
    "segment": segment,
    "contract_start_date": contract_start.date,
    "contract_end_date": contract_end.date,
    "annual_commit_usd": commit,
    "commit_consumed_usd": commit_consumed,
    "open_pipeline_usd": open_pipeline,
    "usage_growth_90d_pct": usage_growth_90d,
    "usage_last_7d_units": usage_last_7d,
    "usage_4wk_avg_units": usage_4wk_avg,
    "active_developers": active_devs,
    "new_developers_30d": new_devs_30d,
    "sa_meetings_90d": sa_meetings_90d,
})

# --- Plant the four featured accounts (one per quadrant) -------------------
def contract(days_in: int) -> dict:
    """12-month contract that started `days_in` days before the snapshot."""
    start = AS_OF_DATE - pd.Timedelta(days=days_in)
    return {"contract_start_date": start.date(),
            "contract_end_date": (start + pd.DateOffset(years=1)).date()}


featured = [
    # Northwind Commerce → FDE Deep Engagement.
    # A big retailer whose developers are rapidly adopting the platform (usage
    # up, new developers arriving, SA team engaged) BUT whose large migration
    # stalled, so it is far behind on consuming its commit.
    # High potential + real risk = the ideal FDE deep-engagement case.
    {
        "account_name": "Northwind Commerce", "industry": "Retail & eCommerce",
        "region": "AMER", "segment": "Enterprise", **contract(220),
        "annual_commit_usd": 1_200_000, "commit_consumed_usd": 340_000,  # ~47% of expected pace
        "open_pipeline_usd": 450_000, "usage_growth_90d_pct": 62.0,
        "usage_last_7d_units": 31_000, "usage_4wk_avg_units": 24_000,
        "active_developers": 140, "new_developers_30d": 28, "sa_meetings_90d": 6,
    },
    # Contoso Media → Scaled SA Program.
    # A fast-growing mid-market streaming company: strong signals everywhere,
    # but a small contract. Worth helping, just not with a dedicated FDE —
    # one-to-many office hours and templates are the efficient motion.
    {
        "account_name": "Contoso Media", "industry": "Media & Gaming",
        "region": "EMEA", "segment": "Mid-Market", **contract(180),
        "annual_commit_usd": 120_000, "commit_consumed_usd": 71_000,  # ~120% of pace
        "open_pipeline_usd": 30_000, "usage_growth_90d_pct": 48.0,
        "usage_last_7d_units": 2_900, "usage_4wk_avg_units": 2_400,
        "active_developers": 40, "new_developers_30d": 12, "sa_meetings_90d": 3,
    },
    # Fabrikam Health → Strategic Bet.
    # A large healthcare commit with lots of unused spend and a big renewal
    # opportunity, but weak engagement signals today. High stakes, low
    # likelihood: a targeted exec + SA discovery play, not an FDE yet.
    {
        "account_name": "Fabrikam Health", "industry": "Healthcare",
        "region": "AMER", "segment": "Enterprise", **contract(150),
        "annual_commit_usd": 1_500_000, "commit_consumed_usd": 525_000,  # ~85% of pace
        "open_pipeline_usd": 300_000, "usage_growth_90d_pct": -4.0,
        "usage_last_7d_units": 27_000, "usage_4wk_avg_units": 28_500,
        "active_developers": 60, "new_developers_30d": 1, "sa_meetings_90d": 1,
    },
    # Tailspin Games → Digital.
    # A small studio, flat usage, no pipeline. Served well by docs, webinars
    # and community; SA time here would not move revenue.
    {
        "account_name": "Tailspin Games", "industry": "Media & Gaming",
        "region": "APAC", "segment": "Commercial", **contract(255),
        "annual_commit_usd": 30_000, "commit_consumed_usd": 20_000,  # ~95% of pace
        "open_pipeline_usd": 0, "usage_growth_90d_pct": 2.0,
        "usage_last_7d_units": 560, "usage_4wk_avg_units": 580,
        "active_developers": 6, "new_developers_30d": 0, "sa_meetings_90d": 0,
    },
]
accounts = pd.concat([pd.DataFrame(featured), accounts], ignore_index=True)

# Salesforce-style 18-char-ish Account Ids (prefix 001 = Account object).
accounts.insert(0, "account_id", [f"001NW{i:010d}" for i in range(1, len(accounts) + 1)])

OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
accounts.to_csv(OUT_PATH, index=False)
print(f"Wrote {len(accounts)} accounts to {OUT_PATH.relative_to(Path(__file__).parent)}")
