<!-- Source of truth for the 'How this works' page (docs/how-this-works.html).
     Numbers are the pipeline's exact values as of the 2026-10-01 snapshot; on the site they are
     read live from docs/data/accounts.json. If you change a rule here, change pipeline.py too. -->

# How this works

Oct 10, 2026 · @Bharat

## Summary

The command center turns customer data into one decision: where Solutions Architects (SAs) and Forward Deployed Engineers (FDEs) spend their limited time, and what kind of help each account gets.

It works in eight steps. Data comes in from Salesforce and product usage. Each account gets a propensity score (how likely it is to grow) and a pool of funds (money available to unlock). Together they give an opportunity value. Alerts add a "why now". Each account then gets a type of help, limited by team capacity. The team engages, revenue follows, and a comparison group shows whether the help made a difference.

The worked example is Northwind Commerce: a $1.2M commit with only 28% used, 60% of the year gone, and 145 days to renewal. The system places it in Deep engagement (SA + FDE) because it has a $1.31M pool of funds, a propensity score of 81, and 3 active alerts.

## The problem

SAs and FDEs are the scarcest technical resource in go-to-market, and without a system their time goes to whoever asks loudest, not where it matters most.

**How this works today, in many teams:**

- Account teams request help by message or meeting, one at a time.
- Requests are judged on relationships and urgency, not on data.
- Nobody sees the full list of active work, blockers, or results in one place.
- Good work with one customer stays with that customer. It rarely becomes a repeatable program.
- Leaders can't easily answer: "Is SA and FDE time growing consumption?"

**What this costs:**

- Big opportunities go unnoticed until renewal, when it's too late to help.
- Small accounts that would grow on their own get expensive one-on-one help.
- Teams can't prove the return on SA and FDE investment, so it's hard to justify more headcount.

The goal: a clear, repeatable way to decide where technical time goes, run the work, and measure whether it drove the right business outcomes.

## The lifecycle at a glance

The system runs in eight steps, and the last step feeds back into the first so it improves every quarter.

1. **Data comes in.** Salesforce and product usage data arrive on a schedule.
2. **Clean and combine.** Messy records are fixed and each company becomes one row.
3. **Score propensity.** Each account gets a 0–100 score for how likely it is to grow. *Decision: who is likely to grow?*
4. **Size the prize.** Pool of funds and opportunity value are calculated. *Decision: is it worth our time?*
5. **Alert and prioritize.** Alerts add urgency, each account gets a type of help, and team capacity sets the cutoff. *Decision: where do SAs and FDEs go?*
6. **Engage the customer.** The team runs the right play: deep engagement, a scaled program, discovery, or self-serve. *Decision: what kind of help?*
7. **Revenue.** Workloads reach production and consumption grows.
8. **Measure and learn.** Helped accounts are compared with a similar group that wasn't helped, and the scoring is updated. *Decision: did it work, and what do we change?*

Steps 1–2 are data, steps 3–5 are decisions, and steps 6–8 are action and revenue. Each step has its own section below.

## Data

Everything starts with two sources joined into one row per account: what customers bought (Salesforce) and what they actually use (product usage).

### How this works

| Source | What it tells us | Example fields |
|---|---|---|
| Salesforce: Account | Who the customer is | Name, segment, industry, region, owner |
| Salesforce: Contract | What they committed to spend | Annual commit, start and end dates, amount used |
| Salesforce: Opportunity | Deals in progress | Stage, amount, product, close date |
| Salesforce: Activity | How engaged they are | Meetings and calls in the last 90 days |
| Salesforce: SA engagement (custom) | Past and current technical help | Type, SA or FDE, hours, outcome |
| Product usage | What they actually use | Monthly spend by product, products used |
| Self-serve signups | Who is building on their own | New builders by company email domain |

The data goes through three layers, the same pattern a data warehouse uses:

1. **Raw.** Data lands exactly as it arrived. Nothing is changed, so we can always trace a number back.
2. **Cleaned.** Duplicate accounts are merged, names and industries are standardized, child accounts are rolled up to their parent company, and usage is matched to the right account. Usage that can't be matched is logged, not dropped.
3. **Ready to use.** One row per account per month, with every number needed for scoring.

In this run: 521 account records became 503 companies after 6 duplicate records were merged and 12 child accounts were rolled up; 16 different industry spellings were standardized; 36 usage rows ($17K) couldn't be matched and were logged; 300 signups from personal email domains couldn't be tied to a company.

After scoring, results are written back as Salesforce fields (propensity score, pool of funds, alerts, type of help, top reasons) so account teams see them where they already work.

### Why we did it this way

- One row per account makes every account comparable and every score explainable.
- Keeping raw data untouched means any number can be checked against its source.
- Writing results back to Salesforce matters more than any dashboard: teams act on what they see in their daily tools.
- Monthly snapshots let us look back and ask, "What did we know on that date?" This prevents using future information by mistake.

### Possibly we can

- Connect to the real Salesforce and data warehouse instead of sample files.
- Add data quality alerts, such as a spike in usage that can't be matched to an account.
- Add outside signals like company size and which cloud providers a company uses.

## Propensity score

The propensity score is a number from 0 to 100 that says how likely an account is to grow its usage in the next 90 days.

### How this works

Four signals are each turned into a 0–100 score, then combined with weights:

| Signal | What it measures | Weight | How it's scored |
|---|---|---|---|
| Usage growth | Change in monthly spend over the last 3 months | 35% | 40%+ = 100 · 25%+ = 85 · 10%+ = 60 · 0%+ = 30 · falling = 0 |
| New builders | People who started building in the last 60 days | 30% | 15+ = 100 · 5+ = 70 · 1+ = 40 · none = 0 |
| Engagement | Meetings and calls in the last 90 days | 15% | 6+ = 100 · 3+ = 60 · 1+ = 30 · none = 0 |
| Product breadth | Number of developer platform products used | 20% | 5+ = 100 · 4 = 80 · 3 = 60 · 2 = 40 · 1 = 20 |

Propensity score = 35% × Usage growth + 30% × New builders + 15% × Engagement + 20% × Product breadth

Each account also gets its top reasons: the three signals that added the most points, written in plain English, such as "28 new builders in 60 days."

### Why we did it this way

- A simple scorecard first. SAs and leaders can see exactly why an account scored high, which builds trust from day one.
- Usage growth carries the most weight because recent momentum is the strongest sign of near-term growth.
- New builders come second because more people building today usually means more workloads in production in a few months.
- Commit pressure is not in the score. Being behind on commit is a risk, not a sign of growth, so it's handled as an alert instead (see Alerts).
- Weights are assumptions. They're set by judgment and kept in one config file so anyone can change them.

### Possibly we can

- Test the weights against real history: did high-scoring accounts actually grow more?
- Move to a machine learning model once enough outcomes are tracked, keeping top reasons so it stays explainable.
- Count new builders only if they deployed something, and exclude automated accounts.

## Pool of funds

The pool of funds is the money available to unlock in an account: commit the customer has already promised but not yet used, plus deals in progress.

### How this works

Pool of funds = Unused commit + Open pipeline

- **Unused commit** = annual commit − amount used so far. This money is already promised. Helping the customer use it protects the renewal.
- **Open pipeline** = the value of deals being worked on but not signed. This is possible new money.

The pool of funds is always shown with its two parts, never as a single total, so readers can see where the money comes from. Across all 503 accounts: $79.39M = $60.22M unused commit + $19.17M open pipeline.

Alongside it, four simple numbers show how the commit is going:

| Number | How it's calculated | What it tells us |
|---|---|---|
| Monthly spend | Amount used ÷ months passed | How fast they use the platform today |
| On-track % | % of commit used ÷ % of contract time passed | 100% = on track. Below 100% = behind |
| Behind by | (Commit × % of time passed) − amount used | How far behind an even pace they are |
| Needed monthly spend | Unused commit ÷ months left | What they'd need to spend to use the full commit |

On-track % status: On track at 90% or more, Slightly behind at 70%–89%, Behind below 70%. These cutoffs are assumptions.

### Why we did it this way

- Unused commit is the most urgent money. If a customer doesn't use what they bought, they're likely to commit less at renewal.
- Pipeline is included because SA and FDE help often decides whether those deals close.
- Showing both parts keeps the number honest. Some teams leave pipeline out because it may overlap with the renewal.
- On-track % assumes even spending, which is a simplification. Retail and eCommerce customers usually spend more in Q4, so a retailer can look behind in summer and catch up in the holidays.

### Possibly we can

- Show two versions side by side: unused commit only, and with pipeline.
- Weight pipeline by deal stage, so an early-stage deal counts less than one about to close.
- Adjust on-track % for seasonality using spending curves from similar accounts.
- Add a third part: the gap between this account's spend and similar companies' spend.

## Opportunity value

Opportunity value combines how likely an account is to grow with how much money is at stake, giving one number to rank accounts by.

### How this works

Opportunity value = (Propensity score ÷ 100) × Pool of funds

| Account | Propensity score | Pool of funds | Opportunity value |
|---|---|---|---|
| Northwind Commerce | 81 | $1.31M | $1.06M |
| Fabrikam Health | 32 | $1.1M | $352K |
| Contoso Media | 77 | $70K | $54K |
| Tailspin Games | 28 | $15K | $4K |

### Why we did it this way

- Propensity alone isn't enough. Contoso scores 77 but has only $70K in play. A high score on a small account doesn't justify dedicated engineers.
- Pool of funds alone isn't enough. Fabrikam has $1.1M in play but a score of 32. Big money with no activity needs discovery first, not a builder.
- Multiplying the two rewards accounts that are both likely to grow and worth a lot, like Northwind.
- It's an estimate, not a forecast. It's for ranking accounts against each other, not for predicting revenue.

### Possibly we can

- Divide by the estimated SA or FDE hours an account needs, to rank by value per hour of team time.
- Check whether opportunity value actually predicts growth once real outcomes are tracked.

## Alerts

Alerts are simple rules that say why an account needs attention now, and an account with an alert moves up within its type of help.

### How this works

| Alert | Fires when | Suggested action | Owner | Respond within | Accounts today |
|---|---|---|---|---|---|
| Commit at risk | On-track % below 70% | Plan to move workloads to production; consider the Commit Burn Sprint | SA | 5 business days | 37 |
| Renewal coming | 180 days or less to renewal for Enterprise accounts, 90 days for everyone else | Review usage and value with the customer before renewal talks | Account team + SA | 10 business days | 140 |
| Builder surge | 15 or more new builders in 60 days | Reach out to help the new builders get to production | SA | 5 business days | 26 |
| Usage spike | Monthly spend up 50% or more in one month | Check the setup can scale; look for expansion | SA | 3 business days | 17 |
| New product | First use of a new product in the last 60 days | Share best practices for that product | SA or scaled program | 10 business days | 26 |
| Usage drop | Monthly spend down 30% or more over 3 months | Health check: find out what changed | Account team + SA | 5 business days | 13 |

Each alert has a time to respond, for example within 5 business days for Commit at risk.

### Why we did it this way

- Scores say who; alerts say when. A high score shows potential. An alert shows a reason to act this week.
- Few alerts on purpose. Six alerts is enough. Too many and people stop reading them.
- Every alert has an owner and an action, so it leads to work, not just a warning.
- All thresholds are assumptions chosen by judgment, and easy to change in one config file.
- On-track % has a known weakness: it assumes even spending, so Commit at risk can fire early for seasonal businesses like retail. Treat it as a prompt to check, not a verdict.

### Possibly we can

- Tune thresholds by checking which alerts led to real growth.
- Adjust Commit at risk for seasonal spending patterns.
- Send alerts straight to the account team's Slack channel or Salesforce.

## Type of help

Every account gets one of four types of help, decided by two questions: is it likely to grow (propensity score of 60 or more), and is there a lot at stake (pool of funds of $250K or more)?

Only Northwind sits in the top-right zone, so it is the only one of the four featured accounts that gets an FDE.

### How this works

| Type of help | Propensity score | Pool of funds | Who | What happens | Goal | Accounts |
|---|---|---|---|---|---|---|
| Deep engagement (SA + FDE) | 60+ | $250K+ | SA leads design and relationship; FDE builds with the customer's developers | Architecture plan, onsite, hands-on build to production | First workload live, fast | 29 |
| Strategic bet | Under 60 | $250K+ | SA leads with the account team; FDE only if a real project appears | Discovery meetings or an onsite to find the first use case | Create momentum | 57 |
| Scaled SA programs | 60+ | Under $250K | SAs in group formats; no FDE | Office hours, workshops, reference architectures | Keep momentum going at low cost | 47 |
| Digital / self-serve | Under 60 | Under $250K | No dedicated people | Docs, templates, product emails; alerts watch for change | Grow on their own | 370 |

SAs are in three of the four types. The SA is the architect and relationship owner. The FDE is the hands-on builder, added only when there's a big, urgent project worth building together.

Accounts move between types every quarter as their data changes:

- Deep engagement → Scaled programs, once the first workload is live.
- Strategic bet → Deep engagement, once a real project appears.
- Scaled programs → Deep engagement, if the pool of funds grows.
- Digital → Scaled programs, if an alert fires.

### Why we did it this way

- Two simple questions are easy to explain and easy to challenge.
- FDEs are the scarcest resource, so they go only where high propensity and a big pool of funds meet.
- Strategic bets get SA time, not FDE time. The money is there but the activity isn't yet; the first job is discovery.
- Cutoffs are assumptions. A score of 60 and $250K were chosen by judgment so that roughly the right number of accounts land in each type for the team's size.

### Possibly we can

- Set cutoffs from data, for example the score above which accounts grew most often.
- Use different cutoffs by segment, since $250K means more for a mid-market account than an enterprise one.

## Team capacity

Team capacity is how many accounts the SAs and FDEs can actively support in a quarter, and it decides where the cutoff line falls.

### How this works

The prototype assumes a team of 10 SAs and 4 FDEs:

| Role | Assumed load | Slots per quarter | Used for |
|---|---|---|---|
| FDE | 2 deep engagements at a time | 8 | Deep engagement only |
| SA | 3 dedicated accounts at a time, plus scaled programs | 30 | Deep engagement and strategic bets |

Accounts are filled into slots in order:

1. Rank accounts within each type of help by opportunity value.
2. Within the same type, accounts with alerts move up.
3. Fill FDE slots with the top Deep engagement accounts until all 8 are used. Each of these also uses an SA slot, because the SA leads the design.
4. The #1 account by opportunity value always gets an SA slot, even without an alert.
5. Fill the remaining SA slots with Deep engagement and Strategic bet accounts, taking whichever type's next account has the higher opportunity value.
6. Everything below the cutoff line goes to scaled programs or self-serve, and is watched by alerts.

Today: 8 accounts hold an FDE slot, 22 more hold an SA slot, and together they hold 37% of all opportunity value.

Manual overrides are allowed. A leader can move an account up or down, but must log a reason. Overrides are reviewed each quarter to see whether they beat the system. Example: Acme Studios was scored as a Strategic bet and moved to Deep engagement (SA + FDE): "Account team confirmed a funded migration project; Strategic bet rule says add an FDE once a real project appears (SA lead: Hannah Cho, 2026-09-28)".

### Why we did it this way

- Without a capacity limit, a priority list is a wish list. "Top 200 accounts" means nothing with 10 SAs.
- A visible cutoff line makes the trade-off clear: adding one account means removing another.
- Overrides with reasons respect local knowledge while keeping the system honest.
- Team size and load are assumptions. The Prioritization page lets you change them with a slider.

### Possibly we can

- Use real SA and FDE hours from the engagement tracker instead of assumed loads.
- Plan capacity by region, so AMER accounts are matched to AMER teams.

## Engagement and onsites

Once an account is chosen, the work is run the same way every time: clear goal, named owners, success criteria, and follow-up, all tracked in one place.

### How this works

The engagement tracker keeps one row per active engagement:

| Field | Example (Northwind) |
|---|---|
| Goal | Move checkout personalization to Workers before renewal |
| Type of help | Deep engagement (SA + FDE) |
| Owners | SA Marcus Lee (design and relationship), FDE Priya Raman (build), account executive Jordan Patel (commercial) |
| Customer stakeholders | Head of platform engineering, checkout team lead |
| Success criteria | First workload in production; On-track % back above 70% |
| Risks and blockers | Security review timing; competing holiday code freeze |
| Status | At risk |
| Next step | Run the architecture onsite, Oct 21 |

The onsite model has five stages:

1. **Intake.** The account team submits a short form: goal, stakeholders, the decision the customer needs to make, and timing.
2. **Agenda design.** The SA shapes the day around the customer's decision, not a product tour.
3. **Staffing and prep.** Pick who attends (SA, FDE, product specialist if needed). Review usage data and the architecture in advance.
4. **Execution.** Run working sessions, agree on a build plan, and name owners on both sides.
5. **Follow-up and measurement.** Send a written summary within 2 business days, track actions in the tracker, and check results at 30 and 90 days.

### Why we did it this way

- One tracker gives leaders a single view of engagement health, blockers, and outcomes.
- Success criteria set up front stop engagements from drifting.
- Onsites built around a decision lead to action. A product overview rarely does.
- Follow-up is a stage, not an afterthought, because most of the value is lost without it.

### Possibly we can

- Build the tracker as a custom object in Salesforce so it lives with the account.
- Add a simple intake form that feeds the tracker automatically.
- Review onsite outcomes quarterly to improve the agenda templates.

## Programs and the PS offer

When the same kind of help works for many customers, it becomes a repeatable program; when customers repeatedly need deep hands-on work, it becomes a packaged Professional Services (PS) offer.

### How this works

**Program playbook: Commit Burn Sprint**

| Part | Detail |
|---|---|
| Trigger | Commit at risk alert and unused commit of $250K or more |
| Who | SA leads; FDE joins for Deep engagement accounts |
| Length | 6 weeks |
| Week 1 | review usage, pick 1–2 workloads to move, agree success criteria |
| Weeks 2–5 | build and test with the customer's developers; weekly check-ins |
| Week 6 | first workload in production; review results with the customer |
| Success measure | On-track % back above 70% within one quarter |
| Eligible accounts | 8 today (Programs page) |

**PS offer: Workers Migration Accelerator**

| Tier | Scope | Length | Price |
|---|---|---|---|
| Starter | One workload, architecture review and build plan | 2 weeks | $25K |
| Standard | One workload taken to production with the customer's team | 6 weeks | $60K |
| Advanced | Several workloads, plus team enablement and handover | 12 weeks | $120K |

The business case has three parts: services revenue, the consumption the migration unlocks, and the cost to deliver it. The Programs page shows each part.

### Why we did it this way

- Programs scale what works. One SA running a proven sprint can help more accounts than one-off engagements.
- Clear trigger, steps, and success measure make a program easy to repeat and easy to measure.
- Packaging services in tiers makes them easier to understand, price, and sell.
- Services are tied to consumption. The point isn't only services revenue; it's helping customers use the platform more.
- Real pricing would come from Finance and Professional Services.

### Possibly we can

- Run the Commit Burn Sprint as a pilot with a few accounts and compare against the comparison group.
- Build the PS business case with real delivery costs and consumption data.
- Add more programs as patterns appear, such as a Workers AI onboarding program.

## Measuring impact

To prove SA and FDE help drives revenue, we compare accounts we helped with a similar group we deliberately didn't help; the difference in growth is the impact.

### How this works

1. **Pick similar accounts.** From accounts that qualify for help, set aside a small group, chosen at random, that gets the normal service only. This is the comparison group. Today: 10 of 48 qualifying accounts (20%).
2. **Help the rest as planned.**
3. **Track both groups for one to two quarters:** monthly spend growth, on-track %, renewals, time to first production workload.
4. **Compare.** The extra growth in the helped group is the impact of the SA and FDE work.
5. **Feed it back.** Use what worked to adjust scoring weights, alert thresholds, and programs.

For example, if helped accounts grew monthly spend by 34% over two quarters and the comparison group by 19%, the impact would be 15 percentage points.

### Why we did it this way

- Accounts with high scores often grow anyway. Without a comparison group, the team would take credit for growth that would have happened regardless.
- Random selection makes the two groups alike, so the difference is fair.
- A small comparison group limits the cost of not helping some accounts. Accounts holding a dedicated SA or FDE slot are never held back.

### Possibly we can

- Keep the comparison group small and rotate it each quarter so no customer is left out for long.
- Where a comparison group isn't acceptable, compare against similar accounts from an earlier period instead.
- Report impact in dollars and as return on SA and FDE hours.

## Operating rhythm and ownership

The system only works if it runs on a regular schedule and every program eventually has a long-term owner.

### How this works

| How often | What happens | Who |
|---|---|---|
| Weekly | Review the priority list, new alerts, and blocked engagements; agree on changes | SA and FDE leads, strategy |
| Monthly | Refresh data and scores; update the engagement tracker | Strategy, data partner |
| Quarterly | Review impact against the comparison group; adjust weights, thresholds, and capacity; review overrides | Developer GTM leadership |

**Handing a program to a durable owner.** A new program stays with the strategy team until it meets four tests:

- It has a clear trigger and steps that others can follow.
- It has run with enough accounts to show a result.
- Its impact is measured against the comparison group.
- A team has agreed to own it, with time to run it.

Then it moves to that team, and strategy moves on to the next new idea.

### Why we did it this way

- A weekly rhythm turns the scores into action.
- Quarterly reviews keep the system honest and let it improve.
- Clear handoff tests stop strategy teams from running programs forever, and stop half-proven programs from being handed off too soon.

### Possibly we can

- Add a one-page quarterly report for leadership: coverage, pipeline, engagement health, and impact.
- Track how long programs take to go from idea to durable owner.

## Case study: Northwind Commerce, end to end

Northwind has used only 28% of a $1.2M commit with 60% of the year gone, so the system places it in Deep engagement (SA + FDE) to protect the renewal and grow usage.

### Step 1: Data comes in

| Field | Value |
|---|---|
| Segment, industry, region | Enterprise, Retail & eCommerce, AMER |
| Annual commit | $1,200,000 |
| Amount used so far | $340,000 |
| Contract time passed | 60% (about 7.2 of 12 months) |
| Days to renewal | 145 |
| Open pipeline | $450,000 |
| New builders, last 60 days | 28 |
| Usage growth, last 3 months | +38% |
| Meetings and calls, last 90 days | 4 |
| Products used | 3 (KV, R2, Workers) |

### Step 2: Clean and combine

Self-serve signups using Northwind's company email domain were matched to the Northwind account (28 in the last 60 days), and usage from its 2 billing accounts, including child account Northwind Commerce Canada, was rolled up into one row.

### Step 3: Propensity score

| Signal | Northwind | Signal score | Weight | Points |
|---|---|---|---|---|
| Usage growth | +38% | 85 | 35% | 29.75 |
| New builders | 28 | 100 | 30% | 30.00 |
| Engagement | 4 meetings and calls | 60 | 15% | 9.00 |
| Product breadth | 3 products | 60 | 20% | 12.00 |
| **Total** |  |  |  | **80.75 → 81** |

Top reasons: 28 new builders in 60 days; Usage up 38% in 3 months; Uses 3 developer platform products.

### Step 4: Pool of funds and commit health

| Number | Math | Result |
|---|---|---|
| % of commit used | $340K ÷ $1.2M | 28% |
| On-track % | 28% ÷ 60% | 47% Behind |
| Expected by now | $1.2M × 60% | $723K |
| Behind by | $723K − $340K | $383K |
| Unused commit | $1.2M − $340K | $860K |
| Pool of funds | $860K + $450K | $1.31M |
| Monthly spend | $340K ÷ 7.2 months | about $47K |
| Needed monthly spend | $860K ÷ 4.8 months | about $180K |
| Year-end use at today's pace | $47K × 12 | about $564K (47% of commit) |

### Step 5: Opportunity value, alerts, and type of help

- **Opportunity value:** 0.81 × $1.31M = about $1.06M, rank #2 of 503.
- **Alerts:** Commit at risk (On-track % of 47% is below 70%), Renewal coming (145 days is within 180 for Enterprise accounts), Builder surge (28 new builders is 15 or more).
- **Type of help:** propensity score 81 (60 or more) and pool of funds $1.31M ($250K or more) → Deep engagement (SA + FDE).
- **Team capacity:** high opportunity value plus 3 alerts put Northwind in one of the 8 FDE slots (coverage: SA + FDE).

A note on seasonality: Northwind's remaining months include the holiday shopping season, when retail usage usually peaks. Part of the gap may close on its own, so the team checks last year's holiday usage before setting targets.

### Step 6: Engage the customer

1. **Architecture onsite.** The SA runs a working session on moving checkout personalization to Workers, with the head of platform engineering and the checkout team.
2. **Commit Burn Sprint.** Over 6 weeks, the FDE builds with Northwind's developers to put the first workload into production.
3. **PS offer.** If more workloads follow, the Workers Migration Accelerator (Standard tier, $60K) gives them a packaged path.

### Step 7: Expected outcome

Targets, not forecasts: first workload in production within 6 weeks, On-track % back above 70% within the quarter, and renewal at the current commit or higher. To use the full commit, monthly spend has to rise from $47K to about $180K. The pipeline deals become more likely to close once a workload is live.

### Step 8: Measure and learn

Northwind is in the helped group. After two quarters, its growth is compared with similar accounts in the comparison group, and the results feed back into the scoring weights and the Commit Burn Sprint playbook.

Walk through Northwind step by step on the Lifecycle page →

## Assumptions and limitations

The prototype shows a method; every item below is an assumption or simplification to calibrate with real data.

| Item | Status | Why it matters |
|---|---|---|
| Propensity score weights | Assumption | Set by judgment; should be tested against real outcomes |
| Type of help cutoffs (score 60, $250K) | Assumption | Chosen to fit the assumed team size |
| Alert thresholds | Assumption | Chosen by judgment; easy to change |
| On-track % status cutoffs (90%, 70%) | Assumption | Simple bands for readability |
| Team size (10 SAs, 4 FDEs) and loads | Assumption | Set to fit the prototype; change it with the slider |
| PS tiers and prices | Proposed | Real pricing would come from Finance and Professional Services |
| Impact example | Example | Shows how measurement would work, not a result |
| Even spending through the year | Simplification | Overstates risk for seasonal businesses like retail |
| Contract terms | Generic | Whether unused commit expires or rolls over varies by contract |
| Data freshness | Simplification | Real usage and billing data can lag by weeks |

The structure is designed to be calibrated with real Salesforce and usage data, real contract terms, and the team's actual capacity.

## Opportunities to explore

With real data and a team to run it, possibly we can take the prototype further in these directions:

| Opportunity | What it adds |
|---|---|
| Connect real Salesforce and warehouse data | Live scores instead of sample files |
| Test weights and cutoffs against history | Scores that are proven, not just reasonable |
| Machine learning propensity model | Better ranking once outcomes are tracked, with top reasons kept |
| Seasonality-adjusted on-track % | Fewer false alarms for retail and other seasonal accounts |
| Stage-weighted pipeline in the pool of funds | A more realistic pool of funds |
| Value per hour of SA and FDE time | Ranking by the best use of scarce people |
| Alerts sent to Slack and Salesforce | Faster action where teams already work |
| Engagement tracker as a Salesforce object | One place for engagement health and outcomes |
| Rotating comparison group | Ongoing, fair proof of impact |
| AI assistant that answers questions about any account | Faster answers for account teams, using a secure backend |

## Glossary and role mapping

### Glossary

| Term | Meaning |
|---|---|
| Propensity score | How likely an account is to grow in the next 90 days, from 0 to 100. |
| Pool of funds | Unused commit plus open pipeline. |
| Opportunity value | Propensity score × pool of funds; used to rank accounts. |
| Annual commit | What the customer promised to spend this contract year. |
| Unused commit | Commit promised but not yet used. |
| Open pipeline | Deals in progress, not yet signed. |
| Monthly spend | How much the customer uses per month: amount used ÷ months passed. |
| On-track % | Share of commit used compared to share of time passed; 100% = on track. 90% = slightly behind; below 50% = using it at under half the needed rate. |
| Behind by | How much less they've used than an even pace expects. |
| Needed monthly spend | Monthly spend needed to use the full commit by renewal. |
| Days to renewal | Days until the contract is up. |
| New builders | People at the customer who started building in the last 60 days, matched by company email domain. |
| Alerts | "Why now" rules that move an account up within its type of help. |
| Top reasons | The three signals that added most to the score. |
| Type of help | Deep engagement (SA + FDE), Strategic bet, Scaled SA programs, or Digital / self-serve. |
| Team capacity | How many accounts SAs and FDEs can support in a quarter: 10 SAs × 3 = 30 SA slots, 4 FDEs × 2 = 8 FDE slots (assumptions). |
| Comparison group | Similar accounts not helped, used to measure impact. 20% of qualifying accounts, chosen at random. |
| Impact | Extra growth in helped accounts compared with the comparison group. |
| SA | Solutions Architect: designs the approach and owns the technical relationship. |
| FDE | Forward Deployed Engineer: builds hands-on with the customer's developers. |

### How this maps to the role

| Section | Role responsibility it shows |
|---|---|
| Data | Salesforce CRM, BigQuery, CRM data; partner with Revenue Engineering and Data |
| Propensity score | Account propensity; identify the right customer opportunities |
| Pool of funds and opportunity value | Technical revenue pipeline; investment ROI; accelerate consumption |
| Alerts | Upcoming opportunities and blockers |
| Type of help and team capacity | SA/FDE prioritization, resourcing, and account coverage |
| Engagement and onsites | Coordinate strategic customer engagement; plan and scale technical onsite visits |
| Programs and the PS offer | Repeatable playbooks and operating rhythms; pricing, packaging, business cases, rollout plans |
| Measuring impact | Investment ROI; feedback loops; measurable programs |
| Operating rhythm and ownership | Incubate new motions until they are measurable and ready for durable ownership |

## Decision log

Each key judgment call in one place: what we decided, why, and what we could try next. Every number is read from the pipeline output.

### Scorecard weights

**Decision**

Propensity score = 35% usage growth + 30% new builders + 15% engagement + 20% product breadth, each bucketed to 0–100.

**Why**

Recent momentum is the strongest sign of near-term growth; more people building today usually means more workloads in production soon. Commit pressure is a risk, not growth, so it's an alert instead.

**Possibly we can**

Possibly we can test the weights against real history, then move to a machine learning model that keeps top reasons.

### Signal windows

**Decision**

Usage growth over 3 months; new builders over 60 days; meetings and calls over 90 days.

**Why**

Long enough to smooth out noise, short enough to reflect what the customer is doing now.

**Possibly we can**

Possibly we can count new builders only if they deployed something, and exclude automated accounts.

### Pool of funds formula

**Decision**

Pool of funds = unused commit + open pipeline; opportunity value = propensity score ÷ 100 × pool of funds.

**Why**

Unused commit is the most urgent money; pipeline is included because SA and FDE help often decides whether those deals close. Opportunity value is for ranking, not a forecast.

**Possibly we can**

Possibly we can weight pipeline by deal stage and divide opportunity value by the SA/FDE hours an account needs.

### Alert thresholds

**Decision**

Commit at risk below 70% On-track %; Renewal coming within 180 days for Enterprise and 90 days for everyone else; Builder surge 15+ in 60 days; Usage spike +50% in a month; Usage drop −30% over 3 months; New product in 60 days.

**Why**

Scores say who; alerts say when. Six alerts is enough, and each one has an owner and an action. Enterprise gets a longer renewal window because big contracts enter procurement months ahead; one 180-day window would flag half of all accounts.

**Possibly we can**

Possibly we can tune thresholds by checking which alerts led to real growth.

### On-track bands

**Decision**

On track at 90%+, Slightly behind at 70%–89%, Behind below 70%.

**Why**

Simple bands for readability; the Behind line matches the Commit at risk alert. On-track % assumes even spending, which overstates risk for seasonal businesses like retail.

**Possibly we can**

Possibly we can adjust On-track % for seasonality using spending curves from similar accounts.

### Type-of-help cut-offs

**Decision**

Propensity score 60+ and pool of funds $250K+.

**Why**

Two simple questions are easy to explain and easy to challenge; the cut-offs put roughly the right number of accounts in each type for the team's size.

**Possibly we can**

Possibly we can set cut-offs from data and use different cut-offs by segment.

### Team capacity

**Decision**

10 SAs × 3 accounts = 30 SA slots; 4 FDEs × 2 deep engagements = 8 FDE slots.

**Why**

Without a capacity limit, a priority list is a wish list. A visible cut-off line makes the trade-off clear.

**Possibly we can**

Possibly we can use real SA and FDE hours from the engagement tracker and plan capacity by region.

### Comparison group

**Decision**

20% of accounts that qualify for scaled help are chosen at random for the comparison group.

**Why**

Accounts with high scores often grow anyway; random selection makes the two groups alike, so the difference is fair.

**Possibly we can**

Possibly we can rotate the comparison group each quarter so no customer is left out for long.
