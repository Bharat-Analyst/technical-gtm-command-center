"""
pipeline.py — scores every account and decides where SA / FDE time goes.

Flow (mirrors warehouse layers):
    data/raw/accounts.csv                  CRM + telemetry extract (input)
    data/processed/account_scores.csv      scored "mart" table, every column
    data/output/salesforce_writeback.csv   only the fields we'd push to Salesforce
    docs/data/accounts.json                what the website reads

Steps:
    1. Propensity score (0–100) from a weighted scorecard + top 3 reasons
    2. Headroom and Expected Value
    3. Flags: Commit at Risk, Renewal Window, Usage Spike, New Developers
    4. Quadrant (who should own the account: FDE, SA program, etc.)
    5. Rank by Expected Value; the top N fit current SA/FDE capacity
    6. Export
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

# Flag thresholds.
COMMIT_AT_RISK_MIN_ELAPSED = 0.25  # too early in the contract to judge before 25% elapsed
COMMIT_AT_RISK_MAX_PACE = 0.70     # consuming <70% of expected pace → large unused commit at renewal
RENEWAL_WINDOW_DAYS = 120          # ~1 quarter + prep time: when renewal decisions get made
USAGE_SPIKE_RATIO = 1.5            # last 7 days ≥ 1.5× the 4-week average = something new launched
NEW_DEVELOPERS_MIN = 10            # ≥10 new developers in 30 days = a new team, not noise

# Quadrant cut-offs.
SCORE_HIGH = 60                    # roughly the top third of accounts by propensity
HEADROOM_HIGH = 300_000            # dollar headroom big enough to justify FDE-level effort

# How many accounts current SA/FDE headcount can actively cover.
CAPACITY_TOP_N = 30

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw" / "accounts.csv"
PROCESSED = ROOT / "data" / "processed" / "account_scores.csv"
WRITEBACK = ROOT / "data" / "output" / "salesforce_writeback.csv"
SITE_JSON = ROOT / "docs" / "data" / "accounts.json"
CONTENT_JSON = ROOT / "docs" / "data" / "content.json"

QUADRANTS = {
    (True, True): "FDE Deep Engagement",   # likely to grow AND lots at stake
    (True, False): "Scaled SA Program",    # likely to grow, smaller $ → one-to-many
    (False, True): "Strategic Bet",        # big $ but weak signals → targeted exec/SA play
    (False, False): "Digital",             # self-serve docs, webinars, community
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
    top_pct = max(1, round((1 - row[f"pctl_{name}"]) * 100))
    rank_txt = f"top {top_pct}% of accounts"
    if name == "usage_growth":
        return f"Usage {row['usage_growth_90d_pct']:+.0f}% over the last 90 days ({rank_txt})"
    if name == "new_developers":
        return f"{row['new_developers_30d']} new developers in the last 30 days ({rank_txt})"
    if name == "engagement":
        return f"{row['sa_meetings_90d']} SA meetings in the last 90 days ({rank_txt})"
    if name == "commit_burn":
        return f"Consuming commit at {row['burn_pace']:.0%} of expected pace ({rank_txt})"
    raise ValueError(name)


def top_reasons(row: pd.Series) -> list[str]:
    """The 3 signals that contributed the most points to this account's score."""
    ranked = sorted(WEIGHTS, key=lambda n: row[f"contrib_{n}"], reverse=True)
    return [describe_signal(n, row) for n in ranked[:3]]


# =============================================================================
# 2. HEADROOM & EXPECTED VALUE
# =============================================================================
def add_value(df: pd.DataFrame) -> pd.DataFrame:
    # Unconsumed commit: money the customer already agreed to spend but hasn't.
    # Helping them use it protects the renewal. Can't go below zero.
    df["unconsumed_commit_usd"] = (df["annual_commit_usd"] - df["commit_consumed_usd"]).clip(lower=0)
    # Headroom = what's at stake: unused commit + new deals in flight.
    df["headroom_usd"] = df["unconsumed_commit_usd"] + df["open_pipeline_usd"]
    # Expected Value = headroom weighted by how likely we are to realize it.
    df["expected_value_usd"] = (df["propensity_score"] / 100 * df["headroom_usd"]).round(0)
    return df


# =============================================================================
# 3. FLAGS
# =============================================================================
def add_flags(df: pd.DataFrame) -> pd.DataFrame:
    rules = {
        "Commit at Risk": (df["contract_elapsed_share"] >= COMMIT_AT_RISK_MIN_ELAPSED)
                          & (df["burn_pace"] < COMMIT_AT_RISK_MAX_PACE),
        "Renewal Window": df["days_to_renewal"].between(0, RENEWAL_WINDOW_DAYS),
        "Usage Spike": df["usage_spike_ratio"] >= USAGE_SPIKE_RATIO,
        "New Developers": df["new_developers_30d"] >= NEW_DEVELOPERS_MIN,
    }
    for flag, mask in rules.items():
        df[f"flag_{flag.lower().replace(' ', '_')}"] = mask
    df["flags"] = [[f for f, m in rules.items() if m.iloc[i]] for i in range(len(df))]
    return df


# =============================================================================
# 4. QUADRANT
# =============================================================================
def add_quadrant(df: pd.DataFrame) -> pd.DataFrame:
    # Value axis uses headroom (not Expected Value) so the two axes stay
    # independent: EV already contains the score.
    high_score = df["propensity_score"] >= SCORE_HIGH
    high_value = df["headroom_usd"] >= HEADROOM_HIGH
    df["quadrant"] = [QUADRANTS[(s, v)] for s, v in zip(high_score, high_value)]
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
# 6. EXPORT
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
        "GTM_Headroom__c": df["headroom_usd"].round(0),
        "GTM_Expected_Value__c": df["expected_value_usd"],
        "GTM_Priority_Rank__c": df["priority_rank"],
        "GTM_Quadrant__c": df["quadrant"],
        "GTM_Flags__c": df["flags"].str.join(";"),
        "GTM_In_Capacity__c": df["in_capacity"],
        "GTM_Scored_Date__c": AS_OF_DATE.date().isoformat(),
    })
    writeback.to_csv(WRITEBACK, index=False)

    # Website JSON: compact, rounded, only what the pages display.
    site_cols = [
        "account_id", "account_name", "industry", "region", "segment",
        "propensity_score", "top_reasons", "headroom_usd", "unconsumed_commit_usd",
        "open_pipeline_usd", "expected_value_usd", "flags", "quadrant",
        "priority_rank", "in_capacity", "annual_commit_usd", "commit_consumed_usd",
        "burn_pace", "contract_elapsed_share", "days_to_renewal",
        "usage_growth_90d_pct", "new_developers_30d", "sa_meetings_90d",
    ]
    records = df[site_cols].round({"burn_pace": 2, "contract_elapsed_share": 2,
                                   "headroom_usd": 0, "unconsumed_commit_usd": 0})
    payload = {
        "meta": {
            "as_of_date": AS_OF_DATE.date().isoformat(),
            "weights": WEIGHTS,
            "thresholds": {
                "score_high": SCORE_HIGH, "headroom_high": HEADROOM_HIGH,
                "capacity_top_n": CAPACITY_TOP_N,
                "commit_at_risk_max_pace": COMMIT_AT_RISK_MAX_PACE,
                "renewal_window_days": RENEWAL_WINDOW_DAYS,
                "usage_spike_ratio": USAGE_SPIKE_RATIO,
                "new_developers_min": NEW_DEVELOPERS_MIN,
            },
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
    program["eligible_unconsumed_commit_usd"] = int(df.loc[at_risk, "unconsumed_commit_usd"].sum())
    CONTENT_JSON.write_text(json.dumps(content, indent=2) + "\n")


def main() -> None:
    df = pd.read_csv(RAW)
    df = add_derived_fields(df)
    df = score_accounts(df)
    df = add_value(df)
    df = add_flags(df)
    df = add_quadrant(df)
    df = add_rank(df)
    export(df)

    # --- Console summary ----------------------------------------------------
    print(f"Scored {len(df)} accounts as of {AS_OF_DATE.date()}")
    print("\nQuadrants:\n" + df["quadrant"].value_counts().to_string())
    print("\nFlag counts:")
    for f in ["Commit at Risk", "Renewal Window", "Usage Spike", "New Developers"]:
        print(f"  {f:16s} {df['flags'].apply(lambda x: f in x).sum()}")

    nw = df[df["account_name"] == "Northwind Commerce"].iloc[0]
    print("\nNorthwind Commerce:")
    print(f"  Score {nw.propensity_score} | Headroom ${nw.headroom_usd:,.0f} | "
          f"EV ${nw.expected_value_usd:,.0f} | Rank #{nw.priority_rank} | In capacity: {nw.in_capacity}")
    print(f"  Quadrant: {nw.quadrant} | Flags: {', '.join(nw['flags'])}")
    for r in nw['top_reasons']:
        print(f"   - {r}")
    assert nw.quadrant == "FDE Deep Engagement", "Northwind should be FDE Deep Engagement"
    assert "Commit at Risk" in nw['flags'], "Northwind should be flagged Commit at Risk"
    print("  ✓ Story check passed")


if __name__ == "__main__":
    main()
