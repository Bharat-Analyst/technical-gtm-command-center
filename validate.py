"""
validate.py — the pipeline's last step. Re-derives every number the site shows
from the raw extracts, independently of pipeline.py, and fails loudly on any mismatch.

Why: the dashboard is meant for a GTM director. One number that disagrees with
another (or a percentage over 100%) costs more credibility than any feature adds.

Checks:
  1. Clean and combine: roll-ups, merges, signups, meetings and usage per company
  2. Every computed field in docs/data/accounts.json matches a fresh recomputation
  3. Shares stay inside 0–100%; money is never negative
  4. Days to renewal agree with % of contract elapsed (±5 days)
  5. Pool of funds = unused commit + open pipeline, exactly
  6. Scores, alerts, type of help, team capacity slots and programs follow the published rules
  7. Overrides always carry a logged reason
  8. content.json counts and the Salesforce write-back match the JSON
  9. The featured accounts match the methodology page
Prints a Northwind check table showing each formula and its result.

Run on its own:  .venv/bin/python validate.py
"""

import json
import math
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent
RAW = ROOT / "data" / "raw"
SITE_JSON = ROOT / "docs" / "data" / "accounts.json"
CONTENT_JSON = ROOT / "docs" / "data" / "content.json"
WRITEBACK = ROOT / "data" / "output" / "salesforce_writeback.csv"

DAYS_PER_MONTH = 365 / 12
MONEY_TOL, SHARE_TOL, RENEWAL_TOL_DAYS = 1.0, 0.0002, 5

# The methodology page states these; the data must agree.
FEATURED_SPEC = {
    "Northwind Commerce": dict(segment="Enterprise", industry="Retail & eCommerce", region="AMER",
                               annual_commit_usd=1_200_000, commit_consumed_usd=340_000, days_to_renewal=145,
                               open_pipeline_usd=450_000, new_builders_60d=28, meetings_90d=4, product_count=3,
                               propensity_score=81, pool_of_funds=1_310_000,
                               quadrant="Deep engagement (SA + FDE)", coverage="SA + FDE",
                               flags=["Commit at risk", "Renewal coming", "Builder surge"]),
    "Contoso Media": dict(propensity_score=77, pool_of_funds=70_000, quadrant="Scaled SA programs"),
    "Fabrikam Health": dict(propensity_score=32, pool_of_funds=1_100_000, quadrant="Strategic bet"),
    "Tailspin Games": dict(propensity_score=28, pool_of_funds=15_000, quadrant="Digital / self-serve"),
}


def bucket(value, buckets):
    for minimum, points in buckets:
        if value >= minimum:
            return points
    return 0


def run() -> None:
    site = json.loads(SITE_JSON.read_text())
    meta, accounts = site["meta"], site["accounts"]
    t, cap, win = meta["thresholds"], meta["capacity"], meta["signal_windows"]
    as_of = pd.Timestamp(meta["as_of_date"])
    content = json.loads(CONTENT_JSON.read_text())
    writeback = pd.read_csv(WRITEBACK).set_index("Id")
    failures: list[str] = []

    def check(ok, msg):
        if not ok:
            failures.append(msg)

    def close(a, b, tol):
        return abs(a - b) <= tol

    # ---------------- 1. Clean and combine, re-done independently ----------------
    acc = pd.read_csv(RAW / "accounts.csv", dtype=str, keep_default_na=False)
    contracts = pd.read_csv(RAW / "contracts.csv").set_index("account_id")
    opps = pd.read_csv(RAW / "opportunities.csv")
    acts = pd.read_csv(RAW / "activities.csv", parse_dates=["date"])
    usage = pd.read_csv(RAW / "usage_monthly.csv", dtype={"sf_account_id": str}, keep_default_na=False)
    signups = pd.read_csv(RAW / "signups.csv", parse_dates=["signup_date"])

    # Company = the top-level record with a contract that shares this record's email domain.
    company_of_domain = {r.email_domain: r.account_id for r in acc.itertuples()
                         if r.parent_account_id == "" and r.account_id in contracts.index}
    company_of = {r.account_id: company_of_domain[r.email_domain] for r in acc.itertuples()}
    check(len(company_of_domain) == len(accounts), f"{len(company_of_domain)} companies in raw data, {len(accounts)} in JSON")

    usage["company"] = usage["sf_account_id"].map(company_of)
    months = sorted(usage["month"].unique())
    last, prev, three_ago = months[-1], months[-2], months[-1 - win["usage_growth_months"]]
    matched = usage.dropna(subset=["company"])
    spend = matched.groupby(["company", "month"])["spend_usd"].sum().round(2)
    last_products = matched[matched["month"] == last].groupby("company")["product"].apply(lambda s: sorted(set(s)))
    first_use = matched.groupby(["company", "product"])["month"].min()
    recent_months = set(months[-round(win["new_product_days"] / 30):])
    open_pipe = opps[~opps["is_closed"]].assign(company=lambda d: d["account_id"].map(company_of)).groupby("company")["amount_usd"].sum()
    meetings = acts[acts["date"] >= as_of - pd.Timedelta(days=win["engagement_days"])] \
        .assign(company=lambda d: d["account_id"].map(company_of)).groupby("company").size()
    signups["company"] = signups["email_domain"].map(company_of_domain)
    builders = signups[(signups["signup_date"] >= as_of - pd.Timedelta(days=win["new_builders_days"]))].groupby("company").size()
    check(int(usage["company"].isna().sum()) == meta["cleaning"]["unmatched_usage_rows"], "unmatched usage count differs")

    for a in accounts:
        name, cid = a["account_name"], a["account_id"]
        c = contracts.loc[cid]
        start, end = pd.Timestamp(c.start_date), pd.Timestamp(c.end_date)
        term, days_el = (end - start).days, max((as_of - start).days, 0)
        elapsed = min(days_el / term, 1)
        dtr = (end - as_of).days
        used, commit = c.amount_used_usd, c.annual_commit_usd
        unused = max(commit - used, 0)
        pipe = float(open_pipe.get(cid, 0))
        months_left = max(dtr, 0) / DAYS_PER_MONTH
        growth = spend[(cid, last)] / spend[(cid, three_ago)] - 1
        mom = spend[(cid, last)] / spend[(cid, prev)] - 1
        prods = last_products.get(cid, [])
        new_prod = [p for (co, p), m in first_use.items() if co == cid and m in recent_months and m > months[0]]
        nb, mt = int(builders.get(cid, 0)), int(meetings.get(cid, 0))

        # ---------------- 2. Recompute and compare -----------------------------
        w8, bk = meta["weights"], meta["buckets"]
        pts = (w8["usage_growth"] * bucket(round(growth, 4), bk["usage_growth"])
               + w8["new_builders"] * bucket(nb, bk["new_builders"])
               + w8["engagement"] * bucket(mt, bk["engagement"])
               + w8["product_breadth"] * bucket(len(prods), bk["product_breadth"]))
        score = math.floor(pts + 0.5 + 1e-9)
        pool = unused + pipe
        want = {
            "annual_commit_usd": (commit, 0), "commit_consumed_usd": (used, 0), "open_pipeline_usd": (pipe, MONEY_TOL),
            "contract_elapsed_share": (elapsed, SHARE_TOL), "days_to_renewal": (dtr, 0),
            "burn_pace": ((used / commit) / elapsed, 0.001), "unused_commit": (unused, MONEY_TOL),
            "burn_rate_monthly": (used / max(days_el / DAYS_PER_MONTH, 1), MONEY_TOL),
            "expected_consumed_to_date": (commit * elapsed, MONEY_TOL + commit * SHARE_TOL),
            "behind_pace_amount": (max(commit * elapsed - used, 0), MONEY_TOL + commit * SHARE_TOL),
            "required_monthly_burn": (unused / months_left if months_left > 0 else unused, MONEY_TOL),
            "pool_of_funds": (pool, MONEY_TOL), "usage_growth_3m": (growth, 0.0001), "spend_mom_change": (mom, 0.0001),
            "new_builders_60d": (nb, 0), "meetings_90d": (mt, 0), "product_count": (len(prods), 0),
            "propensity_score": (score, 0), "expected_value_usd": (score / 100 * pool, MONEY_TOL),
        }
        for f, (w, tol) in want.items():
            check(close(a[f], w, tol), f"{name}: {f} = {a[f]} but recomputes to {w:.4f}")
        check(a["products_used"] == prods, f"{name}: products differ")
        check((a["new_product"] in new_prod) if a["new_product"] else not new_prod, f"{name}: new product differs")

        # ---------------- 3–5. Ranges and identities -----------------------------
        check(0 <= a["contract_elapsed_share"] <= 1, f"{name}: % elapsed outside 0–100%")
        check(0 <= a["propensity_score"] <= 100, f"{name}: score outside 0–100")
        for f in ["unused_commit", "pool_of_funds", "behind_pace_amount", "required_monthly_burn", "burn_rate_monthly"]:
            check(a[f] >= 0, f"{name}: {f} is negative")
        check(abs(term * (1 - a["contract_elapsed_share"]) - a["days_to_renewal"]) <= RENEWAL_TOL_DAYS,
              f"{name}: days to renewal disagree with % elapsed")
        check(a["pool_of_funds"] == a["unused_commit"] + a["open_pipeline_usd"], f"{name}: pool of funds ≠ unused + pipeline")

        # ---------------- 6. Alerts and type of help ---------------------------
        alerts = {
            "Commit at risk": a["burn_pace"] < t["commit_at_risk_max_pace"] and elapsed >= t["commit_at_risk_min_elapsed"],
            "Renewal coming": 0 <= dtr <= t["renewal_coming_days"],
            "Builder surge": nb >= t["builder_surge_min"],
            "Usage spike": round(mom, 4) >= t["usage_spike_min"],
            "New product": bool(new_prod),
            "Usage drop": round(growth, 4) <= t["usage_drop_max"],
        }
        check(a["flags"] == [k for k, on in alerts.items() if on], f"{name}: alerts {a['flags']} disagree with rules")
        q = meta["quadrants"]  # [deep, bet, scaled, digital]
        hs, hp = score >= t["score_high"], pool >= t["pool_of_funds_high"]
        model_q = q[0] if hs and hp else q[1] if hp else q[2] if hs else q[3]
        check(a["model_quadrant"] == model_q, f"{name}: scorecard type {a['model_quadrant']} but rules give {model_q}")
        # ---------------- 7. Overrides need a reason -----------------------------
        check(a["quadrant"] == a["model_quadrant"] or bool(a["override_reason"]), f"{name}: type changed without a logged reason")

        w = writeback.loc[cid]
        check(w.GTM_Propensity_Score__c == a["propensity_score"] and w.GTM_Priority_Rank__c == a["priority_rank"]
              and close(w.GTM_Pool_Of_Funds__c, a["pool_of_funds"], MONEY_TOL), f"{name}: write-back differs")

    # ---------------- 6b. Team capacity slots, re-filled independently ---------------
    order = sorted(accounts, key=lambda a: (not a["flags"], -a["expected_value_usd"], a["account_id"]))
    deep, bet = meta["quadrants"][0], meta["quadrants"][1]
    deep_q = [a for a in order if a["quadrant"] == deep]
    bet_q = [a for a in order if a["quadrant"] == bet]
    fde_ids = [a["account_id"] for a in deep_q[: cap["fde_slots"]]]
    deep_q, sa_ids = deep_q[cap["fde_slots"]:], set(fde_ids)
    while len(sa_ids) < cap["sa_slots"] and (deep_q or bet_q):
        nxt = deep_q if (not bet_q or (deep_q and deep_q[0]["expected_value_usd"] >= bet_q[0]["expected_value_usd"])) else bet_q
        sa_ids.add(nxt.pop(0)["account_id"])
    for a in accounts:
        check(a["fde_slot"] == (a["account_id"] in fde_ids), f"{a['account_name']}: FDE slot disagrees with the fill rule")
        check(a["sa_slot"] == (a["account_id"] in sa_ids), f"{a['account_name']}: SA slot disagrees with the fill rule")
    evs = [a["expected_value_usd"] for a in accounts]
    check(evs == sorted(evs, reverse=True) and [a["priority_rank"] for a in accounts] == list(range(1, len(accounts) + 1)),
          "ranks are not by opportunity value")
    check(abs(sum(meta["weights"].values()) - 1) < 1e-9, "weights don't sum to 100%")

    # Programs and comparison group.
    for a in accounts:
        el = "Commit at risk" in a["flags"] and a["unused_commit"] >= t["sprint_min_unused"]
        check(a["sprint_eligible"] == el, f"{a['account_name']}: sprint eligibility differs")
        check(not (a["holdout"] and a["sa_slot"]), f"{a['account_name']}: dedicated help held back")
        check(not a["holdout"] or a["qualifies_for_scaled_help"], f"{a['account_name']}: comparison group outside qualifying accounts")

    # ---------------- 8. content.json counts ---------------------------------------
    el = [a for a in accounts if a["sprint_eligible"]]
    p = content["program"]
    check(p["eligible_accounts"] == len(el) and p["eligible_outside_capacity"] == sum(not a["sa_slot"] for a in el)
          and p["eligible_unused_commit"] == round(sum(a["unused_commit"] for a in el)), "content.json program counts are stale")
    names = {a["account_name"] for a in accounts}
    for e in content["engagements"]:
        check(e["account"] in names, f"content.json engagement for unknown account {e['account']}")

    # ---------------- 9. Featured accounts ---------------------------------------------
    by_name = {a["account_name"]: a for a in accounts}
    for name, spec in FEATURED_SPEC.items():
        for k, v in spec.items():
            check(by_name[name][k] == v, f"{name}: {k} = {by_name[name][k]}, methodology says {v}")
    print_northwind(by_name["Northwind Commerce"])

    if failures:
        print(f"\n✗ VALIDATION FAILED: {len(failures)} problem(s)")
        for f in failures[:40]:
            print("   -", f)
        sys.exit(1)
    print(f"\n✓ Validation passed: {len(accounts)} accounts, every number recomputed from raw data")


def print_northwind(a: dict) -> None:
    usd = lambda n: f"${n:,.0f}"
    rows = [
        ("Annual commit", "Salesforce contract", usd(a["annual_commit_usd"])),
        ("Used so far", "Salesforce contract", usd(a["commit_consumed_usd"])),
        ("% of commit used", "used ÷ commit", f"{a['commit_used_share']:.0%}"),
        ("% of contract elapsed", "days passed ÷ term days", f"{a['contract_elapsed_share']:.0%}"),
        ("Days to renewal", "contract end − as-of date", f"{a['days_to_renewal']}"),
        ("On-track %", "% used ÷ % elapsed", f"{a['burn_pace']:.0%}"),
        ("Expected by now", "commit × % elapsed", usd(a["expected_consumed_to_date"])),
        ("Behind by", "expected − used", usd(a["behind_pace_amount"])),
        ("Unused commit", "commit − used", usd(a["unused_commit"])),
        ("Open pipeline", "open opportunities", usd(a["open_pipeline_usd"])),
        ("Pool of funds", "unused commit + open pipeline", usd(a["pool_of_funds"])),
        ("Monthly spend", "used ÷ months passed", usd(a["burn_rate_monthly"])),
        ("Needed monthly spend", "unused ÷ months left", usd(a["required_monthly_burn"])),
        ("Year-end use at today's pace", "monthly spend × 12", usd(a["projected_year_use"])),
        ("Usage growth (3 months)", "last month ÷ 3 months before − 1", f"{a['usage_growth_3m']:+.0%} → {a['score_usage_growth']}"),
        ("New builders (60 days)", "signups matched by domain", f"{a['new_builders_60d']} → {a['score_new_builders']}"),
        ("Meetings and calls (90 days)", "Salesforce activity", f"{a['meetings_90d']} → {a['score_engagement']}"),
        ("Products used", ", ".join(a["products_used"]), f"{a['product_count']} → {a['score_product_breadth']}"),
        ("Propensity score", "0.35·usage + 0.30·builders + 0.15·eng + 0.20·breadth", f"{a['propensity_score']}"),
        ("Opportunity value", "score ÷ 100 × pool of funds", usd(a["expected_value_usd"])),
        ("Alerts", "rules on How this works", ", ".join(a["flags"]) or "none"),
        ("Type of help", "score ≥ 60 and pool ≥ $250K", a["quadrant"]),
        ("Team capacity", "slot fill order", a["coverage"]),
    ]
    print("\nNorthwind Commerce check")
    print(f"  {'Measure':30s} {'Formula':52s} Result")
    for m, f, r in rows:
        print(f"  {m:30s} {f:52s} {r}")


if __name__ == "__main__":
    run()
