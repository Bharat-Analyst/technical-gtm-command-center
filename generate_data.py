"""
generate_data.py — creates the raw extracts that pipeline.py reads.

Stands in for scheduled exports from Salesforce and product usage. Like real
extracts, they are messy on purpose: duplicate account records, child
accounts, inconsistent industry names, usage that can't be matched, and
self-serve signups that must be matched by company email domain. The
pipeline's "Clean and combine" step fixes all of this.

Outputs (data/raw/):
    accounts.csv        Salesforce Account   (incl. duplicates and child accounts)
    contracts.csv       Salesforce Contract  (annual commit, dates, amount used)
    opportunities.csv   Salesforce Opportunity (open and closed deals)
    activities.csv      Salesforce Activity  (meetings and calls)
    usage_monthly.csv   Product usage: monthly spend by billing account and product
    signups.csv         Self-serve signups with company email domain

Seeded (42) so every run produces identical files. Company names are made up.
Four featured accounts (one per type of help) are planted with exact profiles.
"""

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_RANDOM_ACCOUNTS = 499            # + 4 featured accounts = 503 companies
AS_OF_DATE = pd.Timestamp("2026-10-01")   # snapshot date, fixed so results never drift
MONTHS = pd.period_range("2026-04", "2026-09", freq="M")  # last 6 full months of usage
DAYS_PER_MONTH = 365 / 12
OUT = Path(__file__).parent / "data" / "raw"

rng = np.random.default_rng(SEED)

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
    "Analytics", "Apparel", "Studios", "Systems", "Networks", "Markets", "Learning",
]
INDUSTRY_OF_SUFFIX = {
    "Retail": "Retail & eCommerce", "Apparel": "Retail & eCommerce", "Markets": "Retail & eCommerce",
    "Foods": "Retail & eCommerce", "Health": "Healthcare", "Finance": "Financial Services",
    "Insurance": "Financial Services", "Media": "Media & Gaming", "Games": "Media & Gaming",
    "Studios": "Media & Gaming",
}  # anything else → "Technology"
# Real CRMs hold the same industry typed several ways; cleaning standardizes them.
MESSY_INDUSTRY = {
    "Retail & eCommerce": ["Retail & eCommerce", "retail & ecommerce", "Retail and eCommerce", "Retail/eCommerce"],
    "Healthcare": ["Healthcare", "Health Care", "healthcare"],
    "Financial Services": ["Financial Services", "FinServ", "financial services"],
    "Media & Gaming": ["Media & Gaming", "Media and Gaming", "media & gaming"],
    "Technology": ["Technology", "Tech", "technology"],
}
PRODUCTS = ["Workers", "KV", "R2", "Pages", "D1", "Durable Objects", "Queues", "Workers AI"]
OWNERS = ["Avery Chen", "Jordan Patel", "Sam Rivera", "Morgan Lee", "Taylor Brooks", "Riley Kim"]
OPEN_STAGES = ["Discovery", "Evaluation", "Proposal", "Negotiation"]

slug = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())


def account_id(i: int) -> str:
    return f"001NW{i:010d}"


# ---------------------------------------------------------------------------
# Company-level profiles (one per real company). Featured accounts first.
# ---------------------------------------------------------------------------
def featured_profiles() -> list[dict]:
    """
    Exact profiles so the walkthrough lands where the methodology says:
      Northwind  → Deep engagement (SA + FDE), score 81, 3 alerts
      Contoso    → Scaled SA programs, score 77, $70K pool of funds
      Fabrikam   → Strategic bet, score 32, $1.1M pool of funds
      Tailspin   → Digital / self-serve, score 28, $15K pool of funds
    """
    return [
        dict(name="Northwind Commerce", segment="Enterprise", industry="Retail & eCommerce", region="AMER",
             days_in=220, commit=1_200_000, used=340_000, open_opps=[300_000, 150_000],
             growth=0.38, products=["Workers", "R2", "KV"], new_product=None,
             builders_60d=28, meetings_90d=4, child="Northwind Commerce Canada"),
        dict(name="Contoso Media", segment="Mid-Market", industry="Media & Gaming", region="EMEA",
             days_in=180, commit=120_000, used=80_000, open_opps=[30_000],
             growth=0.45, products=["Workers", "KV", "Pages"], new_product=None,
             builders_60d=9, meetings_90d=4, child=None),
        dict(name="Fabrikam Health", segment="Enterprise", industry="Healthcare", region="AMER",
             days_in=165, commit=1_500_000, used=700_000, open_opps=[200_000, 100_000],
             growth=-0.04, products=["Workers", "KV", "R2", "D1", "Queues"], new_product=None,
             builders_60d=2, meetings_90d=0, child=None),
        dict(name="Tailspin Games", segment="Commercial", industry="Media & Gaming", region="APAC",
             days_in=255, commit=30_000, used=15_000, open_opps=[],
             growth=-0.06, products=["Workers", "KV", "R2", "Pages"], new_product=None,
             builders_60d=2, meetings_90d=0, child=None),
    ]


def random_profiles(n: int) -> list[dict]:
    names = rng.choice([f"{p} {s}" for p in PREFIXES for s in SUFFIXES], size=n, replace=False)
    commit_median = {"Enterprise": 600_000, "Mid-Market": 150_000, "Commercial": 40_000}
    builders_rate = {"Enterprise": 6.0, "Mid-Market": 3.0, "Commercial": 1.0}
    meetings_rate = {"Enterprise": 3.0, "Mid-Market": 1.5, "Commercial": 0.5}
    max_products = {"Enterprise": 6, "Mid-Market": 4, "Commercial": 3}
    out = []
    for name in names:
        seg = rng.choice(["Enterprise", "Mid-Market", "Commercial"], p=[0.2, 0.4, 0.4])
        commit = round(rng.lognormal(np.log(commit_median[seg]), 0.5), -3)
        days_in = int(rng.integers(10, 360))
        pace = float(np.clip(rng.normal(1.0, 0.25), 0.2, 1.6))
        used = round(commit * days_in / 365 * pace, -2)
        n_opps = int(rng.choice([0, 1, 2, 3], p=[0.5, 0.3, 0.15, 0.05]))
        opps = [round(commit * rng.uniform(0.05, 0.4), -3) for _ in range(n_opps)]
        n_prod = int(rng.integers(1, max_products[seg] + 1))
        products = ["Workers"] + list(rng.choice(PRODUCTS[1:], size=n_prod - 1, replace=False))
        new_product = products[-1] if (n_prod > 1 and rng.random() < 0.08) else None
        # Rare builder surges (a new team arriving) on top of the normal trickle.
        builders = int(rng.poisson(builders_rate[seg]) + (rng.poisson(18) if rng.random() < 0.04 else 0))
        out.append(dict(
            name=str(name), segment=str(seg), industry=INDUSTRY_OF_SUFFIX.get(name.split()[-1], "Technology"),
            region=str(rng.choice(["AMER", "EMEA", "APAC", "LATAM"], p=[0.45, 0.3, 0.18, 0.07])),
            days_in=days_in, commit=commit, used=used, open_opps=opps,
            growth=float(np.clip(rng.normal(0.08, 0.2), -0.6, 1.2)),
            spike=rng.random() < 0.04, products=products, new_product=new_product,
            builders_60d=builders, meetings_90d=int(rng.poisson(meetings_rate[seg])), child=None,
        ))
    return out


profiles = featured_profiles() + random_profiles(N_RANDOM_ACCOUNTS)

# A few enterprise companies also have a regional child account in Salesforce.
for p in rng.choice([p for p in profiles[4:] if p["segment"] == "Enterprise"], size=11, replace=False):
    p["child"] = f"{p['name']} {rng.choice(['EMEA', 'APAC', 'Canada', 'UK'])}"

# ---------------------------------------------------------------------------
# Build the raw tables
# ---------------------------------------------------------------------------
accounts, contracts, opps, activities, usage, signups = [], [], [], [], [], []
next_id = 1
ba_counter = 1

for p in profiles:
    aid = account_id(next_id); next_id += 1
    domain = f"{slug(p['name'])}.com"
    accounts.append(dict(account_id=aid, account_name=p["name"], segment=p["segment"],
                         industry=str(rng.choice(MESSY_INDUSTRY[p["industry"]])), region=p["region"],
                         owner=str(rng.choice(OWNERS)), parent_account_id="", email_domain=domain))
    child_id = None
    if p["child"]:
        child_id = account_id(next_id); next_id += 1
        accounts.append(dict(account_id=child_id, account_name=p["child"], segment=p["segment"],
                             industry=str(rng.choice(MESSY_INDUSTRY[p["industry"]])), region=p["region"],
                             owner=accounts[-1]["owner"], parent_account_id=aid, email_domain=domain))

    # Contract: commit lives on the parent account.
    start = AS_OF_DATE - pd.Timedelta(days=p["days_in"])
    contracts.append(dict(contract_id=f"800NW{len(contracts) + 1:010d}", account_id=aid,
                          start_date=start.date(), end_date=(start + pd.DateOffset(years=1)).date(),
                          annual_commit_usd=p["commit"], amount_used_usd=p["used"]))

    # Opportunities: open deals count toward the pool of funds; closed ones don't.
    for amt in p["open_opps"]:
        opps.append(dict(opportunity_id=f"006NW{len(opps) + 1:010d}", account_id=aid,
                         stage=str(rng.choice(OPEN_STAGES)), amount_usd=amt,
                         product=str(rng.choice(PRODUCTS)), close_date=(AS_OF_DATE + pd.Timedelta(days=int(rng.integers(20, 200)))).date(),
                         is_closed=False))
    for _ in range(int(rng.poisson(0.6))):
        opps.append(dict(opportunity_id=f"006NW{len(opps) + 1:010d}", account_id=aid,
                         stage=str(rng.choice(["Closed Won", "Closed Lost"])), amount_usd=round(p["commit"] * rng.uniform(0.05, 0.3), -3),
                         product=str(rng.choice(PRODUCTS)), close_date=(AS_OF_DATE - pd.Timedelta(days=int(rng.integers(30, 400)))).date(),
                         is_closed=True))

    # Activities: meetings/calls in the last 90 days, plus older ones that must be ignored.
    logged_on = [aid] + ([child_id] if child_id else [])
    for _ in range(p["meetings_90d"]):
        activities.append(dict(activity_id=f"00TNW{len(activities) + 1:010d}", account_id=str(rng.choice(logged_on)),
                               type=str(rng.choice(["Meeting", "Call"])), date=(AS_OF_DATE - pd.Timedelta(days=int(rng.integers(1, 90)))).date()))
    for _ in range(int(rng.poisson(2))):
        activities.append(dict(activity_id=f"00TNW{len(activities) + 1:010d}", account_id=aid,
                               type=str(rng.choice(["Meeting", "Call"])), date=(AS_OF_DATE - pd.Timedelta(days=int(rng.integers(91, 300)))).date()))

    # Usage: 6 months of monthly spend. Average ≈ the contract's monthly spend so
    # far; the trend matches the growth target (last month vs 3 months before).
    months_elapsed = max(p["days_in"] / DAYS_PER_MONTH, 1)
    avg = p["used"] / months_elapsed
    r = (1 + p["growth"]) ** (1 / 3)
    shape = np.array([r ** t for t in range(-5, 1)])
    series = avg * shape / shape.mean()
    if p.get("spike"):
        series[-1] *= 1.6  # something new launched last month
    weights = rng.dirichlet(np.ones(len(p["products"])) * 2)
    bas = [f"BA-{ba_counter:05d}"]; ba_counter += 1
    if child_id:
        bas.append(f"BA-{ba_counter:05d}"); ba_counter += 1
    for m_idx, month in enumerate(MONTHS):
        for prod, w in zip(p["products"], weights):
            # A newly adopted product has no spend before its first month (Aug).
            if prod == p["new_product"] and month < pd.Period("2026-08", "M"):
                continue
            total = series[m_idx] * w
            # Child account's billing account carries 30% of usage; roll-up adds it back.
            split = [(bas[0], aid, 0.7), (bas[1], child_id, 0.3)] if child_id else [(bas[0], aid, 1.0)]
            for ba, sf_id, share in split:
                usage.append(dict(billing_account_id=ba, sf_account_id=sf_id, month=str(month),
                                  product=prod, spend_usd=round(total * share, 2)))

    # Self-serve signups: last-60-day builders plus older ones, matched by email domain.
    for _ in range(p["builders_60d"]):
        signups.append(dict(signup_id=f"SU-{len(signups) + 1:06d}", email_domain=domain,
                            signup_date=(AS_OF_DATE - pd.Timedelta(days=int(rng.integers(1, 61)))).date()))
    for _ in range(int(rng.poisson(p["builders_60d"] + 1))):
        signups.append(dict(signup_id=f"SU-{len(signups) + 1:06d}", email_domain=domain,
                            signup_date=(AS_OF_DATE - pd.Timedelta(days=int(rng.integers(61, 365)))).date()))

# Duplicate account records (same company typed twice), no contract of their own.
for p in rng.choice(profiles[4:], size=6, replace=False):
    original = next(a for a in accounts if a["account_name"] == p["name"])
    dup_id = account_id(next_id); next_id += 1
    accounts.append(dict(original, account_id=dup_id, account_name=f"{p['name']} Inc.", parent_account_id=""))
    activities.append(dict(activity_id=f"00TNW{len(activities) + 1:010d}", account_id=dup_id, type="Meeting",
                           date=(AS_OF_DATE - pd.Timedelta(days=int(rng.integers(1, 90)))).date()))

# Usage that can't be matched to any Salesforce account (must be logged, not dropped).
for i in range(6):
    for month in MONTHS:
        usage.append(dict(billing_account_id=f"BA-{ba_counter:05d}", sf_account_id="", month=str(month),
                          product=str(rng.choice(PRODUCTS)), spend_usd=round(rng.uniform(50, 900), 2)))
    ba_counter += 1

# Personal-email signups can't be tied to a company.
for _ in range(300):
    signups.append(dict(signup_id=f"SU-{len(signups) + 1:06d}", email_domain=str(rng.choice(["gmail.com", "outlook.com", "proton.me"])),
                        signup_date=(AS_OF_DATE - pd.Timedelta(days=int(rng.integers(1, 365)))).date()))

OUT.mkdir(parents=True, exist_ok=True)
for name, rows in [("accounts", accounts), ("contracts", contracts), ("opportunities", opps),
                   ("activities", activities), ("usage_monthly", usage), ("signups", signups)]:
    pd.DataFrame(rows).to_csv(OUT / f"{name}.csv", index=False)
    print(f"Wrote {len(rows):>6} rows to data/raw/{name}.csv")
