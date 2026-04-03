/**
 * POST /api/letters/generate
 *
 * Generates a personalized Next Chapter letter from meeting data + buyer research.
 * Runs the same LetterTemplateEngine logic server-side so output is identical to
 * the client-side engine in /public/letter-template.js.
 *
 * Request body:
 *   {
 *     company_id:          string,
 *     meeting_data:        Object,   // from MeetingForm.getFormData()
 *     buyer_research_data: Object,   // from researcher agent
 *     opts?: {
 *       ownerName?:   string,
 *       companyName?: string,
 *       vertical?:    string,
 *     }
 *   }
 *
 * Response (200):
 *   {
 *     letter_text:               string,
 *     personalization_score:     number,   // 0.0–1.0
 *     score_breakdown:           Object,
 *     tone_signal:               string,   // "urgent" | "warm" | "exploratory"
 *     estimated_valuation_range: Object,
 *     readiness_label:           string,   // "Production Ready" | "Good" | "Needs Refinement"
 *   }
 */

// Credentials: all keys come from env vars. See .env.example for names.
// Vercel injects these at runtime. Local dev: copy .env.example to .env

const path = require('path');
const fs = require('fs');

// ---------------------------------------------------------------------------
// Config-driven valuation multiples — loaded from vertical config JSON
// Single source of truth: lib/config/verticals/home_services.json
// ---------------------------------------------------------------------------

function loadMultiplesFromConfig() {
  try {
    const configPath = path.resolve(__dirname, '../../lib/config/verticals/home_services.json');
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    const base = config.valuation_fields || {};
    const subs = config.sub_verticals || {};
    const multiples = {};

    // Build from sub-verticals
    for (const [slug, sv] of Object.entries(subs)) {
      const svVf = sv.valuation_fields || {};
      multiples[slug] = {
        floor:   svVf.multiple_floor   || base.multiple_floor   || 4.0,
        ceiling: svVf.multiple_ceiling  || base.multiple_ceiling || 7.0,
        median:  svVf.multiple_median   || base.multiple_median  || 5.5,
      };
    }
    // Base/default
    multiples.default = {
      floor:   base.multiple_floor   || 4.0,
      ceiling: base.multiple_ceiling || 7.0,
      median:  base.multiple_median  || 5.5,
    };
    return multiples;
  } catch (e) {
    // Fallback if config file not available (e.g. during build)
    return null;
  }
}

// Legacy fallback — used only when vertical config is unavailable
const LEGACY_MULTIPLES = {
  water_treatment:  { floor: 4.0, ceiling: 8.0,  median: 5.5  },
  hvac:             { floor: 4.5, ceiling: 8.5,  median: 6.0  },
  plumbing:         { floor: 4.0, ceiling: 7.5,  median: 5.5  },
  roofing:          { floor: 3.5, ceiling: 7.0,  median: 5.0  },
  pest_control:     { floor: 5.0, ceiling: 10.0, median: 7.0  },
  concrete_precast: { floor: 4.0, ceiling: 7.5,  median: 5.5  },
  flooring:         { floor: 3.5, ceiling: 6.5,  median: 4.75 },
  default:          { floor: 4.0, ceiling: 7.0,  median: 5.5  },
};

const VERTICAL_MULTIPLES = loadMultiplesFromConfig() || LEGACY_MULTIPLES;

// Valuation metric label — from config primary_metric
const VALUATION_METRIC = (() => {
  try {
    const configPath = path.resolve(__dirname, '../../lib/config/verticals/home_services.json');
    const config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
    const metric = (config.valuation_fields || {}).primary_metric || 'ebitda';
    return { ebitda: 'EBITDA', revenue: 'revenue', arr: 'ARR', sde: 'SDE' }[metric] || 'EBITDA';
  } catch (e) { return 'EBITDA'; }
})();

const SCORE_THRESHOLDS = { production: 0.80, good: 0.60 };

// ---- helpers ----------------------------------------------------------------

function hasContent(val) {
  return val && typeof val === 'string' && val.trim().length > 5;
}

function formatDollar(n) {
  if (!n || isNaN(n)) return '';
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
  if (n >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

function readinessLabel(score) {
  if (score >= SCORE_THRESHOLDS.production) return 'Production Ready';
  if (score >= SCORE_THRESHOLDS.good)       return 'Good';
  return 'Needs Refinement';
}

function timelineToPhrase(timeline) {
  const map = {
    '3months':  '3-month timeline',
    '6months':  '6-month runway',
    '12months': '12-month window',
    '18months': '18-month horizon',
    '24months': '2-year horizon',
    'none':     'exploratory mindset',
  };
  return map[timeline] || (timeline ? `${timeline} timeline` : '');
}

function dealBreakerNarrative(dealBreakers) {
  const labels = {
    whole_company:     'selling the whole company',
    not_customer_list: 'not just selling a customer list',
    stay_operator:     'having a path to stay involved as an operator',
    full_proceeds:     'receiving full cash proceeds at close',
    keep_employees:    'protecting your team',
    maintain_location: 'keeping the location intact',
  };
  const active = Object.entries(dealBreakers || {})
    .filter(([, v]) => v === true)
    .map(([k]) => labels[k] || k.replace(/_/g, ' '));
  if (active.length === 0) return 'the right structure';
  if (active.length === 1) return active[0];
  const last = active.pop();
  return `${active.join(', ')} and ${last}`;
}

function sumAddbacks(meetingData) {
  const p = meetingData.owner_perks || {};
  return (p.vehicle_allowance    || 0)
       + (p.family_salary        || 0)
       + (p.travel_entertainment || 0)
       + (p.insurance_benefits   || 0);
}

// ---- scoring ----------------------------------------------------------------

function computeScore(meetingData, buyerResearch) {
  const breakdown = {};

  // 0.30 — story elements
  const story = meetingData.story_elements || {};
  const storyFields = ['origin', 'challenge', 'culture', 'community', 'personal', 'quirky'];
  const storyFilled = storyFields.filter(k => story[k] && story[k].trim().length > 10).length;
  breakdown.story_elements = parseFloat((Math.min(storyFilled / 2, 1) * 0.30).toFixed(3));

  // 0.30 — buyer research
  const buyerSignals = [
    hasContent(buyerResearch.acquisition_history),
    hasContent(buyerResearch.strategic_rationale),
    hasContent(buyerResearch.approach_strategy),
  ].filter(Boolean).length;
  breakdown.buyer_research = parseFloat(((buyerSignals / 3) * 0.30).toFixed(3));

  // 0.20 — timeline/motivation match
  const hasMeetingMotivation  = hasContent(meetingData.motivation_type);
  const hasBuyerDealStructure = hasContent(buyerResearch.deal_structure)
    || hasContent(buyerResearch.typical_deal_structure)
    || hasContent(buyerResearch.approach_strategy);
  breakdown.timeline_match = parseFloat(
    ((hasMeetingMotivation ? 0.10 : 0) + (hasBuyerDealStructure ? 0.10 : 0)).toFixed(3)
  );

  // 0.10 — deal-breakers addressed
  const activeDealBreakers = Object.values(meetingData.deal_breakers || {}).filter(Boolean).length;
  const dealBreakersAddressed = hasContent(buyerResearch.deal_breaker_alignment)
    || hasContent(buyerResearch.approach_strategy);
  breakdown.deal_breakers = parseFloat(
    (activeDealBreakers > 0 && dealBreakersAddressed ? 0.10 : activeDealBreakers > 0 ? 0.05 : 0.10).toFixed(3)
  );

  // 0.10 — financial detail
  const hasRevenue = (meetingData.annual_revenue || 0) > 0;
  const hasEbitda  = (meetingData.estimated_ebitda || 0) > 0 || (meetingData.ebitda_margin || 0) > 0;
  breakdown.financial_detail = parseFloat(
    (((hasRevenue ? 1 : 0) + (hasEbitda ? 1 : 0)) / 2 * 0.10).toFixed(3)
  );

  const total = parseFloat(
    Object.values(breakdown).reduce((s, v) => s + v, 0).toFixed(2)
  );
  return { total, breakdown };
}

// ---- valuation --------------------------------------------------------------

function computeValuationRange(meetingData, vertical) {
  const multiples = VERTICAL_MULTIPLES[vertical] || VERTICAL_MULTIPLES.default;

  let ebitda = null;
  if (meetingData.estimated_ebitda && meetingData.estimated_ebitda > 0) {
    ebitda = meetingData.estimated_ebitda + sumAddbacks(meetingData);
  } else if (meetingData.annual_revenue && meetingData.ebitda_margin) {
    ebitda = (meetingData.annual_revenue * (meetingData.ebitda_margin / 100)) + sumAddbacks(meetingData);
  }

  if (!ebitda || ebitda <= 0) {
    return { low: null, mid: null, high: null, ebitda_used: null, note: 'Insufficient financial data' };
  }

  const recurringPct    = meetingData.recurring_revenue_percentage || meetingData.recurring_revenue || 0;
  const premiumFactor   = recurringPct >= 60 ? 0.5 : recurringPct >= 40 ? 0.25 : 0;
  const floorMultiple   = multiples.floor;
  const ceilingMultiple = multiples.ceiling + premiumFactor;
  const medianMultiple  = multiples.median  + premiumFactor * 0.5;

  return {
    low:              Math.round(ebitda * floorMultiple   / 100000) * 100000,
    mid:              Math.round(ebitda * medianMultiple  / 100000) * 100000,
    high:             Math.round(ebitda * ceilingMultiple / 100000) * 100000,
    ebitda_used:      ebitda,
    multiple_floor:   floorMultiple,
    multiple_ceiling: ceilingMultiple,
    multiple_median:  medianMultiple,
    recurring_premium: premiumFactor > 0,
  };
}

// ---- tone -------------------------------------------------------------------

function computeTone(meetingData) {
  const readiness  = meetingData.emotional_readiness || meetingData.readiness_scale || 5;
  const motivation = meetingData.motivation_type || '';
  const timeline   = meetingData.timeline || meetingData.timeline_type || '';

  if (readiness >= 8 || timeline === '3months' || motivation === 'retirement') return 'urgent';
  if (readiness >= 6 || timeline === '6months' || timeline === '12months')     return 'warm';
  return 'exploratory';
}

// ---- letter paragraphs ------------------------------------------------------

function buildParagraph1(meetingData, companyName, buyerName, buyerResearch) {
  const story = meetingData.story_elements || {};
  let storyHook = '';
  if (story.origin && story.origin.trim()) {
    storyHook = `${story.origin.trim()} `;
  } else if (story.challenge && story.challenge.trim()) {
    storyHook = `The way you've navigated ${story.challenge.trim()} is exactly the kind of story that gets a buyer's attention. `;
  }

  const strategicRat = buyerResearch.strategic_rationale ? `${buyerResearch.strategic_rationale.trim()} ` : '';
  const buyerContext  = hasContent(buyerResearch.company_overview) ? `${buyerResearch.company_overview.trim()} ` : '';
  const fitStatement  = strategicRat || buyerContext
    ? `That's precisely why ${buyerName} belongs in this conversation — ${strategicRat || buyerContext}`
    : `That combination is exactly what buyers like ${buyerName} are looking for right now. `;

  return `${storyHook}${fitStatement}I wanted to reach out directly because I believe there is a genuine fit between what you've built at ${companyName} and what ${buyerName} is actively pursuing.`;
}

function buildParagraph2(meetingData, companyName, buyerName, buyerResearch, valuation) {
  const parts = [];

  if (meetingData.annual_revenue && meetingData.annual_revenue > 0) {
    const revFormatted = formatDollar(meetingData.annual_revenue);
    let financialLine = `${companyName} is running ${revFormatted} in annual revenue`;
    if (meetingData.ebitda_margin && meetingData.ebitda_margin > 0) {
      financialLine += ` with ${meetingData.ebitda_margin}% EBITDA margins`;
    } else if (valuation.ebitda_used) {
      financialLine += ` generating ${formatDollar(valuation.ebitda_used)} in adjusted EBITDA`;
    }
    if (meetingData.growth_rate && meetingData.growth_rate > 0) {
      financialLine += ` and ${meetingData.growth_rate}% year-over-year growth`;
    }
    financialLine += ' — numbers that will stand up in any quality of earnings process.';
    parts.push(financialLine);
  }

  const kp = meetingData.key_people || {};
  const teamNames = [kp.tech_leader, kp.sales_leader, kp.other_key]
    .filter(p => p && p.name && p.name.trim())
    .map(p => p.name.trim());
  if (teamNames.length > 0) {
    parts.push(`The team that built this business — ${teamNames.join(', ')} — is in place and capable of running it without you day one post-close.`);
  }

  const story = meetingData.story_elements || {};
  if (story.culture && story.culture.trim()) {
    parts.push(story.culture.trim());
  }

  const dealBreakers = meetingData.deal_breakers || {};
  const dealBreakersActive = Object.entries(dealBreakers).filter(([, v]) => v === true);
  if (dealBreakersActive.length > 0) {
    const buyerMeetsBreakers = hasContent(buyerResearch.deal_breaker_alignment)
      ? buyerResearch.deal_breaker_alignment.trim()
      : `${buyerName} is structured to honor exactly the terms that matter most to you`;
    parts.push(`We know what you need in a deal — ${dealBreakerNarrative(dealBreakers)} — and ${buyerMeetsBreakers}.`);
  }

  return parts.join(' ');
}

function buildParagraph3(meetingData, companyName, buyerName, buyerResearch, valuation, decisionMaker) {
  const parts = [];

  const timeline = meetingData.timeline || meetingData.timeline_type || '';
  const timelinePhrase = timelineToPhrase(timeline);
  if (timelinePhrase) {
    const buyerSpeed = hasContent(buyerResearch.typical_deal_structure)
      ? `${buyerResearch.typical_deal_structure.trim()}, which aligns precisely with your timeline`
      : `they move quickly when the fit is right, which maps to your timing`;
    parts.push(`Your ${timelinePhrase} maps well to how ${buyerName} operates — ${buyerSpeed}.`);
  }

  if (valuation.low && valuation.high) {
    const low  = formatDollar(valuation.low);
    const high = formatDollar(valuation.high);
    const mult = `${valuation.multiple_floor}x–${valuation.multiple_ceiling}x ${VALUATION_METRIC}`;
    parts.push(`Based on current market comps in your vertical, a business like ${companyName} is realistically positioned in the ${low}–${high} range at ${mult}.`);
    if (valuation.recurring_premium) {
      parts.push(`Your recurring revenue base is a real premium driver — buyers underwrite that cash flow at the top of the multiple range.`);
    }
  }

  const acqHistory = hasContent(buyerResearch.acquisition_history)
    ? `${buyerResearch.acquisition_history.trim()} `
    : '';
  parts.push(`${acqHistory}I'd like to introduce you directly to ${decisionMaker} at ${buyerName}. This is not a cattle call — if you're willing to take one conversation, I will make sure the right person is on the other end of it.`);

  return parts.join(' ');
}

function buildClosing(meetingData, companyName, decisionMaker) {
  const motivation = meetingData.motivation_type || '';
  if (motivation === 'retirement' || motivation === 'health') {
    return `There's no pressure here and no obligation. When you've spent your life building something as real as ${companyName}, the decision to explore what's next deserves to happen on your terms. Reply to this letter, send an email, or call me directly — whichever feels most comfortable. I'm here when you're ready.`;
  }
  if (motivation === 'growth_capital' || motivation === 'partner') {
    return `You've built something worth growing further, and the right partner can accelerate everything you've already put in motion. A single conversation with ${decisionMaker} costs nothing and could change how you think about what's possible from here. I'll make the introduction — just say the word.`;
  }
  return `This letter costs you nothing and obligates you to nothing. If you're even slightly curious about what ${companyName} is worth in today's market — and what your options actually look like — I hope you'll reach out. I'll make the introduction to ${decisionMaker} the same day.`;
}

function buildLetter(meetingData, buyerResearch, { ownerName, companyName, buyerName, valuation }) {
  const ownerFirst    = (ownerName || '').split(' ')[0] || ownerName;
  const decisionMaker = (buyerResearch.decision_makers && buyerResearch.decision_makers[0]
    ? buyerResearch.decision_makers[0].name
    : null)
    || buyerResearch.primary_contact
    || buyerName;

  const p1 = buildParagraph1(meetingData, companyName, buyerName, buyerResearch);
  const p2 = buildParagraph2(meetingData, companyName, buyerName, buyerResearch, valuation);
  const p3 = buildParagraph3(meetingData, companyName, buyerName, buyerResearch, valuation, decisionMaker);
  const cl = buildClosing(meetingData, companyName, decisionMaker);

  return [
    `<p class="letter-paragraph" data-section="greeting">Dear ${ownerFirst},</p>`,
    '',
    `<p class="letter-paragraph" data-section="p1">${p1}</p>`,
    '',
    `<p class="letter-paragraph" data-section="p2">${p2}</p>`,
    '',
    `<p class="letter-paragraph" data-section="p3">${p3}</p>`,
    '',
    `<p class="letter-paragraph" data-section="closing">${cl}</p>`,
  ].join('\n');
}

// ---------------------------------------------------------------------------
// Vercel serverless handler
// ---------------------------------------------------------------------------

module.exports = async function handler(req, res) {
  // CORS preflight
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(204).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  let body;
  try {
    body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  } catch {
    return res.status(400).json({ error: 'Invalid JSON body' });
  }

  const { company_id, meeting_data, buyer_research_data, opts = {} } = body || {};

  if (!meeting_data || !buyer_research_data) {
    return res.status(400).json({ error: 'meeting_data and buyer_research_data are required' });
  }

  const ownerName   = opts.ownerName   || meeting_data.owner_name   || 'the owner';
  const companyName = opts.companyName || meeting_data.company_name || 'your company';
  const buyerName   = buyer_research_data.company_name || buyer_research_data.buyer_name || 'this buyer';
  const vertical    = opts.vertical    || meeting_data.vertical     || 'default';

  const score    = computeScore(meeting_data, buyer_research_data);
  const tone     = computeTone(meeting_data);
  const valuation = computeValuationRange(meeting_data, vertical);
  const letterText = buildLetter(meeting_data, buyer_research_data, {
    ownerName,
    companyName,
    buyerName,
    valuation,
  });

  return res.status(200).json({
    letter_text:               letterText,
    personalization_score:     score.total,
    score_breakdown:           score.breakdown,
    tone_signal:               tone,
    estimated_valuation_range: valuation,
    readiness_label:           readinessLabel(score.total),
    meta: {
      company_id:   company_id || null,
      buyer_name:   buyerName,
      company_name: companyName,
      generated_at: new Date().toISOString(),
    },
  });
};
