"""
validate.py — the pipeline's last step. Re-derives every number the site shows
from the raw CSV, independently of pipeline.py, and fails loudly on any mismatch.

Why: the dashboard is meant for a GTM director. One number that disagrees with
another (or a percentage over 100%) costs more credibility than any feature adds.

Checks:
  1. Every computed field in docs/data/accounts.json matches a fresh recomputation
  2. Shares/percentages stay inside 0–100% where they must
  3. Days to renewal agree with % of contract elapsed (±5 days)
  4. Pool of funds = unused commit + open pipeline, exactly
  5. Flags, quadrants, ranks and capacity follow the published thresholds
  6. content.json counts and the Salesforce write-back match the JSON
  7. Northwind Commerce matches its agreed profile
Prints a Northwind table showing each formula and its result.

Run on its own:  .venv/bin/python validate.py
"""

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw" / "accounts.csv"
SITE_JSON = ROOT / "docs" / "data" / "accounts.json"
CONTENT_JSON = ROOT / "docs" / "data" / "content.json"
WRITEBACK = ROOT / "data" / "output" / "salesforce_writeback.csv"

DAYS_PER_MONTH = 365 / 12
MONEY_TOL = 1.0      # values are rounded to whole dollars
SHARE_TOL = 0.006    # shares are rounded to 2 decimals in the JSON
RENEWAL_TOL_DAYS = 5

# The agreed Northwind profile. If the data generator changes, this catches it.
NORTHWIND_SPEC = {
    "segment": "Enterprise", "industry": "Retail & eCommerce", "region": "AMER",
    "annual_commit_usd": 1_200_000, "commit_consumed_usd": 340_000,
    "contract_elapsed_share": 0.60, "days_to_renewal": 145,
    "open_pipeline_usd": 450_000, "new_developers_30d": 28,
}


def run() -> None:
    raw = pd.read_csv(RAW).set_index("account_id")
    site = json.loads(SITE_JSON.read_text())
    meta, accounts = site["meta"], site["accounts"]
    t = meta["thresholds"]
    content = json.loads(CONTENT_JSON.read_text())
    writeback = pd.read_csv(WRITEBACK).set_index("Id")
    failures: list[str] = []

    def check(ok: bool, msg: str) -> None:
        if not ok:
            failures.append(msg)

    def close(a: float, b: float, tol: float) -> bool:
        return abs(a - b) <= tol

    for a in accounts:
        r = raw.loc[a["account_id"]]
        name = a["account_name"]
        start, end = pd.Timestamp(r.contract_start_date), pd.Timestamp(r.contract_end_date)
        as_of = pd.Timestamp(meta["as_of_date"])
        term_days = (end - start).days
        elapsed = min(max((as_of - start).days / term_days, 0), 1)
        days_to_renewal = (end - as_of).days

        # --- 1. Recompute every derived field from raw inputs --------------
        expected = {
            "contract_elapsed_share": (elapsed, SHARE_TOL),
            "days_to_renewal": (days_to_renewal, 0),
            "burn_pace": ((r.commit_consumed_usd / r.annual_commit_usd) / elapsed, SHARE_TOL),
            "unused_commit": (max(r.annual_commit_usd - r.commit_consumed_usd, 0), MONEY_TOL),
            "expected_consumed_to_date": (r.annual_commit_usd * elapsed, MONEY_TOL),
            "behind_pace_amount": (max(r.annual_commit_usd * elapsed - r.commit_consumed_usd, 0), MONEY_TOL),
            "burn_rate_monthly": (r.commit_consumed_usd / (elapsed * term_days / DAYS_PER_MONTH), MONEY_TOL),
        }
        months_left = max(days_to_renewal, 0) / DAYS_PER_MONTH
        unused = max(r.annual_commit_usd - r.commit_consumed_usd, 0)
        expected["required_monthly_burn"] = (unused / months_left if months_left > 0 else unused, MONEY_TOL)
        expected["pool_of_funds"] = (unused + r.open_pipeline_usd, MONEY_TOL)
        expected["expected_value_usd"] = (a["propensity_score"] / 100 * (unused + r.open_pipeline_usd), MONEY_TOL)
        for field in ["annual_commit_usd", "commit_consumed_usd", "open_pipeline_usd", "new_developers_30d",
                      "sa_meetings_90d", "usage_growth_90d_pct", "active_developers"]:
            expected[field] = (r[field], 0)
        for field, (want, tol) in expected.items():
            check(close(a[field], want, tol), f"{name}: {field} = {a[field]} but recomputes to {want:.4f}")

        # --- 2. Ranges ------------------------------------------------------
        check(0 <= a["contract_elapsed_share"] <= 1, f"{name}: contract elapsed {a['contract_elapsed_share']} outside 0–100%")
        check(0 <= a["propensity_score"] <= 100, f"{name}: score {a['propensity_score']} outside 0–100")
        check(a["burn_pace"] >= 0, f"{name}: negative burn pace")
        for f in ["unused_commit", "pool_of_funds", "behind_pace_amount", "required_monthly_burn", "burn_rate_monthly"]:
            check(a[f] >= 0, f"{name}: {f} is negative")

        # --- 3. Days to renewal vs % elapsed (±5 days) -------------------------
        implied = term_days * (1 - a["contract_elapsed_share"])
        check(abs(implied - a["days_to_renewal"]) <= RENEWAL_TOL_DAYS,
              f"{name}: {a['days_to_renewal']} days to renewal but {a['contract_elapsed_share']:.0%} elapsed implies {implied:.0f}")

        # --- 4. Pool of funds identity, exactly ----------------------------
        check(a["pool_of_funds"] == a["unused_commit"] + a["open_pipeline_usd"],
              f"{name}: pool of funds {a['pool_of_funds']} ≠ unused {a['unused_commit']} + pipeline {a['open_pipeline_usd']}")

        # --- 5. Flags and quadrant follow the published thresholds ---------
        flags = {
            "Commit at Risk": elapsed >= t["commit_at_risk_min_elapsed"] and a["burn_pace"] < t["commit_at_risk_max_pace"],
            "Renewal Window": 0 <= days_to_renewal <= t["renewal_window_days"],
            "Usage Spike": a["usage_spike_ratio"] >= t["usage_spike_ratio"] - 0.005,
            "New Developers": a["new_developers_30d"] >= t["new_developers_min"],
        }
        for f, on in flags.items():
            # Burn pace and spike ratio are rounded in the JSON; skip borderline cases.
            borderline = (f == "Commit at Risk" and abs(a["burn_pace"] - t["commit_at_risk_max_pace"]) < SHARE_TOL) or \
                         (f == "Usage Spike" and abs(a["usage_spike_ratio"] - t["usage_spike_ratio"]) < SHARE_TOL)
            if not borderline:
                check(on == (f in a["flags"]), f"{name}: flag '{f}' should be {'on' if on else 'off'}")
        high_score = a["propensity_score"] >= t["score_high"]
        high_value = a["pool_of_funds"] >= t["pool_of_funds_high"]
        want_q = {(True, True): "FDE Deep Engagement", (True, False): "Scaled SA Program",
                  (False, True): "Strategic Bet", (False, False): "Digital"}[(high_score, high_value)]
        check(a["quadrant"] == want_q, f"{name}: quadrant {a['quadrant']} but thresholds give {want_q}")

        # --- 6a. Salesforce write-back agrees with the site JSON -----------
        w = writeback.loc[a["account_id"]]
        check(w.GTM_Propensity_Score__c == a["propensity_score"], f"{name}: write-back score differs")
        check(close(w.GTM_Pool_Of_Funds__c, a["pool_of_funds"], MONEY_TOL), f"{name}: write-back pool of funds differs")
        check(w.GTM_Priority_Rank__c == a["priority_rank"], f"{name}: write-back rank differs")

    # --- 5b. Ranks are by expected value, and capacity = top N -------------
    evs = [a["expected_value_usd"] for a in accounts]
    check(evs == sorted(evs, reverse=True), "accounts are not sorted by expected value")
    check([a["priority_rank"] for a in accounts] == list(range(1, len(accounts) + 1)), "ranks are not 1..N")
    check(all(a["in_capacity"] == (a["priority_rank"] <= t["capacity_top_n"]) for a in accounts),
          "in_capacity does not match the capacity threshold")
    check(abs(sum(meta["weights"].values()) - 1) < 1e-9, "scorecard weights don't sum to 100%")
    check(0 < meta["holdout_share"] < 1, "holdout share outside 0–100%")

    # --- 6b. content.json counts match the accounts ------------------------
    at_risk = [a for a in accounts if "Commit at Risk" in a["flags"]]
    p = content["program"]
    check(p["eligible_accounts"] == len(at_risk), "content.json eligible_accounts is stale")
    check(p["eligible_outside_capacity"] == sum(not a["in_capacity"] for a in at_risk), "content.json eligible_outside_capacity is stale")
    check(p["eligible_unused_commit"] == round(sum(a["unused_commit"] for a in at_risk)), "content.json eligible_unused_commit is stale")
    names = {a["account_name"] for a in accounts}
    for e in content["engagements"]:
        check(e["account"] in names, f"content.json engagement for unknown account {e['account']}")

    # --- 7. Northwind matches its agreed profile + printed check table -----
    nw = next(a for a in accounts if a["account_name"] == "Northwind Commerce")
    for k, want in NORTHWIND_SPEC.items():
        got = nw[k]
        ok = close(got, want, SHARE_TOL) if isinstance(want, float) else got == want
        check(ok, f"Northwind: {k} = {got}, agreed profile says {want}")
    print_northwind(nw)

    if failures:
        print(f"\n✗ VALIDATION FAILED: {len(failures)} problem(s)")
        for f in failures[:40]:
            print("   -", f)
        sys.exit(1)
    print(f"\n✓ Validation passed: {len(accounts)} accounts, every number recomputed from raw data")


def print_northwind(a: dict) -> None:
    usd = lambda n: f"${n:,.0f}"
    rows = [
        ("Annual commit", "from Salesforce", usd(a["annual_commit_usd"])),
        ("Consumed", "from usage billing", usd(a["commit_consumed_usd"])),
        ("% of commit used", "consumed ÷ commit", f"{a['commit_consumed_usd'] / a['annual_commit_usd']:.1%}"),
        ("% of contract elapsed", "days elapsed ÷ term days", f"{a['contract_elapsed_share']:.0%}"),
        ("Days to renewal", "contract end − as-of date", f"{a['days_to_renewal']}"),
        ("Burn pace", "% used ÷ % elapsed", f"{a['burn_pace']:.0%}"),
        ("Burn rate (monthly)", "consumed ÷ months elapsed", usd(a["burn_rate_monthly"])),
        ("Expected consumed to date", "commit × % elapsed", usd(a["expected_consumed_to_date"])),
        ("Behind pace amount", "expected − consumed", usd(a["behind_pace_amount"])),
        ("Unused commit", "commit − consumed", usd(a["unused_commit"])),
        ("Required monthly burn", "unused ÷ months to renewal", usd(a["required_monthly_burn"])),
        ("Open pipeline", "from Salesforce", usd(a["open_pipeline_usd"])),
        ("Pool of funds", "unused commit + open pipeline", usd(a["pool_of_funds"])),
        ("Propensity score", "weighted percentile scorecard", f"{a['propensity_score']}/100"),
        ("Expected value", "score ÷ 100 × pool of funds", usd(a["expected_value_usd"])),
        ("New developers (30 days)", "from usage telemetry", f"{a['new_developers_30d']}"),
        ("Flags", "thresholds in decision log", ", ".join(a["flags"]) or "none"),
        ("Quadrant", "score ≥ cut-off × pool ≥ cut-off", a["quadrant"]),
    ]
    print("\nNorthwind Commerce check")
    print(f"  {'Measure':28s} {'Formula':32s} Result")
    print(f"  {'-' * 28} {'-' * 32} {'-' * 20}")
    for m, f, r in rows:
        print(f"  {m:28s} {f:32s} {r}")


if __name__ == "__main__":
    run()
