"""
pipeline.py — turns raw Salesforce + product usage extracts into one decision
per account: where SAs and FDEs spend their limited time.

Steps (mirrors "How this works"):
    1. Data comes in        read data/raw/*.csv
    2. Clean and combine    standardize, merge duplicates, roll up child accounts,
                            match usage and signups; one row per account (and per month)
    3. Score propensity     4 bucketed signals × weights → 0–100, with top reasons
    4. Size the prize       pool of funds, commit health, opportunity value
    5. Alert and prioritize 6 alerts, type of help, logged overrides, team capacity slots
    6–8. Engage / revenue / measure: program + PS routing, comparison group, exports
Last: validate.py recomputes everything independently and fails loudly on any mismatch.

Outputs:
    data/processed/account_month.csv       one row per account per month
    data/processed/account_scores.csv      one row per account, every field
    data/processed/unmatched_usage.csv     usage we couldn't match (logged, not dropped)
    data/output/salesforce_writeback.csv   fields pushed back to Salesforce
    docs/data/accounts.json                what every page reads
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

# =============================================================================
# ASSUMPTIONS — every judgment call lives here (documented on "How this works").
# =============================================================================
AS_OF_DATE = pd.Timestamp("2026-10-01")
SEED = 42
DAYS_PER_MONTH = 365 / 12

# Signal windows
USAGE_GROWTH_MONTHS = 3        # change in monthly spend over the last 3 months
NEW_BUILDERS_DAYS = 60         # people who started building recently
ENGAGEMENT_DAYS = 90           # meetings and calls
NEW_PRODUCT_DAYS = 60          # first use of a product

# Propensity score: each signal is bucketed to 0–100, then weighted.
# Buckets are (minimum, points), checked top-down; below the last minimum = 0.
USAGE_GROWTH_BUCKETS = [(0.40, 100), (0.25, 85), (0.10, 60), (0.0, 30)]   # falling = 0
NEW_BUILDERS_BUCKETS = [(15, 100), (5, 70), (1, 40)]                      # none = 0
ENGAGEMENT_BUCKETS = [(6, 100), (3, 60), (1, 30)]                         # none = 0
PRODUCT_BREADTH_BUCKETS = [(5, 100), (4, 80), (3, 60), (2, 40), (1, 20)]
WEIGHTS = {
    # Recent momentum is the strongest sign of near-term growth.
    "usage_growth": 0.35,
    # More people building today usually means more production workloads soon.
    "new_builders": 0.30,
    # A warm relationship makes our time convert faster.
    "engagement": 0.15,
    # Customers using several products are building real systems, not trials.
    "product_breadth": 0.20,
}
assert abs(sum(WEIGHTS.values()) - 1) < 1e-9

# Type of help cut-offs
SCORE_HIGH = 60
POOL_OF_FUNDS_HIGH = 250_000

# Alerts
COMMIT_AT_RISK_MAX_PACE = 0.70
COMMIT_AT_RISK_MIN_ELAPSED = 0.25   # On-track % is too noisy in the first quarter of a contract
# Renewal coming: big contracts enter procurement months ahead, so Enterprise gets a
# longer runway. One window for everyone would flag half of all accounts (180 days)
# or warn Enterprise teams too late (90 days).
RENEWAL_COMING_DAYS_ENTERPRISE = 180
RENEWAL_COMING_DAYS_OTHER = 90
BUILDER_SURGE_MIN = 15
USAGE_SPIKE_MIN = 0.50              # monthly spend up 50%+ in one month
USAGE_DROP_MAX = -0.30              # monthly spend down 30%+ over 3 months
ON_TRACK_GOOD = 0.90                # status bands next to On-track %
ON_TRACK_WARN = COMMIT_AT_RISK_MAX_PACE

# Alert catalogue shown on screen (name, action, owner, time to respond).
ALERTS = [
    {"name": "Commit at risk", "action": "Plan to move workloads to production; consider the Commit Burn Sprint",
     "owner": "SA", "respond_business_days": 5},
    {"name": "Renewal coming", "action": "Review usage and value with the customer before renewal talks",
     "owner": "Account team + SA", "respond_business_days": 10},
    {"name": "Builder surge", "action": "Reach out to help the new builders get to production",
     "owner": "SA", "respond_business_days": 5},
    {"name": "Usage spike", "action": "Check the setup can scale; look for expansion",
     "owner": "SA", "respond_business_days": 3},
    {"name": "New product", "action": "Share best practices for that product",
     "owner": "SA or scaled program", "respond_business_days": 10},
    {"name": "Usage drop", "action": "Health check: find out what changed",
     "owner": "Account team + SA", "respond_business_days": 5},
]
ALERT_NAMES = [a["name"] for a in ALERTS]

# Team capacity (per quarter)
N_SAS, SA_LOAD = 10, 3              # 3 dedicated accounts per SA at a time → 30 SA slots
N_FDES, FDE_LOAD = 4, 2             # 2 deep engagements per FDE at a time → 8 FDE slots

# Programs and PS
SPRINT_MIN_UNUSED = 250_000         # Commit Burn Sprint: Commit at risk + this much unused commit
HOLDOUT_SHARE = 0.20                # comparison group share of accounts that qualify for scaled help
PS_STARTER_BELOW, PS_STANDARD_BELOW = 200_000, 1_000_000   # tier by unused commit

# Type of help names and what each one means (shown on screen as-is).
DEEP, BET, SCALED, DIGITAL = "Deep engagement (SA + FDE)", "Strategic bet", "Scaled SA programs", "Digital / self-serve"
TYPES = {
    DEEP: {"who": "SA leads design and relationship; FDE builds with the customer's developers",
           "what": "Architecture plan, onsite, hands-on build to production", "goal": "First workload live, fast"},
    BET: {"who": "SA leads with the account team; FDE only if a real project appears",
          "what": "Discovery meetings or an onsite to find the first use case", "goal": "Create momentum"},
    SCALED: {"who": "SAs in group formats; no FDE",
             "what": "Office hours, workshops, reference architectures", "goal": "Keep momentum going at low cost"},
    DIGITAL: {"who": "No dedicated people",
              "what": "Docs, templates, product emails; alerts watch for change", "goal": "Grow on their own"},
}
QUADRANTS = {(True, True): DEEP, (False, True): BET, (True, False): SCALED, (False, False): DIGITAL}
FEATURED = {DEEP: "Northwind Commerce", BET: "Fabrikam Health", SCALED: "Contoso Media", DIGITAL: "Tailspin Games"}

# Industry names as typed in Salesforce → one standard name.
INDUSTRY_STANDARD = {
    "retail & ecommerce": "Retail & eCommerce", "retail and ecommerce": "Retail & eCommerce", "retail/ecommerce": "Retail & eCommerce",
    "healthcare": "Healthcare", "health care": "Healthcare",
    "financial services": "Financial Services", "finserv": "Financial Services",
    "media & gaming": "Media & Gaming", "media and gaming": "Media & Gaming",
    "technology": "Technology", "tech": "Technology",
}

ROOT = Path(__file__).parent
RAW, PROCESSED, OUTPUT = ROOT / "data" / "raw", ROOT / "data" / "processed", ROOT / "data" / "output"
SITE_JSON = ROOT / "docs" / "data" / "accounts.json"
CONTENT_JSON = ROOT / "docs" / "data" / "content.json"
OVERRIDES = RAW / "overrides.csv"


def half_up(x: float) -> int:
    """Round 80.5 → 81 (Python's round() would give 80)."""
    return int(np.floor(x + 0.5 + 1e-9))


def bucket(value: float, buckets: list) -> int:
    for minimum, points in buckets:
        if value >= minimum:
            return points
    return 0


# =============================================================================
# 1–2. DATA COMES IN, CLEAN AND COMBINE
# =============================================================================
def clean_and_combine() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    accounts = pd.read_csv(RAW / "accounts.csv", dtype=str, keep_default_na=False)
    contracts = pd.read_csv(RAW / "contracts.csv")
    opps = pd.read_csv(RAW / "opportunities.csv")
    activities = pd.read_csv(RAW / "activities.csv", parse_dates=["date"])
    usage = pd.read_csv(RAW / "usage_monthly.csv", dtype={"sf_account_id": str}, keep_default_na=False)
    signups = pd.read_csv(RAW / "signups.csv", parse_dates=["signup_date"])

    # Standardize industry names.
    raw_spellings = accounts["industry"].nunique()
    accounts["industry"] = accounts["industry"].str.lower().map(INDUSTRY_STANDARD)
    assert accounts["industry"].notna().all(), "unknown industry spelling — add it to INDUSTRY_STANDARD"

    # Every raw account id → the one company it belongs to:
    #  a) duplicate top-level records (same email domain) merge into the record holding the contract;
    #  b) child accounts roll up to their parent.
    to_company = {}
    children = accounts[accounts["parent_account_id"] != ""]
    top = accounts[accounts["parent_account_id"] == ""]
    has_contract = set(contracts["account_id"])
    for _, group in top.groupby("email_domain"):
        keep = sorted(group["account_id"], key=lambda i: (i not in has_contract, i))[0]
        for i in group["account_id"]:
            to_company[i] = keep
    for row in children.itertuples():
        to_company[row.account_id] = to_company[row.parent_account_id]

    companies = top[top["account_id"].isin(has_contract)].copy().reset_index(drop=True)
    kids = children.groupby("parent_account_id")["account_name"].apply(list)
    companies["child_accounts"] = companies["account_id"].map(lambda i: kids.get(i, []))
    dup_counts = top.groupby("email_domain").size() - 1
    companies["duplicates_merged"] = companies["email_domain"].map(dup_counts).astype(int)

    # Contract fields.
    c = contracts.set_index("account_id")
    for col in ["start_date", "end_date", "annual_commit_usd", "amount_used_usd"]:
        companies[col] = companies["account_id"].map(c[col])

    # Open pipeline = open (not closed) opportunities.
    open_opps = opps[~opps["is_closed"]].copy()
    open_opps["company"] = open_opps["account_id"].map(to_company)
    companies["open_pipeline_usd"] = companies["account_id"].map(open_opps.groupby("company")["amount_usd"].sum()).fillna(0)

    # Meetings and calls in the window, wherever they were logged (child, duplicate or parent).
    # "Last N days" includes day N.
    recent = activities[activities["date"] >= AS_OF_DATE - pd.Timedelta(days=ENGAGEMENT_DAYS)].copy()
    recent["company"] = recent["account_id"].map(to_company)
    companies["meetings_90d"] = companies["account_id"].map(recent.groupby("company").size()).fillna(0).astype(int)

    # Self-serve signups matched by company email domain.
    domain_to_company = {d: to_company[g["account_id"].iloc[0]] for d, g in top.groupby("email_domain")}
    signups["company"] = signups["email_domain"].map(domain_to_company)
    new = signups[(signups["signup_date"] >= AS_OF_DATE - pd.Timedelta(days=NEW_BUILDERS_DAYS)) & signups["company"].notna()]
    companies["new_builders_60d"] = companies["account_id"].map(new.groupby("company").size()).fillna(0).astype(int)

    # Usage: match billing rows to companies; log (don't drop) what can't be matched.
    usage["company"] = usage["sf_account_id"].map(to_company)
    unmatched = usage[usage["company"].isna()]
    PROCESSED.mkdir(parents=True, exist_ok=True)
    unmatched.drop(columns="company").to_csv(PROCESSED / "unmatched_usage.csv", index=False)
    matched = usage[usage["company"].notna()]
    bas = matched.groupby("company")["billing_account_id"].apply(lambda s: sorted(set(s)))
    companies["billing_accounts"] = companies["account_id"].map(lambda i: bas.get(i, []))

    # Ready-to-use monthly table: one row per account per month.
    account_month = (matched.groupby(["company", "month"])
                     .agg(spend_usd=("spend_usd", "sum"), products_used=("product", lambda s: sorted(set(s))))
                     .reset_index().rename(columns={"company": "account_id"}))
    account_month["spend_usd"] = account_month["spend_usd"].round(2)

    stats = {
        "raw_account_records": int(len(accounts)), "companies": int(len(companies)),
        "child_accounts_rolled_up": int(len(children)),
        "duplicate_records_merged": int(len(top) - len(companies)),
        "industry_spellings_standardized": int(raw_spellings),
        "billing_accounts_matched": int(matched["billing_account_id"].nunique()),
        "unmatched_usage_rows": int(len(unmatched)), "unmatched_usage_usd": round(float(unmatched["spend_usd"].sum()), 2),
        "signups_matched_60d": int(len(new)), "signups_unmatched": int(signups["company"].isna().sum()),
    }
    return companies, account_month, stats


def add_usage_signals(df: pd.DataFrame, account_month: pd.DataFrame) -> pd.DataFrame:
    months = sorted(account_month["month"].unique())
    last, prev, three_ago = months[-1], months[-2], months[-1 - USAGE_GROWTH_MONTHS]
    spend = account_month.pivot(index="account_id", columns="month", values="spend_usd")
    prods = account_month.set_index(["account_id", "month"])["products_used"]
    df["spend_last_month"] = df["account_id"].map(spend[last]).round(0)
    df["usage_growth_3m"] = df["account_id"].map(spend[last] / spend[three_ago] - 1).round(4)
    df["spend_mom_change"] = df["account_id"].map(spend[last] / spend[prev] - 1).round(4)
    df["products_used"] = df["account_id"].map(lambda a: prods.get((a, last), []))
    df["product_count"] = df["products_used"].str.len()
    # New product = first used within the last NEW_PRODUCT_DAYS (≈ the last 2 months),
    # and not present at the start of the usage history.
    recent_months = set(months[-round(NEW_PRODUCT_DAYS / 30):])
    first_month = account_month.explode("products_used").groupby(["account_id", "products_used"])["month"].min()
    new_prod = first_month[first_month.isin(recent_months) & (first_month > months[0])].reset_index()
    df["new_product"] = df["account_id"].map(new_prod.groupby("account_id")["products_used"].first())
    return df


# =============================================================================
# 3. PROPENSITY SCORE
# =============================================================================
def score(df: pd.DataFrame) -> pd.DataFrame:
    df["score_usage_growth"] = df["usage_growth_3m"].map(lambda g: bucket(g, USAGE_GROWTH_BUCKETS))
    df["score_new_builders"] = df["new_builders_60d"].map(lambda n: bucket(n, NEW_BUILDERS_BUCKETS))
    df["score_engagement"] = df["meetings_90d"].map(lambda n: bucket(n, ENGAGEMENT_BUCKETS))
    df["score_product_breadth"] = df["product_count"].map(lambda n: bucket(n, PRODUCT_BREADTH_BUCKETS))
    for s in WEIGHTS:
        df[f"points_{s}"] = (WEIGHTS[s] * df[f"score_{s}"]).round(2)
    df["propensity_score"] = sum(df[f"points_{s}"] for s in WEIGHTS).map(half_up)
    df["top_reasons"] = df.apply(top_reasons, axis=1)
    return df


def describe(signal: str, r: pd.Series) -> str:
    if signal == "usage_growth":
        g = r["usage_growth_3m"]
        return f"Usage {'up' if g >= 0 else 'down'} {abs(g):.0%} in 3 months"
    if signal == "new_builders":
        n = r["new_builders_60d"]
        return f"{n} new builder{'' if n == 1 else 's'} in {NEW_BUILDERS_DAYS} days" if n else f"No new builders in {NEW_BUILDERS_DAYS} days"
    if signal == "engagement":
        n = r["meetings_90d"]
        return f"{n} meeting{'' if n == 1 else 's'} and calls in {ENGAGEMENT_DAYS} days" if n else f"No meetings or calls in {ENGAGEMENT_DAYS} days"
    n = r["product_count"]
    return f"Uses {n} developer platform product{'' if n == 1 else 's'}"


def top_reasons(r: pd.Series) -> list:
    """The three signals that added the most points (ties: higher weight first)."""
    ranked = sorted(WEIGHTS, key=lambda s: (r[f"points_{s}"], WEIGHTS[s]), reverse=True)
    return [describe(s, r) for s in ranked[:3]]


# =============================================================================
# 4. POOL OF FUNDS, COMMIT HEALTH, OPPORTUNITY VALUE
# =============================================================================
def size_the_prize(df: pd.DataFrame) -> pd.DataFrame:
    start, end = pd.to_datetime(df["start_date"]), pd.to_datetime(df["end_date"])
    term_days = (end - start).dt.days
    days_elapsed = (AS_OF_DATE - start).dt.days.clip(lower=0)
    elapsed = (days_elapsed / term_days).clip(0, 1)
    df["days_to_renewal"] = (end - AS_OF_DATE).dt.days
    df = df.rename(columns={"amount_used_usd": "commit_consumed_usd"})
    used_share = df["commit_consumed_usd"] / df["annual_commit_usd"]
    # Compute from unrounded shares, round once at the end.
    df["burn_pace"] = (used_share / elapsed).round(4)                                           # On-track %
    df["contract_elapsed_share"] = elapsed.round(4)
    df["commit_used_share"] = used_share.round(4)
    months_elapsed = (days_elapsed / DAYS_PER_MONTH).clip(lower=1)
    months_left = df["days_to_renewal"].clip(lower=0) / DAYS_PER_MONTH
    df["burn_rate_monthly"] = (df["commit_consumed_usd"] / months_elapsed).round(0)              # Monthly spend
    df["expected_consumed_to_date"] = (df["annual_commit_usd"] * elapsed).round(0)
    df["behind_pace_amount"] = (df["expected_consumed_to_date"] - df["commit_consumed_usd"]).clip(lower=0).round(0)
    df["unused_commit"] = (df["annual_commit_usd"] - df["commit_consumed_usd"]).clip(lower=0)
    df["required_monthly_burn"] = np.where(months_left > 0, df["unused_commit"] / months_left.where(months_left > 0, 1),
                                           df["unused_commit"]).round(0)
    df["projected_year_use"] = (df["burn_rate_monthly"] * 12).round(0)                            # at today's pace
    df["pool_of_funds"] = df["unused_commit"] + df["open_pipeline_usd"]
    df["expected_value_usd"] = (df["propensity_score"] / 100 * df["pool_of_funds"]).round(0)    # Opportunity value
    return df


# =============================================================================
# 5. ALERTS, TYPE OF HELP, OVERRIDES, TEAM CAPACITY
# =============================================================================
def add_alerts(df: pd.DataFrame) -> pd.DataFrame:
    rules = {
        "Commit at risk": (df["burn_pace"] < COMMIT_AT_RISK_MAX_PACE) & (df["contract_elapsed_share"] >= COMMIT_AT_RISK_MIN_ELAPSED),
        "Renewal coming": (df["days_to_renewal"] >= 0) & (df["days_to_renewal"] <= np.where(
            df["segment"] == "Enterprise", RENEWAL_COMING_DAYS_ENTERPRISE, RENEWAL_COMING_DAYS_OTHER)),
        "Builder surge": df["new_builders_60d"] >= BUILDER_SURGE_MIN,
        "Usage spike": df["spend_mom_change"] >= USAGE_SPIKE_MIN,
        "New product": df["new_product"].notna(),
        "Usage drop": df["usage_growth_3m"] <= USAGE_DROP_MAX,
    }
    assert list(rules) == ALERT_NAMES
    df["flags"] = [[n for n, m in rules.items() if m.iloc[i]] for i in range(len(df))]
    df["has_alert"] = df["flags"].str.len() > 0
    return df


def add_type_of_help(df: pd.DataFrame) -> pd.DataFrame:
    high_score = df["propensity_score"] >= SCORE_HIGH
    high_pool = df["pool_of_funds"] >= POOL_OF_FUNDS_HIGH
    df["quadrant"] = [QUADRANTS[(s, p)] for s, p in zip(high_score, high_pool)]
    df["model_quadrant"] = df["quadrant"]
    df["override_reason"] = None
    # Logged overrides: a leader can move an account, but must record why.
    if OVERRIDES.exists():
        for o in pd.read_csv(OVERRIDES).itertuples():
            assert o.override_type_of_help in TYPES, f"unknown type of help: {o.override_type_of_help}"
            assert isinstance(o.reason, str) and o.reason.strip(), f"override for {o.account_id} has no reason"
            hit = df["account_id"] == o.account_id
            assert hit.any(), f"override for unknown account {o.account_id}"
            df.loc[hit, "quadrant"] = o.override_type_of_help
            df.loc[hit, "override_reason"] = f"{o.reason} ({o.owner}, {o.date})"
    return df


def assign_capacity(df: pd.DataFrame) -> pd.DataFrame:
    """
    Fill slots in order (the browser repeats this when the sliders move):
      1. Within each type, accounts with alerts first, then by opportunity value.
      2. FDE slots go to the top Deep engagement accounts; each also uses an SA slot.
         The #1 account by opportunity value always gets an SA slot.
      3. Remaining SA slots go to Deep engagement and Strategic bet accounts: each type keeps its
         own order, and the next slot goes to whichever type's next account has more opportunity value.
      4. Everyone else gets scaled programs or self-serve.
    """
    by_value = df.sort_values(["expected_value_usd", "account_id"], ascending=[False, True])["account_id"]
    df["priority_rank"] = df["account_id"].map({a: i + 1 for i, a in enumerate(by_value)})
    order = df.sort_values(["has_alert", "expected_value_usd", "account_id"], ascending=[False, False, True])
    fde_slots, sa_slots = N_FDES * FDE_LOAD, N_SAS * SA_LOAD
    deep_queue = list(order.loc[order["quadrant"] == DEEP, "account_id"])
    bet_queue = list(order.loc[order["quadrant"] == BET, "account_id"])
    fde_ids = deep_queue[:fde_slots]
    # Remaining SA slots: alerts only reorder accounts *within* a type, so the two
    # queues are merged by taking whichever next account has the higher opportunity value.
    ev = df.set_index("account_id")["expected_value_usd"]
    deep_rest, sa_ids = deep_queue[fde_slots:], list(fde_ids)
    # The #1 account by opportunity value always gets an SA slot, alerts or not:
    # leaving the biggest opportunity uncovered is a trade-off no leader would accept.
    ranked = df[df["quadrant"].isin([DEEP, BET])].sort_values(["expected_value_usd", "account_id"], ascending=[False, True])
    top = ranked["account_id"].iloc[0] if len(ranked) else None
    if top is not None and top not in sa_ids and len(sa_ids) < sa_slots:
        sa_ids.append(top)
        deep_rest = [a for a in deep_rest if a != top]
        bet_queue = [a for a in bet_queue if a != top]
    while len(sa_ids) < sa_slots and (deep_rest or bet_queue):
        take_deep = bet_queue == [] or (deep_rest and ev[deep_rest[0]] >= ev[bet_queue[0]])
        sa_ids.append((deep_rest if take_deep else bet_queue).pop(0))
    df["fde_slot"] = df["account_id"].isin(fde_ids)
    df["sa_slot"] = df["account_id"].isin(sa_ids)
    df["in_capacity"] = df["sa_slot"]
    df["coverage"] = np.select([df["fde_slot"], df["sa_slot"]], ["SA + FDE", "SA"], default="Outside team capacity")
    return df


# =============================================================================
# 6–8. ENGAGE, REVENUE, MEASURE: help plan, program, PS tier, comparison group
# =============================================================================
def help_plan(q: str, fde: bool, sa: bool) -> str:
    if q == DEEP:
        if fde:
            return "SA leads design and relationship; FDE builds with the customer's developers to production"
        return "SA leads now; FDE joins when a slot opens" if sa else "Waiting for team capacity; scaled programs meanwhile"
    if q == BET:
        return "SA-led discovery with the account team; FDE only if a real project appears" if sa \
            else "Account team leads; SA discovery when capacity frees up"
    return TYPES[q]["what"]


def ps_tier(r: pd.Series):
    if not (("Commit at risk" in r["flags"]) or r["quadrant"] == BET):
        return None
    u = r["unused_commit"]
    return "Starter" if u < PS_STARTER_BELOW else "Standard" if u < PS_STANDARD_BELOW else "Advanced"


def route(df: pd.DataFrame) -> pd.DataFrame:
    df["motion"] = [help_plan(q, f, s) for q, f, s in zip(df["quadrant"], df["fde_slot"], df["sa_slot"])]
    eligible = df["flags"].map(lambda f: "Commit at risk" in f) & (df["unused_commit"] >= SPRINT_MIN_UNUSED)
    df["sprint_eligible"] = eligible
    df["program"] = np.where(eligible, np.where(df["fde_slot"], "Commit Burn Sprint (SA + FDE)", "Commit Burn Sprint (SA-led)"), None)
    # Comparison group: from accounts that qualify for scaled help (Scaled SA programs,
    # or the sprint without a dedicated slot), a random share gets normal service only.
    # Accounts holding a dedicated SA or FDE slot are never held back.
    qualifies = (df["quadrant"] == SCALED) | (eligible & ~df["sa_slot"])
    df["qualifies_for_scaled_help"] = qualifies
    candidates = sorted(df.loc[qualifies, "account_id"])
    n_hold = round(len(candidates) * HOLDOUT_SHARE)
    held = set(np.random.default_rng(SEED).choice(candidates, size=n_hold, replace=False)) if n_hold else set()
    df["holdout"] = df["account_id"].isin(held)
    df.loc[df["holdout"], "program"] = "Comparison group (normal service only)"
    df["ps_recommended_tier"] = df.apply(ps_tier, axis=1)
    df["slug"] = df["account_name"].str.lower().str.replace(r"[^a-z0-9]+", "-", regex=True).str.strip("-")
    assert df["slug"].is_unique
    return df


# =============================================================================
# EXPORT
# =============================================================================
SITE_COLS = [
    "account_id", "slug", "account_name", "segment", "industry", "region", "owner",
    "annual_commit_usd", "commit_consumed_usd", "commit_used_share", "contract_elapsed_share", "days_to_renewal",
    "open_pipeline_usd", "unused_commit", "pool_of_funds", "burn_pace", "burn_rate_monthly",
    "expected_consumed_to_date", "behind_pace_amount", "required_monthly_burn", "projected_year_use",
    "spend_last_month", "usage_growth_3m", "spend_mom_change", "products_used", "product_count", "new_product",
    "new_builders_60d", "meetings_90d", "child_accounts", "billing_accounts", "duplicates_merged",
    "score_usage_growth", "score_new_builders", "score_engagement", "score_product_breadth",
    "points_usage_growth", "points_new_builders", "points_engagement", "points_product_breadth",
    "propensity_score", "top_reasons", "expected_value_usd", "flags", "quadrant", "model_quadrant", "override_reason",
    "priority_rank", "fde_slot", "sa_slot", "in_capacity", "coverage", "motion", "sprint_eligible", "program",
    "qualifies_for_scaled_help", "holdout", "ps_recommended_tier",
]


def export(df: pd.DataFrame, account_month: pd.DataFrame, stats: dict) -> None:
    for p in (PROCESSED, OUTPUT, SITE_JSON.parent):
        p.mkdir(parents=True, exist_ok=True)
    df = df.sort_values("priority_rank").reset_index(drop=True)

    am = account_month.copy()
    am["products_used"] = am["products_used"].str.join("; ")
    am.to_csv(PROCESSED / "account_month.csv", index=False)
    flat = df.copy()
    for col in ["top_reasons", "flags", "products_used", "child_accounts", "billing_accounts"]:
        flat[col] = flat[col].str.join("; ")
    flat.to_csv(PROCESSED / "account_scores.csv", index=False)

    pd.DataFrame({
        "Id": df["account_id"],
        "GTM_Propensity_Score__c": df["propensity_score"],
        "GTM_Top_Reasons__c": df["top_reasons"].str.join(" | "),
        "GTM_Pool_Of_Funds__c": df["pool_of_funds"].round(0),
        "GTM_Opportunity_Value__c": df["expected_value_usd"],
        "GTM_Priority_Rank__c": df["priority_rank"],
        "GTM_Type_Of_Help__c": df["quadrant"],
        "GTM_Alerts__c": df["flags"].str.join(";"),
        "GTM_Coverage__c": df["coverage"],
        "GTM_Help_Plan__c": df["motion"],
        "GTM_Program__c": df["program"],
        "GTM_PS_Recommendation__c": df["ps_recommended_tier"],
        "GTM_Comparison_Group__c": df["holdout"],
        "GTM_Override_Reason__c": df["override_reason"],
        "GTM_Scored_Date__c": AS_OF_DATE.date().isoformat(),
    }).to_csv(OUTPUT / "salesforce_writeback.csv", index=False)

    meta = {
        "as_of_date": AS_OF_DATE.date().isoformat(),
        "weights": WEIGHTS,
        "buckets": {"usage_growth": USAGE_GROWTH_BUCKETS, "new_builders": NEW_BUILDERS_BUCKETS,
                    "engagement": ENGAGEMENT_BUCKETS, "product_breadth": PRODUCT_BREADTH_BUCKETS},
        "signal_windows": {"usage_growth_months": USAGE_GROWTH_MONTHS, "new_builders_days": NEW_BUILDERS_DAYS,
                           "engagement_days": ENGAGEMENT_DAYS, "new_product_days": NEW_PRODUCT_DAYS},
        "thresholds": {
            "score_high": SCORE_HIGH, "pool_of_funds_high": POOL_OF_FUNDS_HIGH,
            "commit_at_risk_max_pace": COMMIT_AT_RISK_MAX_PACE, "commit_at_risk_min_elapsed": COMMIT_AT_RISK_MIN_ELAPSED,
            "renewal_coming_days_enterprise": RENEWAL_COMING_DAYS_ENTERPRISE,
            "renewal_coming_days_other": RENEWAL_COMING_DAYS_OTHER, "builder_surge_min": BUILDER_SURGE_MIN,
            "usage_spike_min": USAGE_SPIKE_MIN, "usage_drop_max": USAGE_DROP_MAX,
            "on_track_good": ON_TRACK_GOOD, "on_track_warn": ON_TRACK_WARN,
            "sprint_min_unused": SPRINT_MIN_UNUSED,
            "ps_starter_below": PS_STARTER_BELOW, "ps_standard_below": PS_STANDARD_BELOW,
        },
        "capacity": {"sas": N_SAS, "sa_load": SA_LOAD, "fdes": N_FDES, "fde_load": FDE_LOAD,
                     "sa_slots": N_SAS * SA_LOAD, "fde_slots": N_FDES * FDE_LOAD},
        "alerts": ALERTS,
        "types": [{"name": n, **TYPES[n]} for n in [DEEP, BET, SCALED, DIGITAL]],
        "quadrants": [DEEP, BET, SCALED, DIGITAL],
        "featured": [FEATURED[q] for q in [DEEP, SCALED, BET, DIGITAL]],
        "holdout_share": HOLDOUT_SHARE,
        "cleaning": stats,
    }
    records = json.loads(df[SITE_COLS].to_json(orient="records"))
    SITE_JSON.write_text(json.dumps({"meta": meta, "accounts": records}, indent=1))

    # content.json is hand-edited; only its data-driven counts are updated here.
    if CONTENT_JSON.exists():
        content = json.loads(CONTENT_JSON.read_text())
        prog = content.setdefault("program", {})
        el = df[df["sprint_eligible"]]
        prog.update({"eligible_accounts": int(len(el)), "eligible_outside_capacity": int((~el["sa_slot"]).sum()),
                     "eligible_unused_commit": int(el["unused_commit"].sum())})
        CONTENT_JSON.write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n")


def main() -> None:
    df, account_month, stats = clean_and_combine()
    df = add_usage_signals(df, account_month)
    df = score(df)
    df = size_the_prize(df)
    df = add_alerts(df)
    df = add_type_of_help(df)
    df = assign_capacity(df)
    df = route(df)
    export(df, account_month, stats)

    print(f"Scored {len(df)} accounts as of {AS_OF_DATE.date()}")
    print("Clean and combine:", stats)
    print("\nType of help:\n" + df["quadrant"].value_counts().to_string())
    print("\nCoverage:\n" + df["coverage"].value_counts().to_string())
    print("\nAlerts:", {a: int(df["flags"].map(lambda f: a in f).sum()) for a in ALERT_NAMES})
    print("Programs:", df["program"].value_counts().to_dict())

    # Story checks: the four featured accounts must match the methodology page.
    expect = {
        "Northwind Commerce": (81, DEEP, 1_310_000, ["Commit at risk", "Renewal coming", "Builder surge"]),
        "Contoso Media": (77, SCALED, 70_000, None),
        "Fabrikam Health": (32, BET, 1_100_000, None),
        "Tailspin Games": (28, DIGITAL, 15_000, None),
    }
    print("\nFeatured accounts:")
    for name, (s, q, pool, alerts) in expect.items():
        a = df[df["account_name"] == name].iloc[0]
        print(f"  {name:20s} score {a.propensity_score:3d} | pool ${a.pool_of_funds:>10,.0f} | OV ${a.expected_value_usd:>10,.0f} "
              f"| rank #{a.priority_rank:<3d} | {a.quadrant} | {a.coverage} | alerts: {', '.join(a['flags']) or '-'}")
        assert a.propensity_score == s, f"{name}: score {a.propensity_score}, expected {s}"
        assert a.quadrant == q, f"{name}: {a.quadrant}, expected {q}"
        assert a.pool_of_funds == pool, f"{name}: pool {a.pool_of_funds}, expected {pool}"
        if alerts is not None:
            assert a["flags"] == alerts, f"{name}: alerts {a['flags']}, expected {alerts}"
    assert df.loc[df.account_name == "Northwind Commerce", "fde_slot"].item(), "Northwind should hold an FDE slot"
    print("  ✓ Story check passed")

    import validate
    validate.run()


if __name__ == "__main__":
    main()
