// The 8 lifecycle steps, shared by the walkthrough (index.html) and the
// "selected account" callouts on other pages, so every page describes an
// account in the same words. Every number comes from docs/data/*.json.
//
// Each step has:
//   type      data | decision | action   (drives the color coding)
//   what      what happens at this step
//   decision  the question this step answers
//   how       how we decide (thresholds read from the pipeline's meta)
//   screen    the page that shows this step, plus an anchor on that page
//   jd        jd_mapping.json step names this lifecycle step demonstrates
//   why       decision-log entries (decisions.json ids) behind this step
//   sentence  this account's real values, as one plain-English sentence

const LIFECYCLE = (function () {
  const usd = (n) => GTM.usd(n);
  const pct = (x) => GTM.pct(x);
  const lowerFirst = (s) => s.charAt(0).toLowerCase() + s.slice(1);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const article = (word) => (/^[aeiou]/i.test(word) ? "an" : "a");
  const andList = (items) =>
    items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;

  const STEP_TYPES = {
    data: "Data",
    decision: "Decision",
    action: "Action & revenue",
  };

  // ctx = { accounts: accounts.json, content: content.json }
  function steps(ctx) {
    const meta = ctx.accounts.meta;
    const t = meta.thresholds;
    const w = meta.weights;
    const win = meta.signal_windows_days;
    // Type-of-help names come from the pipeline: [high/high, high/low, low/high, low/low].
    const [Q_DEEP, , Q_BET] = meta.quadrants;
    const total = ctx.accounts.accounts.length;
    const content = ctx.content;
    const offer = content.ps_offer;
    const status = (pace) => (pace >= t.on_track_good ? "on track" : pace >= t.on_track_warn ? "slightly behind" : "behind");

    return [
      {
        name: "CRM Data",
        type: "data",
        jd: ["Data comes in"],
        why: [],
        what: "A nightly extract pulls Salesforce Account, Contract and Opportunity fields for every account.",
        decision: "None yet. This is the raw record every later decision is built on.",
        how: "Commit, spend to date, contract dates and open pipeline are taken as-is, with nothing filtered out.",
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `${a.account_name} is ${article(a.segment)} ${a.segment} ${a.industry} account in ${a.region} with a ${usd(a.annual_commit_usd)} annual commit, ` +
          `${usd(a.commit_consumed_usd)} used so far with ${pct(a.contract_elapsed_share)} of the contract year passed, renewing in ${a.days_to_renewal} days, ` +
          `with ${a.open_pipeline_usd > 0 ? `${usd(a.open_pipeline_usd)} in open pipeline` : "no open pipeline"}.`,
      },
      {
        name: "Usage Signals",
        type: "data",
        jd: ["Data comes in", "Clean and combine"],
        why: ["windows"],
        what: "Product usage is joined on: usage trend, recent spikes, new builders and SA meetings.",
        decision: "None yet. These are the signals the Propensity score will weigh.",
        how: `Usage growth compares the last ${win.usage_growth} days with the ${win.usage_growth} before. ` +
          `The spike check compares the last ${t.usage_spike_recent_days} days with the ${t.usage_spike_baseline_days}-day average.`,
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `Usage is ${a.usage_growth_90d_pct >= 0 ? "up" : "down"} ${Math.abs(a.usage_growth_90d_pct)}% over ${win.usage_growth} days, ` +
          `the last ${t.usage_spike_recent_days} days ran at ${a.usage_spike_ratio}× the ${t.usage_spike_baseline_days}-day average, ` +
          `${plural(a.new_developers_30d, "new builder")} started in ${win.new_developers} days (${a.active_developers} active), ` +
          `and the SA team met them ${plural(a.sa_meetings_90d, "time")} in ${win.engagement} days.`,
      },
      {
        name: "Propensity Score",
        type: "decision",
        jd: ["Propensity score"],
        why: ["weights"],
        what: "Each account gets a 0–100 Propensity score for how likely it is to grow if we invest technical time.",
        decision: "How likely is this account to grow with our help?",
        how: `Each signal becomes a percentile against all ${total} accounts, then is weighted: usage growth ${pct(w.usage_growth)}, ` +
          `new builders ${pct(w.new_developers)}, SA engagement ${pct(w.engagement)}, On-track % ${pct(w.commit_burn)}. ` +
          "The three biggest contributors become the top reasons.",
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `${a.account_name} has a Propensity score of ${a.propensity_score}/100; its strongest signals are ${andList(a.top_reasons.map(lowerFirst))}.`,
      },
      {
        name: "Pool of Funds & Alerts",
        type: "decision",
        jd: ["Pool of funds", "Opportunity value", "Alerts"],
        why: ["pool-of-funds", "flags", "on-track-bands"],
        what: "Size what is at stake, weight it by likelihood, and raise alerts that need action now.",
        decision: "How much is at stake, and is anything urgent?",
        how: `Pool of funds = unused commit + open pipeline. Opportunity value = Propensity score ÷ 100 × Pool of funds. ` +
          `Alerts: Commit at Risk (On-track % below ${pct(t.commit_at_risk_max_pace)} after ${pct(t.commit_at_risk_min_elapsed)} of the contract), ` +
          `Days to renewal (within ${t.renewal_window_days} days), Usage Spike (${t.usage_spike_ratio}× normal), ` +
          `New builders (${t.new_developers_min}+ in ${win.new_developers} days).`,
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `The Pool of funds is ${usd(a.pool_of_funds)} (${GTM.poolBreakdown(a)}), an Opportunity value of ${usd(a.expected_value_usd)} ` +
          `at a Propensity score of ${a.propensity_score}; On-track % is ${pct(a.burn_pace)} (${status(a.burn_pace)}), ` +
          `${a.behind_pace_amount > 0 ? `behind by ${usd(a.behind_pace_amount)}` : "not behind"}; ` +
          `${a.flags.length ? `alerts: ${andList(a.flags)}` : "no alerts"}.`,
      },
      {
        name: "Prioritize & Route",
        type: "decision",
        jd: ["Prioritization matrix", "Team capacity"],
        why: ["quadrants", "capacity"],
        what: "Rank every account by Opportunity value, decide its type of help, and check it against team capacity.",
        decision: "Which type of help does this account get?",
        how: `A Propensity score of ${t.score_high}+ and a Pool of funds of ${usd(t.pool_of_funds_high)}+ set the type of help. ` +
          `Team capacity covers the top ${t.capacity_top_n} by Opportunity value. ${Q_DEEP} and ${Q_BET} need team capacity; the other types are scaled.`,
        screen: ["prioritization.html", "#matrix"],
        sentence: (a) =>
          `Ranked #${a.priority_rank} of ${total} by Opportunity value, ${a.account_name} gets ${a.quadrant} as its type of help and is ` +
          `${a.in_capacity ? "inside" : "outside"} the top-${t.capacity_top_n} team capacity line, so its help plan is: ${a.motion}.`,
      },
      {
        name: "Engage & Onsite",
        type: "action",
        jd: ["Engagement tracker", "Onsite planner"],
        why: [],
        what: "Open a tracked engagement with one goal, one owner, a status and a next step. Plan an onsite where a technical decision is stuck.",
        decision: "Who owns it, and what happens next?",
        how: `Accounts with dedicated help get a tracked engagement. Onsites are reserved for ${Q_DEEP} accounts with a clear technical decision to make.`,
        screen: ["engagement.html", "#selected"],
        sentence: (a) => {
          const e = content.engagements.find((x) => x.account === a.account_name);
          if (!e) {
            return `${a.account_name} has no tracked engagement: its type of help is ${a.quadrant} (${a.in_capacity ? "inside" : "outside"} team capacity), ` +
              `so its help plan is: ${a.motion}.`;
          }
          const st = { green: "on track", yellow: "at risk", red: "blocked" }[e.status];
          return `${a.account_name} has an active engagement (owner ${e.owner}) to ${lowerFirst(e.goal)}; it is ${st}, and the next step is: ${lowerFirst(e.next_step)}.`;
        },
      },
      {
        name: "Program & PS Offer",
        type: "action",
        jd: ["Program playbook", "PS offer"],
        why: ["flags", "holdout"],
        what: "Scale what works: a data-triggered SA program for accounts behind on commit, and a packaged services offer where hands-on delivery is needed.",
        decision: "Does it need a program, a paid services package, or neither?",
        how: `The Commit at Risk alert triggers the ${content.program.name} (led by the account's own SA/FDE when it is inside team capacity). ` +
          `${offer.name} is offered to Commit at Risk accounts and ${Q_BET}s, with the tier set by unused commit: ` +
          `Assess under ${usd(t.ps_assess_below)}, Migrate under ${usd(t.ps_migrate_below)}, Scale above.`,
        screen: ["programs.html", "#selected"],
        sentence: (a) => {
          const needed = `it needs ${usd(a.required_monthly_burn)}/month to use its commit by renewal vs. ${usd(a.burn_rate_monthly)}/month today`;
          const program = a.holdout
            ? `At ${pct(a.burn_pace)} On-track %, ${a.account_name} has the Commit at Risk alert (${needed}) but was randomly picked for the comparison group, so it is measured, not enrolled`
            : a.program
            ? `At ${pct(a.burn_pace)} On-track %, ${a.account_name} has the Commit at Risk alert (${needed}) and gets ${a.program === content.program.name ? "the " : "an "}${a.program}`
            : `${a.account_name} has no Commit at Risk alert, so no catch-up program applies`;
          const tier = offer.tiers.find((x) => x.tier === a.ps_recommended_tier);
          const ps = tier
            ? `; recommended services: the ${tier.tier} tier of the ${offer.name} (${tier.duration}, ${usd(tier.price_usd)}).`
            : "; no services package is recommended.";
          return program + ps;
        },
      },
      {
        name: "Measure & Write-back",
        type: "action",
        jd: ["Executive view", "Measure and learn", "Hand off to an owner"],
        why: ["holdout"],
        what: "Push every decision back to Salesforce and prove the time paid off.",
        decision: "Did our time create revenue we would not have had otherwise?",
        how: "Propensity score, top reasons, rank, type of help, alerts, help plan and PS tier are written to Account fields. " +
          "Impact is measured against a random comparison group of similar accounts, so only the extra improvement counts as ROI.",
        screen: ["executive.html", "#measure"],
        sentence: (a) => {
          const metric = a.program
            ? `On-track % (now ${pct(a.burn_pace)}) moving back toward ${pct(t.on_track_good)}`
            : `usage growth (now ${a.usage_growth_90d_pct >= 0 ? "+" : ""}${a.usage_growth_90d_pct}%) and expansion at renewal`;
          return `We write Propensity score ${a.propensity_score}, rank #${a.priority_rank}, type of help (${a.quadrant}) and ` +
            `alerts (${a.flags.length ? a.flags.join(", ") : "none"}) to ${a.account_name}'s Salesforce record, ` +
            (a.holdout
              ? `then use its ${metric.split(" (")[0]} as the baseline the enrolled accounts are compared against.`
              : `then track ${metric} against a comparison group of similar accounts.`);
        },
      },
    ];
  }

  return { steps, STEP_TYPES };
})();
