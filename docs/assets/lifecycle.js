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
    const total = ctx.accounts.accounts.length;
    const content = ctx.content;
    const offer = content.ps_offer;

    return [
      {
        name: "CRM Data",
        type: "data",
        what: "A nightly extract pulls Salesforce Account, Contract and Opportunity fields for every account.",
        decision: "None yet. This is the raw record every later decision is built on.",
        how: "Commit, consumption to date, contract dates and open pipeline are taken as-is, with nothing filtered out.",
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `${a.account_name} is ${article(a.segment)} ${a.segment} ${a.industry} account in ${a.region} with a ${usd(a.annual_commit_usd)} annual commit, ` +
          `${usd(a.commit_consumed_usd)} consumed ${pct(a.contract_elapsed_share)} of the way through its contract, renewing in ${a.days_to_renewal} days, ` +
          `with ${a.open_pipeline_usd > 0 ? `${usd(a.open_pipeline_usd)} in open pipeline` : "no open pipeline"}.`,
      },
      {
        name: "Usage Signals",
        type: "data",
        what: "Product telemetry is joined on: usage trend, recent spikes, developer activity and SA touchpoints.",
        decision: "None yet. These are the signals the score will weigh.",
        how: "Usage growth compares the last 90 days with the 90 before. The spike ratio compares the last 7 days with the 4-week average.",
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `Usage is ${a.usage_growth_90d_pct >= 0 ? "up" : "down"} ${Math.abs(a.usage_growth_90d_pct)}% over 90 days, ` +
          `the last 7 days ran at ${a.usage_spike_ratio}× the 4-week average, ${plural(a.new_developers_30d, "new developer")} joined in 30 days ` +
          `(${a.active_developers} active), and the SA team met them ${plural(a.sa_meetings_90d, "time")} in 90 days.`,
      },
      {
        name: "Propensity Score",
        type: "decision",
        what: "Each account gets a 0–100 score for how likely it is to expand if we invest technical time.",
        decision: "How likely is this account to grow with our help?",
        how: `Each signal becomes a percentile against all ${total} accounts, then is weighted: usage growth ${pct(w.usage_growth)}, ` +
          `new developers ${pct(w.new_developers)}, SA engagement ${pct(w.engagement)}, commit burn ${pct(w.commit_burn)}. ` +
          "The three biggest contributors become the reasons.",
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `${a.account_name} scores ${a.propensity_score}/100; its strongest signals are ${andList(a.top_reasons.map(lowerFirst))}.`,
      },
      {
        name: "Headroom & Flags",
        type: "decision",
        what: "Size what is at stake, weight it by likelihood, and raise flags that need action now.",
        decision: "How much is at stake, and is anything urgent?",
        how: `Headroom = unconsumed commit + open pipeline. Expected value = score / 100 × headroom. ` +
          `Flags: Commit at Risk (25%+ into the contract and burning below ${pct(t.commit_at_risk_max_pace)} of pace), ` +
          `Renewal Window (≤ ${t.renewal_window_days} days), Usage Spike (≥ ${t.usage_spike_ratio}× normal), ` +
          `New Developers (≥ ${t.new_developers_min} in 30 days).`,
        screen: ["prioritization.html", "#selected"],
        sentence: (a) =>
          `Headroom is ${usd(a.headroom_usd)} (${usd(a.unconsumed_commit_usd)} unused commit + ${usd(a.open_pipeline_usd)} open pipeline), ` +
          `worth ${usd(a.expected_value_usd)} in expected value at a score of ${a.propensity_score}; ` +
          `${a.flags.length ? `flags raised: ${andList(a.flags)}` : "no flags raised"}.`,
      },
      {
        name: "Prioritize & Route",
        type: "decision",
        what: "Rank every account by expected value, place it in a quadrant, and check it against SA/FDE capacity.",
        decision: "Which engagement motion does this account get?",
        how: `Score ≥ ${t.score_high} and headroom ≥ ${usd(t.headroom_high)} set the quadrant. Capacity covers the top ${t.capacity_top_n} ` +
          "by expected value. FDE Deep Engagement and Strategic Bets need capacity; the other quadrants use scaled motions.",
        screen: ["prioritization.html", "#matrix"],
        sentence: (a) =>
          `Ranked #${a.priority_rank} of ${total} by expected value, ${a.account_name} falls in ${a.quadrant} and ` +
          `${a.in_capacity ? "inside" : "outside"} the top-${t.capacity_top_n} capacity line, so its motion is: ${a.motion}.`,
      },
      {
        name: "Engage & Onsite",
        type: "action",
        what: "Open a tracked engagement with one goal, one owner, a status and a next step. Plan an onsite where a technical decision is stuck.",
        decision: "Who owns it, and what happens next?",
        how: "Accounts on a dedicated motion get a tracked engagement. Onsites are reserved for FDE Deep Engagement accounts with a clear technical decision to make.",
        screen: ["engagement.html", "#selected"],
        sentence: (a) => {
          const e = content.engagements.find((x) => x.account === a.account_name);
          if (!e) {
            return `${a.account_name} has no tracked engagement: as a ${a.quadrant} account ${a.in_capacity ? "inside" : "outside"} capacity, ` +
              `its motion is: ${a.motion}.`;
          }
          const status = { green: "on track", yellow: "at risk", red: "blocked" }[e.status];
          return `${a.account_name} has an active engagement (owner ${e.owner}) to ${lowerFirst(e.goal)}; it is ${status}, and the next step is: ${lowerFirst(e.next_step)}.`;
        },
      },
      {
        name: "Program & PS Offer",
        type: "action",
        what: "Scale what works: a data-triggered SA program for flagged accounts, and a packaged services offer where hands-on delivery is needed.",
        decision: "Does it need a program, a paid services package, or neither?",
        how: `Commit at Risk triggers the ${content.program.name} (led by the FDE/SA instead when the account is inside capacity). ` +
          `${offer.name} is offered to Commit at Risk accounts and Strategic Bets, with the tier set by unused commit: ` +
          `Assess under ${usd(t.ps_assess_below)}, Migrate under ${usd(t.ps_migrate_below)}, Scale above.`,
        screen: ["programs.html", "#selected"],
        sentence: (a) => {
          const program = a.program
            ? `Burning commit at ${pct(a.burn_pace)} of pace, ${a.account_name} is flagged Commit at Risk and gets ${a.program === content.program.name ? "the " : ""}${a.program}`
            : `${a.account_name} is not flagged Commit at Risk, so no burn-recovery program applies`;
          const tier = offer.tiers.find((x) => x.tier === a.ps_recommended_tier);
          const ps = tier
            ? `; recommended services: the ${tier.tier} tier of the ${offer.name} (${tier.duration}, ${usd(tier.price_usd)} indicative).`
            : "; no services package is recommended.";
          return program + ps;
        },
      },
      {
        name: "Measure & Write-back",
        type: "action",
        what: "Push every decision back to Salesforce and prove the time paid off.",
        decision: "Did our time create revenue we would not have had otherwise?",
        how: "Score, reasons, rank, quadrant, flags, motion and PS tier are written to Account fields. Impact is measured against a randomized holdout of similar accounts, so only incremental lift counts as ROI.",
        screen: ["prioritization.html", "#kpis"],
        sentence: (a) => {
          const metric = a.program
            ? `burn pace (now ${pct(a.burn_pace)}) recovering above 90%`
            : `usage growth (now ${a.usage_growth_90d_pct >= 0 ? "+" : ""}${a.usage_growth_90d_pct}%) and expansion at renewal`;
          return `We write score ${a.propensity_score}, rank #${a.priority_rank}, quadrant (${a.quadrant}) and ` +
            `flags (${a.flags.length ? a.flags.join(", ") : "none"}) to ${a.account_name}'s Salesforce record, ` +
            `then track ${metric} against a holdout of similar accounts.`;
        },
      },
    ];
  }

  return { steps, STEP_TYPES };
})();
