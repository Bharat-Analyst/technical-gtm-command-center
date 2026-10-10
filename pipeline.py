"""
pipeline.py — scores every account and decides where SA / FDE time goes.

Flow (mirrors warehouse layers):
    data/raw/accounts.csv                  CRM + telemetry extract (input)
    data/processed/account_scores.csv      scored "mart" table, every column
    data/output/salesforce_writeback.csv   only the fields we'd push to Salesforce
    docs/data/accounts.json                what the website reads

Steps:
    1. Propensity score (0–100) from a weighted scorecard + top 3 reasons
    2. Pool of funds and Expected Value
    3. Flags: Commit at Risk, Renewal Window, Usage Spike, New Developers
    4. Quadrant (who should own the account: FDE, SA program, etc.)
    5. Rank by Expected Value; the top N fit current SA/FDE capacity
    6. Routing: motion, program, recommended PS tier
    7. Export
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd

# =============================================================================
# BUSINESS ASSUMPTIONS — every judgment call lives here so it can be debated.
# =============================================================================

# Snapshot date. Fixed so outputs are reproducible (matches generate_data.py).
AS_OF_DATE = pd.Timestamp("2026-10-01")

# Propensity scorecard weights (must sum to 1.0).
# "Propensity" = how likely this account is to expand if we invest technical time.
WEIGHTS = {
    # Usage growth is the strongest signal: workloads already moving onto the
    # platform are the cheapest to accelerate.
    "usage_growth": 0.35,
    # New developers arriving = new teams/projects starting. Early technical
    # help shapes architecture before choices get locked in.
    "new_developers": 0.25,
    # Existing SA engagement means a warm relationship and known champions,
    # so our time converts faster.
    "engagement": 0.20,
    # Commit burn pace: customers consuming ahead of schedule tend to expand
    # at renewal. Weighted lowest because under-burn is handled by its own flag.
    "commit_burn": 0.20,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1"

# Signal look-back windows (they match how the telemetry extract defines its columns).
USAGE_GROWTH_WINDOW_DAYS = 90      # one quarter: smooths weekly noise but still reflects today
ENGAGEMENT_WINDOW_DAYS = 90        # same quarter, so SA meetings line up with usage
NEW_DEVELOPERS_WINDOW_DAYS = 30    # new teams show up fast; a month catches them early

# Flag thresholds.
COMMIT_AT_RISK_MIN_ELAPSED = 0.25  # too early in the contract to judge before 25% elapsed
COMMIT_AT_RISK_MAX_PACE = 0.70     # consuming <70% of expected pace → large unused commit at renewal
RENEWAL_WINDOW_DAYS = 120          # ~1 quarter + prep time: when renewal decisions get made
USAGE_SPIKE_RATIO = 1.5            # last 7 days ≥ 1.5× the 4-week average = something new launched
# On-track status bands shown next to On-track % (burn pace). The lower band
# matches the Commit at Risk line so the label and the alert never disagree.
ON_TRACK_GOOD = 0.90               # 90%+ = On track: small gaps close on their own
ON_TRACK_WARN = COMMIT_AT_RISK_MAX_PACE  # 70–89% = Slightly behind; below 70% = Behind
USAGE_SPIKE_RECENT_DAYS = 7        # (these two windows match the telemetry columns)
USAGE_SPIKE_BASELINE_DAYS = 28
NEW_DEVELOPERS_MIN = 10            # ≥10 new developers in 30 days = a new team, not noise

# Quadrant cut-offs.
SCORE_HIGH = 60                    # roughly the top third of accounts by propensity
POOL_OF_FUNDS_HIGH = 300_000       # pool of funds big enough to justify FDE-level effort

# How many accounts current SA/FDE headcount can actively cover.
CAPACITY_TOP_N = 30

# Professional Services tier by unconsumed commit: the bigger the stalled
# spend, the bigger the migration it takes to recover it.
PS_ASSESS_BELOW = 200_000          # small gap → 2-week assessment is enough
PS_MIGRATE_BELOW = 1_000_000       # mid gap → migrate one production workload
                                   # ≥ $1M → multi-workload "Scale" tier

# Holdout: share of Commit Burn Sprint accounts deliberately NOT enrolled, so we
# can compare outcomes and credit only the incremental lift as ROI.
HOLDOUT_SHARE = 0.20
SEED = 42                          # same seed as the data, so the holdout is reproducible

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw" / "accounts.csv"
# Human overrides of the type of help. Every override must carry a reason, an
# owner and a date, and is written back to Salesforce next to the score.
OVERRIDES = ROOT / "data" / "raw" / "overrides.csv"
PROCESSED = ROOT / "data" / "processed" / "account_scores.csv"
WRITEBACK = ROOT / "data" / "output" / "salesforce_writeback.csv"
SITE_JSON = ROOT / "docs" / "data" / "accounts.json"
CONTENT_JSON = ROOT / "docs" / "data" / "content.json"

# One showcase account per quadrant, used by the lifecycle walkthrough.
# "Type of help" names (shown on screen as-is).
DEEP = "Deep engagement (SA + FDE)"   # likely to grow AND lots at stake → SA designs, FDE builds
SCALED = "Scaled SA programs"          # likely to grow, smaller $ → SA group formats, no FDE
BET = "Strategic Bet"                  # big $ but weak signals → SA-led discovery
DIGITAL = "Digital / self-serve"       # neither → no SA/FDE time

FEATURED = {
    DEEP: "Northwind Commerce",
    SCALED: "Contoso Media",
    BET: "Fabrikam Health",
    DIGITAL: "Tailspin Games",
}

QUADRANTS = {
    (True, True): DEEP,
    (True, False): SCALED,
    (False, True): BET,
    (False, False): DIGITAL,
}


# =============================================================================
# 1. PROPENSITY SCORE
# =============================================================================
def add_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Turn raw CRM/telemetry columns into the business measures we score on."""
    start = pd.to_datetime(df["contract_start_date"])
    end = pd.to_datetime(df["contract_end_date"])
    term_days = (end - start).dt.days

    df["contract_elapsed_share"] = ((AS_OF_DATE - start).dt.days / term_days).clip(0, 1)
    df["days_to_renewal"] = (end - AS_OF_DATE).dt.days
    df["commit_consumed_share"] = df["commit_consumed_usd"] / df["annual_commit_usd"]
    # Burn pace: 1.0 = on schedule to use exactly the commit; 0.5 = half the expected rate.
    df["burn_pace"] = df["commit_consumed_share"] / df["contract_elapsed_share"]
    df["usage_spike_ratio"] = df["usage_last_7d_units"] / df["usage_4wk_avg_units"]
    return df


def score_accounts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Each signal is converted to a percentile (0–1) versus all other accounts,
    so "1.0" means "best in the book". Percentiles keep one extreme account
    from distorting the scale and are easy to explain ("top 5%").
    Score = weighted sum of percentiles × 100.
    """
    signals = {
        "usage_growth": df["usage_growth_90d_pct"],
        "new_developers": df["new_developers_30d"],
        "engagement": df["sa_meetings_90d"],
        "commit_burn": df["burn_pace"].clip(upper=1.5),  # beyond 1.5× pace adds no extra signal
    }
    for name, values in signals.items():
        df[f"pctl_{name}"] = values.rank(pct=True)
        df[f"contrib_{name}"] = WEIGHTS[name] * df[f"pctl_{name}"] * 100

    df["propensity_score"] = sum(df[f"contrib_{n}"] for n in WEIGHTS).round(0).astype(int)
    df["top_reasons"] = df.apply(top_reasons, axis=1)
    return df


def describe_signal(name: str, row: pd.Series) -> str:
    """Plain-English sentence for one signal, with its real value."""
    # Above the median say "top X%"; below it say "bottom X%". ("Top 54%" for
    # a weak signal reads as praise and would confuse a reader.)
    pctl = row[f"pctl_{name}"]
    if pctl >= 0.5:
        rank_txt = f"top {max(1, round((1 - pctl) * 100))}% of accounts"
    else:
        rank_txt = f"bottom {max(1, round(pctl * 100))}% of accounts"
    if name == "usage_growth":
        return f"Usage {row['usage_growth_90d_pct']:+.0f}% over the last 90 days ({rank_txt})"
    if name == "new_developers":
        n = row["new_developers_30d"]
        return f"{n} new builder{'' if n == 1 else 's'} in the last 30 days ({rank_txt})"
    if name == "engagement":
        n = row["sa_meetings_90d"]
        return f"{n} SA meeting{'' if n == 1 else 's'} in the last 90 days ({rank_txt})"
    if name == "commit_burn":
        return f"On-track % is {row['burn_pace']:.0%} ({rank_txt})"
    raise ValueError(name)


def top_reasons(row: pd.Series) -> list[str]:
    """The 3 signals that contributed the most points to this account's score."""
    ranked = sorted(WEIGHTS, key=lambda n: row[f"contrib_{n}"], reverse=True)
    return [describe_signal(n, row) for n in ranked[:3]]


# =============================================================================
# 2. POOL OF FUNDS & EXPECTED VALUE
# =============================================================================
DAYS_PER_MONTH = 365 / 12


def add_value(df: pd.DataFrame) -> pd.DataFrame:
    # Unconsumed commit: money the customer already agreed to spend but hasn't.
    # Helping them use it protects the renewal. Can't go below zero.
    df["unused_commit"] = (df["annual_commit_usd"] - df["commit_consumed_usd"]).clip(lower=0)
    # Pool of funds = money available to unlock: unused commit + open deals.
    df["pool_of_funds"] = df["unused_commit"] + df["open_pipeline_usd"]

    # Burn measures. Burn RATE is dollars per month; burn PACE compares usage
    # with the calendar (1.0 = on schedule to use exactly the commit).
    days_elapsed = df["contract_elapsed_share"] * (pd.to_datetime(df["contract_end_date"]) - pd.to_datetime(df["contract_start_date"])).dt.days
    months_elapsed = days_elapsed / DAYS_PER_MONTH
    months_remaining = df["days_to_renewal"].clip(lower=0) / DAYS_PER_MONTH
    df["burn_rate_monthly"] = (df["commit_consumed_usd"] / months_elapsed).round(0)
    # What a straight-line customer would have used by today.
    df["expected_consumed_to_date"] = (df["annual_commit_usd"] * df["contract_elapsed_share"]).round(0)
    df["behind_pace_amount"] = (df["expected_consumed_to_date"] - df["commit_consumed_usd"]).clip(lower=0).round(0)
    # Monthly spend needed from today to use the full commit by renewal.
    df["required_monthly_burn"] = np.where(months_remaining > 0, df["unused_commit"] / months_remaining, df["unused_commit"]).round(0)
    # Expected Value = pool of funds weighted by how likely we are to realize it.
    df["expected_value_usd"] = (df["propensity_score"] / 100 * df["pool_of_funds"]).round(0)
    return df


# Alert names (shown on screen as-is), in display order.
ALERTS = ["Commit at Risk", "Days to renewal", "Usage Spike", "New builders"]


# =============================================================================
# 3. FLAGS
# =============================================================================
def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    rules = {
        "Commit at Risk": (df["contract_elapsed_share"] >= COMMIT_AT_RISK_MIN_ELAPSED)
                          & (df["burn_pace"] < COMMIT_AT_RISK_MAX_PACE),
        "Days to renewal": df["days_to_renewal"].between(0, RENEWAL_WINDOW_DAYS),
        "Usage Spike": df["usage_spike_ratio"] >= USAGE_SPIKE_RATIO,
        "New builders": df["new_developers_30d"] >= NEW_DEVELOPERS_MIN,
    }
    assert list(rules) == ALERTS, "alert rules and ALERTS (shown on screen) must match"
    for flag, mask in rules.items():
        df[f"flag_{flag.lower().replace(' ', '_')}"] = mask
    df["flags"] = [[f for f, m in rules.items() if m.iloc[i]] for i in range(len(df))]
    return df


# =============================================================================
# 4. QUADRANT
# =============================================================================
def add_quadrant(df: pd.DataFrame) -> pd.DataFrame:
    # Value axis uses pool of funds (not Expected Value) so the two axes stay
    # independent: EV already contains the score.
    high_score = df["propensity_score"] >= SCORE_HIGH
    high_value = df["pool_of_funds"] >= POOL_OF_FUNDS_HIGH
    df["quadrant"] = [QUADRANTS[(s, v)] for s, v in zip(high_score, high_value)]
    df["model_quadrant"] = df["quadrant"]  # what the scorecard said, kept for review
    df["override_reason"] = None

    # Apply logged human overrides. The model is a starting point, not the last
    # word; logging the reason lets us learn where the scorecard is wrong.
    if OVERRIDES.exists():
        for o in pd.read_csv(OVERRIDES).itertuples():
            assert o.override_type_of_help in QUADRANTS.values(), f"unknown type of help: {o.override_type_of_help}"
            assert isinstance(o.reason, str) and o.reason.strip(), f"override for {o.account_id} has no reason"
            hit = df["account_id"] == o.account_id
            assert hit.any(), f"override for unknown account {o.account_id}"
            df.loc[hit, "quadrant"] = o.override_type_of_help
            df.loc[hit, "override_reason"] = f"{o.reason} ({o.owner}, {o.date})"
    return df


# =============================================================================
# 5. RANK & CAPACITY
# =============================================================================
def add_rank(df: pd.DataFrame) -> pd.DataFrame:
    # Ties broken by account_id so the order is stable run to run.
    df = df.sort_values(["expected_value_usd", "account_id"], ascending=[False, True]).reset_index(drop=True)
    df["priority_rank"] = np.arange(1, len(df) + 1)
    df["in_capacity"] = df["priority_rank"] <= CAPACITY_TOP_N
    return df


# =============================================================================
# 6. ROUTING — which motion, program and services offer each account gets
# =============================================================================
def motion_for(quadrant: str, in_capacity: bool) -> str:
    """Engagement motion. Capacity only matters for the two high-touch motions."""
    if quadrant == DEEP:
        return ("SA leads design and the relationship; FDE builds with the customer's developers until the first production workload"
                if in_capacity else "Waitlist for deep engagement; Scaled SA programs meanwhile")
    if quadrant == BET:
        return ("SA-led discovery with the account team; FDE only if a real project appears"
                if in_capacity else "Account team leads; SA discovery on request")
    if quadrant == SCALED:
        return "SA office hours, workshops and reference architectures (no FDE)"
    return "Docs, templates and alerts (no SA/FDE time)"


def ps_tier_for(row: pd.Series) -> str | None:
    """Target buyers: Commit at Risk accounts first, then Strategic Bets."""
    if not (row["flag_commit_at_risk"] or row["quadrant"] == BET):
        return None
    gap = row["unused_commit"]
    if gap < PS_ASSESS_BELOW:
        return "Assess"
    return "Migrate" if gap < PS_MIGRATE_BELOW else "Scale"


def add_routing(df: pd.DataFrame) -> pd.DataFrame:
    df["motion"] = [motion_for(q, c) for q, c in zip(df["quadrant"], df["in_capacity"])]
    # Commit Burn Sprint covers every Commit at Risk account. Ones inside
    # capacity get the same recovery work led directly by their FDE/SA.
    df["program"] = np.select(
        [df["flag_commit_at_risk"] & df["in_capacity"], df["flag_commit_at_risk"]],
        ["FDE-led catch-up plan", "Commit Burn Sprint"], default=None)
    df["ps_recommended_tier"] = df.apply(ps_tier_for, axis=1)

    # Randomly hold out a share of Sprint accounts. Random (not hand-picked) so
    # the two groups are alike, and the difference in outcomes is the program's effect.
    # FDE-covered accounts are never held out: we don't withhold dedicated help.
    sprint_ids = sorted(df.loc[df["program"] == "Commit Burn Sprint", "account_id"])
    n_holdout = round(len(sprint_ids) * HOLDOUT_SHARE)
    holdout_ids = set(np.random.default_rng(SEED).choice(sprint_ids, size=n_holdout, replace=False))
    df["holdout"] = df["account_id"].isin(holdout_ids)
    df.loc[df["holdout"], "program"] = "Comparison group (measured, not enrolled)"
    # URL-friendly id for links between pages, e.g. ?account=northwind-commerce
    df["slug"] = df["account_name"].str.lower().str.replace(r"[^a-z0-9]+", "-", regex=True).str.strip("-")
    assert df["slug"].is_unique, "Account slugs must be unique"
    return df


# =============================================================================
# 7. EXPORT
# =============================================================================
def export(df: pd.DataFrame) -> None:
    for p in (PROCESSED, WRITEBACK, SITE_JSON):
        p.parent.mkdir(parents=True, exist_ok=True)

    # Full mart table (lists joined so it stays a flat CSV).
    mart = df.copy()
    mart["flags"] = mart["flags"].str.join("; ")
    mart["top_reasons"] = mart["top_reasons"].str.join(" | ")
    mart.to_csv(PROCESSED, index=False)

    # Salesforce write-back: Account Id + custom fields (the __c suffix is
    # Salesforce's convention for custom fields). Multi-select picklists use ";".
    writeback = pd.DataFrame({
        "Id": df["account_id"],
        "GTM_Propensity_Score__c": df["propensity_score"],
        "GTM_Top_Reasons__c": df["top_reasons"].str.join(" | "),
        "GTM_Pool_Of_Funds__c": df["pool_of_funds"].round(0),
        "GTM_Expected_Value__c": df["expected_value_usd"],
        "GTM_Priority_Rank__c": df["priority_rank"],
        "GTM_Quadrant__c": df["quadrant"],
        "GTM_Flags__c": df["flags"].str.join(";"),
        "GTM_In_Capacity__c": df["in_capacity"],
        "GTM_Motion__c": df["motion"],
        "GTM_Program__c": df["program"],
        "GTM_PS_Recommendation__c": df["ps_recommended_tier"],
        "GTM_Holdout__c": df["holdout"],
        "GTM_Override_Reason__c": df["override_reason"],
        "GTM_Scored_Date__c": AS_OF_DATE.date().isoformat(),
    })
    writeback.to_csv(WRITEBACK, index=False)

    # Website JSON: compact, rounded, only what the pages display.
    site_cols = [
        "account_id", "slug", "account_name", "industry", "region", "segment",
        "propensity_score", "top_reasons", "pool_of_funds", "unused_commit",
        "burn_rate_monthly", "expected_consumed_to_date", "behind_pace_amount", "required_monthly_burn",
        "open_pipeline_usd", "expected_value_usd", "flags", "quadrant",
        "priority_rank", "in_capacity", "annual_commit_usd", "commit_consumed_usd",
        "burn_pace", "contract_elapsed_share", "days_to_renewal",
        "usage_growth_90d_pct", "usage_spike_ratio", "active_developers",
        "new_developers_30d", "sa_meetings_90d", "contract_end_date",
        "motion", "program", "ps_recommended_tier", "holdout", "model_quadrant", "override_reason",
    ]
    records = df[site_cols].round({"burn_pace": 2, "contract_elapsed_share": 2, "usage_spike_ratio": 2,
                                   "pool_of_funds": 0, "unused_commit": 0})
    payload = {
        "meta": {
            "as_of_date": AS_OF_DATE.date().isoformat(),
            "weights": WEIGHTS,
            "thresholds": {
                "score_high": SCORE_HIGH, "pool_of_funds_high": POOL_OF_FUNDS_HIGH,
                "capacity_top_n": CAPACITY_TOP_N,
                "commit_at_risk_max_pace": COMMIT_AT_RISK_MAX_PACE,
                "commit_at_risk_min_elapsed": COMMIT_AT_RISK_MIN_ELAPSED,
                "on_track_good": ON_TRACK_GOOD, "on_track_warn": ON_TRACK_WARN,
                "usage_spike_recent_days": USAGE_SPIKE_RECENT_DAYS,
                "usage_spike_baseline_days": USAGE_SPIKE_BASELINE_DAYS,
                "renewal_window_days": RENEWAL_WINDOW_DAYS,
                "usage_spike_ratio": USAGE_SPIKE_RATIO,
                "new_developers_min": NEW_DEVELOPERS_MIN,
                "ps_assess_below": PS_ASSESS_BELOW, "ps_migrate_below": PS_MIGRATE_BELOW,
            },
            "featured": [FEATURED[q] for q in QUADRANTS.values()],
            # Type-of-help names in fixed order: high/high, high/low, low/high, low/low.
            "quadrants": list(QUADRANTS.values()),
            "alerts": ALERTS,
            "signal_windows_days": {
                "usage_growth": USAGE_GROWTH_WINDOW_DAYS,
                "engagement": ENGAGEMENT_WINDOW_DAYS,
                "new_developers": NEW_DEVELOPERS_WINDOW_DAYS,
            },
            "holdout_share": HOLDOUT_SHARE,
        },
        "accounts": json.loads(records.to_json(orient="records")),
    }
    SITE_JSON.write_text(json.dumps(payload, indent=1))

    update_content_counts(df)


def update_content_counts(df: pd.DataFrame) -> None:
    """
    content.json is hand-edited copy. Only touch the data-driven numbers in it
    so manual edits to the wording are never overwritten.
    """
    if not CONTENT_JSON.exists():
        return
    content = json.loads(CONTENT_JSON.read_text())
    at_risk = df["flag_commit_at_risk"]
    program = content.setdefault("program", {})
    program["eligible_accounts"] = int(at_risk.sum())
    # Accounts flagged but outside top-N capacity: the ones only a scaled program reaches.
    program["eligible_outside_capacity"] = int((at_risk & ~df["in_capacity"]).sum())
    program["eligible_unused_commit"] = int(df.loc[at_risk, "unused_commit"].sum())
    program.pop("eligible_unconsumed_commit_usd", None)  # old name, replaced by the line above
    CONTENT_JSON.write_text(json.dumps(content, indent=2) + "\n")


def main() -> None:
    df = pd.read_csv(RAW)
    df = add_derived_fields(df)
    df = score_accounts(df)
    df = add_value(df)
    df = add_flags(df)
    df = add_quadrant(df)
    df = add_rank(df)
    df = add_routing(df)
    export(df)

    # --- Console summary ----------------------------------------------------
    print(f"Scored {len(df)} accounts as of {AS_OF_DATE.date()}")
    print("\nQuadrants:\n" + df["quadrant"].value_counts().to_string())
    print(f"\nProgram: {df['program'].value_counts().to_dict()}")
    print("\nFlag counts:")
    for f in ALERTS:
        print(f"  {f:16s} {df['flags'].apply(lambda x: f in x).sum()}")

    # Story checks: each featured account must land in its intended quadrant.
    print("\nFeatured accounts:")
    for quadrant, name in FEATURED.items():
        a = df[df["account_name"] == name].iloc[0]
        print(f"  {name:20s} score {a.propensity_score:3d} | pool ${a.pool_of_funds:>10,.0f} | "
              f"EV ${a.expected_value_usd:>10,.0f} | rank #{a.priority_rank:<3d} | {a.quadrant} | "
              f"flags: {', '.join(a['flags']) or '-'}")
        assert a.quadrant == quadrant, f"{name} should be {quadrant}, got {a.quadrant}"
    nw = df[df["account_name"] == "Northwind Commerce"].iloc[0]
    assert "Commit at Risk" in nw["flags"], "Northwind should be flagged Commit at Risk"
    print("  ✓ Story check passed")

    # Last step: re-derive every number from the raw file and fail loudly on any mismatch.
    import validate
    validate.run()


if __name__ == "__main__":
    main()
