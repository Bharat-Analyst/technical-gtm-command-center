// The 8 lifecycle steps (as described on "How this works"), shared by the
// walkthrough (index.html) and the "selected account" callouts on other pages.
// Every number comes from docs/data/*.json.
//
// Each step has:
//   type      data | decision | action   (drives the color coding)
//   what      what happens at this step
//   decision  the question this step answers
//   how       how we decide (thresholds read from the pipeline's meta)
//   screen    the page that shows this step, plus an anchor on that page
//   jd        jd_mapping.json step names this lifecycle step demonstrates
//   why       decisions.json ids behind this step
//   sentence  this account's real values, as one plain-English sentence

const LIFECYCLE = (function () {
  const usd = (n) => GTM.usd(n);
  const pct = (x) => GTM.pct(x);
  const lowerFirst = (s) => s.charAt(0).toLowerCase() + s.slice(1);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const article = (word) => (/^[aeiou]/i.test(word) ? "an" : "a");
  const andList = (items) =>
    items.length <= 1 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;

  const STEP_TYPES = { data: "Data", decision: "Decision", action: "Action & revenue" };

  // ctx = { accounts: accounts.json, content: content.json }
  function steps(ctx) {
    const meta = ctx.accounts.meta;
    const t = meta.thresholds, w = meta.weights, win = meta.signal_windows, cap = meta.capacity;
    const [DEEP, BET] = meta.quadrants;
    const total = ctx.accounts.accounts.length;
    const content = ctx.content;
    const offer = content.ps_offer;
    const status = (p) => (p >= t.on_track_good ? "on track" : p >= t.on_track_warn ? "slightly behind" : "behind");

    return [
      {
        name: "Data comes in", type: "data", jd: ["Data comes in"], why: [],
        what: "Salesforce and product usage data arrive on a schedule.",
        decision: "None yet. This is the record every later decision is built on.",
        how: "Account, contract, opportunity and activity data from Salesforce; monthly spend by product from usage; self-serve signups by company email domain.",
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `${a.account_name} is ${article(a.segment)} ${a.segment} ${a.industry} account in ${a.region} with a ${usd(a.annual_commit_usd)} annual commit, ` +
          `${usd(a.commit_consumed_usd)} used so far, ${a.days_to_renewal} days to renewal and ` +
          `${a.open_pipeline_usd > 0 ? `${usd(a.open_pipeline_usd)} in open pipeline` : "no open pipeline"}.`,
      },
      {
        name: "Clean and combine", type: "data", jd: ["Clean and combine"], why: [],
        what: "Messy records are fixed and each company becomes one row.",
        decision: "None yet. Which records belong to the same company?",
        how: "Duplicate accounts are merged, child accounts are rolled up to their parent, industries are standardized, usage is matched to the right account, and signups are matched by email domain. Usage that can't be matched is logged, not dropped.",
        screen: ["prioritization.html", "#selected"],
        sentence: (a) => {
          const parts = [`usage from ${plural(a.billing_accounts.length, "billing account")} rolled into one row`];
          if (a.child_accounts.length) parts.push(`child account ${andList(a.child_accounts)} rolled up`);
          if (a.duplicates_merged) parts.push(`${plural(a.duplicates_merged, "duplicate record")} merged`);
          parts.push(`${plural(a.new_builders_60d, "self-serve signup")} in the last ${win.new_builders_days} days matched by email domain`);
          return `For ${a.account_name}: ${andList(parts)}.`;
        },
      },
      {
        name: "Score propensity", type: "decision", jd: ["Propensity score"], why: ["weights", "windows"],
        what: "Each account gets a 0–100 score for how likely it is to grow.",
        decision: "Who is likely to grow?",
        how: `Usage growth (${pct(w.usage_growth)}), new builders (${pct(w.new_builders)}), meetings and calls (${pct(w.engagement)}) ` +
          `and product breadth (${pct(w.product_breadth)}) are each scored 0–100 from simple buckets, then weighted. The three signals that add the most points become the top reasons.`,
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `${a.account_name} scores ${a.propensity_score}: usage ${a.usage_growth_3m >= 0 ? "up" : "down"} ${pct(Math.abs(a.usage_growth_3m))} (${a.points_usage_growth} points), ` +
          `${plural(a.new_builders_60d, "new builder")} (${a.points_new_builders}), ${a.meetings_90d} meetings and calls (${a.points_engagement}) ` +
          `and ${plural(a.product_count, "product")} (${a.points_product_breadth}).`,
      },
      {
        name: "Size the prize", type: "decision", jd: ["Pool of funds", "Opportunity value"], why: ["pool-of-funds", "on-track-bands"],
        what: "Pool of funds and opportunity value are calculated.",
        decision: "Is it worth our time?",
        how: "Pool of funds = unused commit + open pipeline. Opportunity value = propensity score ÷ 100 × pool of funds. On-track % shows how the commit is going.",
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `The pool of funds is ${usd(a.pool_of_funds)} (${GTM.poolBreakdown(a)}), so the opportunity value is ${usd(a.expected_value_usd)}, rank #${a.priority_rank} of ${total}; ` +
          `On-track % is ${pct(a.burn_pace)} (${status(a.burn_pace)}), with ${usd(a.burn_rate_monthly)} monthly spend against ${usd(a.required_monthly_burn)} needed.`,
      },
      {
        name: "Alert and prioritize", type: "decision", jd: ["Alerts", "Prioritization matrix", "Team capacity"], why: ["flags", "quadrants", "capacity"],
        what: "Alerts add urgency, each account gets a type of help, and team capacity sets the cut-off.",
        decision: "Where do SAs and FDEs go?",
        how: `Propensity score ${t.score_high}+ and pool of funds ${usd(t.pool_of_funds_high)}+ set the type of help. ` +
          `${cap.fde_slots} FDE slots go to the top ${DEEP} accounts; the rest of the ${cap.sa_slots} SA slots go to ${DEEP} and ${BET} accounts. Within each type, accounts with alerts move up.`,
        screen: ["prioritization.html", "#matrix"],
        sentence: (a) =>
          `${a.account_name} has ${a.flags.length ? `${plural(a.flags.length, "alert")} (${a.flags.join(", ")})` : "no alerts"}, ` +
          `type of help ${a.quadrant}${a.override_reason ? " (by logged override)" : ""}, and coverage: ${a.coverage}.`,
      },
      {
        name: "Engage the customer", type: "action", jd: ["Engagement tracker", "Onsite planner"], why: [],
        what: "The team runs the right play: deep engagement, a scaled program, discovery, or self-serve.",
        decision: "What kind of help?",
        how: "Every engagement has a goal, named owners, success criteria and a next step in one tracker. Onsites run in five stages, from intake to follow-up and measurement.",
        screen: ["engagement.html", "#selected"],
        sentence: (a) => {
          const e = content.engagements.find((x) => x.account === a.account_name);
          if (!e) return `${a.account_name} has no tracked engagement; its help plan is: ${lowerFirst(a.motion)}.`;
          const st = { green: "on track", yellow: "at risk", red: "blocked" }[e.status];
          return `${a.account_name}'s engagement aims to ${lowerFirst(e.goal)} (SA ${e.sa}${e.fde ? `, FDE ${e.fde}` : ""}); it is ${st}, and the next step is: ${lowerFirst(e.next_step)}.`;
        },
      },
      {
        name: "Revenue", type: "action", jd: ["Program playbook", "PS offer"], why: ["flags"],
        what: "Workloads reach production and consumption grows.",
        decision: "Is a program or a packaged service the right path?",
        how: `The ${content.program.name} runs for Commit at risk accounts with ${usd(t.sprint_min_unused)}+ unused commit. ` +
          `The ${offer.name} packages deeper hands-on work in three tiers.`,
        screen: ["programs.html", "#selected"],
        sentence: (a) => {
          const prog = a.holdout ? `${a.account_name} is in the comparison group (normal service only)`
            : a.program ? `${a.account_name} is in the ${a.program}`
            : `${a.account_name} isn't in a program`;
          const tier = offer.tiers.find((x) => x.tier === a.ps_recommended_tier);
          return `${prog}; to use its full commit it needs ${usd(a.required_monthly_burn)} a month vs ${usd(a.burn_rate_monthly)} today` +
            (tier ? `, and the ${tier.tier} tier of the ${offer.name} (${tier.duration}, ${usd(tier.price_usd)}) is the recommended path.` : ".");
        },
      },
      {
        name: "Measure and learn", type: "action", jd: ["Executive view", "Measure and learn", "Hand off to an owner"], why: ["holdout"],
        what: "Helped accounts are compared with a similar group that wasn't helped, and the scoring is updated.",
        decision: "Did it work, and what do we change?",
        how: `${pct(meta.holdout_share)} of qualifying accounts are chosen at random as a comparison group. Impact is the extra growth in the helped group; it feeds back into weights, alerts and programs each quarter.`,
        screen: ["executive.html", "#measure"],
        sentence: (a) =>
          a.holdout
            ? `${a.account_name} is in the comparison group: its growth is the baseline the helped accounts are measured against.`
            : `${a.account_name}'s monthly spend (now ${usd(a.spend_last_month)} last month) and On-track % (${pct(a.burn_pace)}) are tracked for two quarters and compared with the comparison group.`,
      },
    ];
  }

  return { steps, STEP_TYPES };
})();
