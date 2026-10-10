# How this works — DRAFT for review (not published)

> Review notes: every number below is from `docs/data/accounts.json` / `content.json` as of the 2026-10-01 snapshot.
> On the live page these numbers are read from the JSON, not typed. Lines marked **⚑ CONFIRM** are assumptions I made.
> Tags shown on the page: **Assumption**, **Illustrative**, **Simulated**.
> Estimated reading time on the page: ~14 min.

---

## 1. Summary

**How this works.** Every account gets a Propensity score (how likely it is to grow) and a Pool of funds (money available to unlock). Multiplying them gives Opportunity value, which ranks all 503 accounts. The ranking, plus alerts and team capacity, decides each account's type of help: Deep engagement (SA + FDE), Scaled SA programs, Strategic Bet, or Digital / self-serve. Work is tracked, packaged into programs and a services offer, and measured against a comparison group.

**Why we did it this way.** SA and FDE time is the scarcest resource in technical GTM. A simple, explainable ranking lets leaders, sellers and SAs agree on where that time goes, and change their minds with a logged reason.

**Possibly we can.** Replace the hand-set scorecard with a model trained on real outcomes once the comparison group produces them.

## 2. The problem

**How this works.** Today, SA and FDE time tends to follow whoever asks loudest. There is no shared view of which accounts are likely to grow, how much money is at stake, or whether the help worked.

**Why we did it this way.** Without a shared ranking, three things go wrong: big accounts with stalled projects are found too late, small fast-growing accounts get expensive one-to-one help, and nobody can show leadership the return on technical headcount.

**Possibly we can.** Interview SA leads and account teams to confirm which of these hurts most, and size it with real Salesforce activity data.
⚑ CONFIRM: these three failure modes are my framing of the role's problem, not taken from the job description.

## 3. The lifecycle at a glance

**How this works.** Eight steps, each linking to its section below:
CRM data (§4) → Usage signals (§4) → Propensity score (§5) → Pool of funds & alerts (§6–8) → Prioritize & route (§9–10) → Engage & onsite (§11) → Program & PS offer (§12) → Measure & write-back (§13–14).
Grey steps gather data, purple steps decide, green steps act and earn revenue.

**Why we did it this way.** Each step answers one question in order, so any decision can be traced back to the data behind it.

**Possibly we can.** Run the whole loop weekly on a schedule and post changes (new alerts, accounts crossing the capacity line) to the account team's Slack channel.

## 4. Data

**How this works.**
1. From Salesforce CRM: account details, annual commit, contract dates, open pipeline.
2. From product usage: spend to date, usage growth (last 90 vs prior 90 days), 7-day vs 28-day spike check, new builders (last 30 days), SA meetings (last 90 days).
3. We clean and combine them so each customer is one row, then score, export a Salesforce write-back file, and validate every number.

| Layer | File | What it holds |
|---|---|---|
| Raw | `data/raw/accounts.csv` | One extract per account |
| Processed | `data/processed/account_scores.csv` | Scored table, one row per customer |
| Output | `data/output/salesforce_writeback.csv` | Fields pushed back to Salesforce |
| Site | `docs/data/accounts.json` | What every page reads |

**Why we did it this way.** Warehouse-style layers make each step checkable. A final validation step recomputes every number from the raw data and stops the pipeline if anything disagrees, so no page can show a number another page contradicts.

**Possibly we can.** Build this in BigQuery with Revenue Engineering and Data, refresh daily, and add product-level usage so we know *which* workload is stalled.
**Assumption:** all 503 accounts are generated sample data (seed 42), shaped like Salesforce objects.

## 5. Propensity score

**How this works.**
1. Four signals are each turned into a percentile against all 503 accounts (1.0 = best in the book).
2. Weighted: usage growth 35%, new builders 25%, SA engagement 20%, On-track % 20%.
3. Score = weighted sum × 100. The three biggest contributors become the top reasons.

*Worked example (Northwind):* 0.35 × 99.8 + 0.25 × 99.8 + 0.20 × 98.3 + 0.20 × 1.8 = 34.9 + 25.0 + 19.7 + 0.4 = **80**.

**Why we did it this way.** Usage growth counts most because it shows work already moving onto the platform. Percentiles stop one extreme account from distorting the scale and read naturally ("top 1%"). A scorecard is easy to explain and audit.
**Assumption:** the weights are judgment calls, not fitted to outcomes.

**Possibly we can.** Fit the weights (or a model) on which accounts actually grew after help, and test 30/60/90-day windows.

## 6. Pool of funds

**How this works.** Pool of funds = unused commit + open pipeline. Across all accounts: **$86M** = $59M unused commit + $27M open pipeline.

**Why we did it this way.** Unused commit protects the renewal: if it goes unused, the customer usually renews smaller. Open pipeline is new revenue our help can speed up. Together they are the money technical help can unlock.

**Possibly we can.** Add forecast usage growth, and weight unused commit and new pipeline differently, since one protects revenue and the other adds it.
⚑ CONFIRM: I treat unused commit as "at risk at renewal." Whether unused commit is billed anyway depends on contract terms I don't know.

## 7. Opportunity value

**How this works.** Opportunity value = Propensity score ÷ 100 × Pool of funds. All 503 accounts are ranked by it; #1 is worth the most time. Total across all accounts: **$49M**.

**Why we did it this way.** It balances likelihood and size, so a huge account with no momentum doesn't automatically outrank a mid-size account that's ready to grow.
**Assumption:** the Propensity score is used as a rough likelihood, not a calibrated probability, so Opportunity value is a ranking tool, not a forecast.

**Possibly we can.** Calibrate the score against past win rates so Opportunity value reads as real expected dollars.

## 8. Alerts

**How this works.** Four "why now" alerts:

| Alert | Fires when | Accounts today |
|---|---|---|
| Commit at Risk | 25%+ into the contract and On-track % below 70% | 45 |
| Days to renewal | Renewal within 120 days | 168 |
| Usage Spike | Last 7 days ≥ 1.5× the 28-day average | 18 |
| New builders | 10+ new builders in 30 days | 25 |

On-track % = share of commit used ÷ share of the contract year passed. Status: On track at 90%+, Slightly behind at 70–89%, Behind below 70%.

**Seasonality caveat.** On-track % assumes even spending all year. Retail spend peaks in Q4, so a retailer like Northwind can look further behind in October than it really is.

**Why we did it this way.** Each alert is tied to one action: catch up on commit, prepare the renewal, support a launch, or onboard a new team. The Behind band matches the Commit at Risk line, so the status and the alert never disagree.
**Assumption:** all thresholds.

**Possibly we can.** Adjust On-track % using spending curves from similar customers in the same industry, and tune each threshold so it fires only as often as the team can act each week.
⚑ CONFIRM: **Days to renewal fires on 168 of 503 accounts (33%)**, too many to be a useful "why now". I recommend tightening it to 60 days, or only alerting when renewal is close *and* On-track % is below 90%.

## 9. Type of help

**How this works.** Propensity score (cut-off 60) and Pool of funds (cut-off $300K) split accounts into four types:

| Type of help | Rule | Who's involved | Accounts |
|---|---|---|---|
| Deep engagement (SA + FDE) | High score, big pool | SA leads design and relationship; FDE builds with the customer's developers until the first production workload | 51 |
| Scaled SA programs | High score, small pool | SAs only, in group formats: office hours, workshops, reference architectures | 90 |
| Strategic Bet | Low score, big pool | SA-led discovery with the account team; FDE only if a real project appears | 33 |
| Digital / self-serve | Low score, small pool | No SA/FDE time: docs, templates, alerts | 329 |

**Moving between types:** accounts move automatically when their score or pool crosses a cut-off on the next run, or by a logged override (§10).

**Why we did it this way.** Separating likelihood from size stops big-but-unlikely and small-but-likely accounts from getting the same expensive help.
**Assumption:** the cut-offs of 60 and $300K.

**Possibly we can.** Revisit the cut-offs each quarter, and add a buffer zone so accounts near a line don't flip back and forth week to week.

## 10. Team capacity

**How this works.** The team can actively cover the top 30 accounts by Opportunity value. Those 30 accounts (6% of all) hold **37%** of all Opportunity value ($18M). Inside the line: 21 Deep engagement and 9 Strategic Bet accounts. Everyone else gets a scaled type of help.
**Logged overrides:** an SA lead or account team can change an account's type of help with a written reason, owner and date. It is written back to Salesforce next to the score, and validation rejects any change without a reason. Example: Willow Markets, scored as a Strategic Bet, moved to Deep engagement once a funded project was confirmed.

**Why we did it this way.** The team is a fixed size, so the cut-off line makes the trade-off visible: the Prioritization slider shows what a bigger or smaller team would reach. Overrides keep human judgment in the loop without hiding it.
**Assumption:** a flat count of 30 accounts.

**Possibly we can.** Set team capacity from real SA/FDE hours per engagement, and review overrides monthly to find where the scorecard is wrong.
⚑ CONFIRM: the "30 accounts" is not tied to a stated team size. Do you want an implied staffing line (e.g. "≈ 6 SAs + 3 FDEs at ~5 accounts each")?

## 11. Engagement and onsites

**How this works.** Every account with dedicated help gets one tracked engagement: goal, owner, status (On track / At risk / Blocked), blocker and next step. Today: 8 example engagements (4 on track, 3 at risk, 1 blocked). Onsites follow seven phases: intake → agenda design → staffing → prep → execution → follow-up → measurement.

**Why we did it this way.** One goal and one next step per account keeps reviews short and makes blockers visible early. Onsites are reserved for Deep engagement accounts with a clear technical decision to make, because they are the most expensive form of help.

**Possibly we can.** Pull engagement status from Salesforce activity automatically, and score each onsite against its success metric 30 days later.

## 12. Programs and the PS offer

**How this works.**
- **Commit Burn Sprint:** every Commit at Risk account (45) qualifies. 5 are inside team capacity and get an FDE-led catch-up plan; 32 are enrolled in a 6-week sprint (kickoff, weekly office hours, week-6 review); 8 are in the comparison group (§13).
- **Workers Migration Accelerator (Illustrative pricing):**

| Tier | Scope | Duration | Price | Deals / yr | Usage pull-through / deal |
|---|---|---|---|---|---|
| Assess | Architecture review + plan | 2 weeks | $25K | 12 | $40K |
| Migrate | One production workload | 6 weeks | $90K | 8 | $150K |
| Scale | Multi-workload + enablement | 12 weeks | $180K | 3 | $400K |

Business case: **$1.6M** services revenue + **$2.9M** usage pull-through = **$4.4M** a year. The tier is picked from unused commit: Assess under $200K, Migrate under $1M, Scale above.

**Why we did it this way.** Help that works for many customers should become a repeatable program, not 45 custom projects. Fixed-scope tiers make services easy to sell and easy to staff.
**Illustrative:** prices, deal counts and pull-through are examples to show the packaging logic, not real Cloudflare prices or offers.

**Possibly we can.** Price tiers from real delivery cost and margin targets, and measure pull-through against the comparison group.

## 13. Measuring impact

**How this works.** Of the 40 Sprint-eligible accounts outside team capacity, 20% (8) are picked at random as the comparison group: measured, but not enrolled. Impact = how much more the enrolled accounts improve than the comparison group.

| Group | Accounts | Avg On-track % today | Unused commit |
|---|---|---|---|
| Enrolled | 32 | 55% | $3.9M |
| Comparison group | 8 | 63% | $1.5M |

**Simulated example (made-up outcomes, to show the method):** after one sprint cycle, suppose enrolled accounts use 40% of their unused commit by renewal and the comparison group uses 32%. Impact = 8 points × $3.9M = **~$310K** extra usage. If the sprint costs one SA for a quarter (**Assumption:** ~$60K fully loaded), ROI ≈ 5×.

**Why we did it this way.** Comparing against similar customers who didn't get help counts only the improvement that wouldn't have happened anyway. Before/after numbers would overstate it.

**Possibly we can.** Match the groups on On-track % before splitting them (today they differ by 8 points, normal for only 8 accounts), and rotate the comparison group each cycle so no customer goes without help for long.
⚑ CONFIRM: the simulated 40% vs 32% and the $60K cost are my inventions for the example. Keep, change, or drop them?

## 14. Operating rhythm and ownership

**How this works.**
- **Weekly:** pipeline refresh; new alerts routed to owners; engagement status updated.
- **Monthly:** review overrides and accounts crossing the capacity line.
- **Each sprint (6 weeks):** compare enrolled vs comparison group.
- **Quarterly:** revisit weights, cut-offs and team capacity with leadership.

Handoff: when the comparison group shows impact for two cycles in a row, the playbook is documented and automated, and the owner has people and a quarterly review on the calendar. Then the Scaled SA team lead owns the program and GTM Strategy keeps measuring.

**Why we did it this way.** A fixed rhythm turns the dashboard into a habit, and a clear handoff stops the strategy team from running programs forever.
⚑ CONFIRM: the weekly/monthly/quarterly cadence and the owner roles are proposed, not taken from the job description.

**Possibly we can.** Publish a one-page weekly digest for leadership from the same JSON.

## 15. Case study: Northwind Commerce, end to end

**The data (from Salesforce and product usage).** Enterprise · Retail & eCommerce · AMER. Annual commit **$1.2M**, used so far **$340K**, **60%** of the contract year passed, **145 days** to renewal, open pipeline **$450K**, **28** new builders in 30 days (140 active), usage **+62%** in 90 days, **6** SA meetings in 90 days.

**The math.**

| Measure | Formula | Result |
|---|---|---|
| % of commit used | $340K ÷ $1.2M | 28% |
| On-track % | 28% ÷ 60% | **47% — Behind** |
| Expected by now | $1.2M × 60% | $723K |
| Behind by | $723K − $340K | **$383K** |
| Unused commit | $1.2M − $340K | $860K |
| Pool of funds | $860K + $450K | **$1.31M** |
| Monthly spend | $340K ÷ 7.2 months | **$47K / month** |
| Needed monthly spend | $860K ÷ 4.8 months left | **$180K / month (3.8× today)** |
| Propensity score | see §5 worked example | **80** |
| Opportunity value | 80 ÷ 100 × $1.31M | **$1.05M — rank #2 of 503** |

**Top reasons:** usage +62% over 90 days (top 1%); 28 new builders in 30 days (top 1%); 6 SA meetings in 90 days (top 2%).
**Alerts:** Commit at Risk, New builders. (On-track % may overstate the risk because of Q4 retail seasonality.)
**Type of help:** Deep engagement (SA + FDE), inside team capacity. The SA leads design; an FDE builds with Northwind's developers until the first production workload.
**Planned engagement:** goal: move checkout personalization to Workers. Owner: FDE Priya Raman / SA Marcus Lee. Status: at risk. Blocker: legacy checkout dependencies. Onsite: Oct 21, 2026. FDE-led catch-up plan; recommended services: the Migrate tier.
**Expected outcome:** personalization live for 25% of checkout traffic in 60 days, and Monthly spend rising toward the $180K/month needed to use the full commit by renewal.

**Why this matters.** Northwind is the clearest case for an FDE: strong momentum (its developers are already adopting the platform) plus a large, specific gap ($383K behind). Without help, it likely renews smaller.

**Possibly we can.** Track Northwind's Monthly spend weekly against the needed $180K, and adjust for its Q4 peak.
⚑ CONFIRM: the current onsite success metric says "On-track % back to 90%+" within 60 days. That would need about $245K a month, roughly 5× today's spend, which a director would question. I suggest changing it to "Monthly spend reaches the needed $180K/month within 60 days."

## 16. Assumptions and limitations

**How this works.** Everything below is an assumption to test:
- Sample data shaped like Salesforce (503 accounts, seed 42); 12-month contracts.
- Scorecard weights, signal windows, alert thresholds, On-track bands, type-of-help cut-offs, team capacity of 30.
- Pool of funds treats unused commit as at risk; Opportunity value is a ranking, not a forecast.
- On-track % is straight-line (no seasonality).
- Services prices and pull-through are illustrative; impact results are simulated.
- The comparison group is small (8 accounts), so early results will be noisy.

**Why we did it this way.** Stating limits up front is what makes the rest credible.

**Possibly we can.** Replace each assumption with a measured value as real data arrives, and record each change on this page.

## 17. Opportunities to explore

**How this works.** Possibly we can:
- Train a model on real outcomes (§5) and calibrate Opportunity value (§7).
- Add seasonality-adjusted On-track % (§8).
- Set team capacity from real hours (§10).
- Run the comparison group for real and report Impact and ROI (§13).
- Add an AI assistant that answers questions about any account, using a secure backend instead of a public static site.

**Why we did it this way.** Each item removes one assumption from §16.

## 18. Glossary and role mapping

**How this works.** Two tables:
- the shared glossary (every ⓘ on the site), rendered from `glossary.json`;
- the role mapping: each step's simple explanation, job-description keywords (exact) and page, rendered from `jd_mapping.json`.

**Why we did it this way.** One source of wording keeps every page consistent.
