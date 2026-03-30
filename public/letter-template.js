/**
 * Letter Template Engine
 * Generates personalized Next Chapter M&A letters from meeting data + buyer research.
 *
 * Input:  meeting_data (from Meeting Page v2) + buyer_research_data (from researcher agent)
 * Output: { letter_text, personalization_score, tone_signal, estimated_valuation_range }
 *
 * Scoring rubric (0.0–1.0):
 *   0.30 — meeting story elements used (origin, challenge, culture)
 *   0.30 — buyer acquisition history + strategic rationale referenced
 *   0.20 — timeline/motivation matched to buyer's typical deal structure
 *   0.10 — deal-breakers addressed specifically
 *   0.10 — financial detail present (revenue, EBITDA, valuation range)
 *
 *   ≥ 0.80 = "Production Ready"
 *   0.60–0.79 = "Good"
 *   < 0.60 = "Needs Refinement"
 */

class LetterTemplateEngine {
  constructor() {
    this.SCORE_THRESHOLDS = {
      production: 0.80,
      good: 0.60,
    };

    // EBITDA multiple ranges by vertical (mirrors letter_engine.py)
    this.VERTICAL_MULTIPLES = {
      water_treatment:  { floor: 4.0, ceiling: 8.0, median: 5.5 },
      hvac:             { floor: 4.5, ceiling: 8.5, median: 6.0 },
      plumbing:         { floor: 4.0, ceiling: 7.5, median: 5.5 },
      roofing:          { floor: 3.5, ceiling: 7.0, median: 5.0 },
      pest_control:     { floor: 5.0, ceiling: 10.0, median: 7.0 },
      concrete_precast: { floor: 4.0, ceiling: 7.5, median: 5.5 },
      flooring:         { floor: 3.5, ceiling: 6.5, median: 4.75 },
      default:          { floor: 4.0, ceiling: 7.0, median: 5.5 },
    };
  }

  // ---------------------------------------------------------------------------
  // Public API
  // ---------------------------------------------------------------------------

  /**
   * Generate a letter from meeting + buyer research data.
   *
   * @param {Object} meetingData    — from MeetingForm.getFormData()
   * @param {Object} buyerResearch  — from researcher agent
   * @param {Object} [opts]
   * @param {string} [opts.ownerName]   — "Larry Casey" or split first/last
   * @param {string} [opts.companyName] — "AquaScience"
   * @param {string} [opts.vertical]    — vertical slug
   * @returns {{ letter_text: string, personalization_score: number, tone_signal: string, estimated_valuation_range: Object }}
   */
  generate(meetingData, buyerResearch, opts = {}) {
    const ownerName    = opts.ownerName    || meetingData.company_name || 'the owner';
    const companyName  = opts.companyName  || meetingData.company_name || 'your company';
    const vertical     = opts.vertical     || meetingData.vertical     || 'default';
    const buyerName    = buyerResearch.company_name || buyerResearch.buyer_name || 'this buyer';

    const score       = this._computeScore(meetingData, buyerResearch);
    const toneSignal  = this._computeTone(meetingData);
    const valuation   = this._computeValuationRange(meetingData, vertical);
    const letterText  = this._buildLetter(meetingData, buyerResearch, {
      ownerName,
      companyName,
      buyerName,
      vertical,
      valuation,
    });

    return {
      letter_text:               letterText,
      personalization_score:     score.total,
      score_breakdown:           score.breakdown,
      tone_signal:               toneSignal,
      estimated_valuation_range: valuation,
      readiness_label:           this._readinessLabel(score.total),
    };
  }

  /**
   * Attach inline-editing hooks to a rendered letter container element.
   * Delegates to the existing InlineEditor system.
   *
   * @param {HTMLElement} containerEl — wrapper div holding the rendered letter
   * @param {string}      letterId   — unique id for storage key
   */
  attachInlineEditing(containerEl, letterId) {
    if (!containerEl) return;

    // Mark each paragraph as editable so InlineEditor picks them up
    containerEl.querySelectorAll('p, .letter-paragraph').forEach((el, i) => {
      if (!el.hasAttribute('data-editable')) {
        el.setAttribute('data-editable', 'true');
        el.setAttribute('data-editable-id', `letter-${letterId}-p${i}`);
      }
    });

    // If InlineEditor is already initialized, wire up the new nodes directly.
    // Otherwise wait for its MutationObserver to catch them.
    if (window.inlineEditor) {
      containerEl.querySelectorAll('[data-editable="true"]').forEach((el) => {
        const editableId = el.getAttribute('data-editable-id');
        if (!el.querySelector('.edit-toggle-btn')) {
          window.inlineEditor.addEditButton(el, editableId);
        }
      });
    }
  }

  /**
   * Render the letter into a DOM container and attach editing.
   *
   * @param {string}      letterText  — HTML or plain text letter
   * @param {string}      containerId — id of the wrapper element
   * @param {string}      letterId    — unique id for storage keys
   */
  renderIntoContainer(letterText, containerId, letterId) {
    const container = document.getElementById(containerId);
    if (!container) {
      console.warn(`LetterTemplateEngine: container #${containerId} not found`);
      return;
    }
    container.innerHTML = letterText;
    this.attachInlineEditing(container, letterId);
  }

  // ---------------------------------------------------------------------------
  // Score computation
  // ---------------------------------------------------------------------------

  _computeScore(meetingData, buyerResearch) {
    const breakdown = {};

    // 0.30 — story elements
    const story = meetingData.story_elements || {};
    const storyFields = ['origin', 'challenge', 'culture', 'community', 'personal', 'quirky'];
    const storyFilled = storyFields.filter(k => story[k] && story[k].trim().length > 10).length;
    const storyWeight = Math.min(storyFilled / 2, 1) * 0.30;   // 2 filled → full weight
    breakdown.story_elements = parseFloat(storyWeight.toFixed(3));

    // 0.30 — buyer acquisition history + strategic rationale
    const hasAcqHistory   = this._hasContent(buyerResearch.acquisition_history);
    const hasStrategicRat = this._hasContent(buyerResearch.strategic_rationale);
    const hasApproach     = this._hasContent(buyerResearch.approach_strategy);
    const buyerSignals    = [hasAcqHistory, hasStrategicRat, hasApproach].filter(Boolean).length;
    const buyerWeight     = (buyerSignals / 3) * 0.30;
    breakdown.buyer_research = parseFloat(buyerWeight.toFixed(3));

    // 0.20 — timeline/motivation matched to buyer's deal structure
    const hasMeetingMotivation = this._hasContent(meetingData.motivation_type);
    const hasBuyerDealStructure = this._hasContent(buyerResearch.deal_structure)
      || this._hasContent(buyerResearch.typical_deal_structure)
      || this._hasContent(buyerResearch.approach_strategy);
    const timelineScore = (hasMeetingMotivation ? 0.10 : 0) + (hasBuyerDealStructure ? 0.10 : 0);
    breakdown.timeline_match = parseFloat(timelineScore.toFixed(3));

    // 0.10 — deal-breakers addressed
    const dealBreakers = meetingData.deal_breakers || {};
    const activeDealBreakers = Object.values(dealBreakers).filter(Boolean).length;
    const dealBreakersAddressed = this._hasContent(buyerResearch.deal_breaker_alignment)
      || this._hasContent(buyerResearch.approach_strategy);
    const dealWeight = activeDealBreakers > 0 && dealBreakersAddressed ? 0.10 : (activeDealBreakers > 0 ? 0.05 : 0.10);
    breakdown.deal_breakers = parseFloat(dealWeight.toFixed(3));

    // 0.10 — financial detail present
    const hasRevenue = (meetingData.annual_revenue || 0) > 0;
    const hasEbitda  = (meetingData.estimated_ebitda || 0) > 0 || (meetingData.ebitda_margin || 0) > 0;
    const financialWeight = ((hasRevenue ? 1 : 0) + (hasEbitda ? 1 : 0)) / 2 * 0.10;
    breakdown.financial_detail = parseFloat(financialWeight.toFixed(3));

    const total = parseFloat(
      Object.values(breakdown).reduce((sum, v) => sum + v, 0).toFixed(2)
    );

    return { total, breakdown };
  }

  _computeTone(meetingData) {
    const readiness = meetingData.emotional_readiness || meetingData.readiness_scale || 5;
    const motivation = meetingData.motivation_type || '';
    const timeline   = meetingData.timeline || meetingData.timeline_type || '';

    if (readiness >= 8 || timeline === '3months' || motivation === 'retirement') {
      return 'urgent';
    }
    if (readiness >= 6 || timeline === '6months' || timeline === '12months') {
      return 'warm';
    }
    return 'exploratory';
  }

  _computeValuationRange(meetingData, vertical) {
    const multiples = this.VERTICAL_MULTIPLES[vertical] || this.VERTICAL_MULTIPLES.default;
    const ebitda = this._resolveEbitda(meetingData);

    if (!ebitda || ebitda <= 0) {
      return { low: null, mid: null, high: null, ebitda_used: null, note: 'Insufficient financial data' };
    }

    // Bump the range up slightly when recurring revenue is strong
    const recurringPct = meetingData.recurring_revenue_percentage || meetingData.recurring_revenue || 0;
    const premiumFactor = recurringPct >= 60 ? 0.5 : recurringPct >= 40 ? 0.25 : 0;

    const floorMultiple  = multiples.floor;
    const ceilingMultiple = multiples.ceiling + premiumFactor;
    const medianMultiple  = multiples.median  + premiumFactor * 0.5;

    return {
      low:         Math.round(ebitda * floorMultiple  / 100000) * 100000,
      mid:         Math.round(ebitda * medianMultiple / 100000) * 100000,
      high:        Math.round(ebitda * ceilingMultiple / 100000) * 100000,
      ebitda_used: ebitda,
      multiple_floor:   floorMultiple,
      multiple_ceiling: ceilingMultiple,
      multiple_median:  medianMultiple,
      recurring_premium: premiumFactor > 0,
    };
  }

  _resolveEbitda(meetingData) {
    // Use explicit EBITDA if provided
    if (meetingData.estimated_ebitda && meetingData.estimated_ebitda > 0) {
      const addbacks = this._sumAddbacks(meetingData);
      return meetingData.estimated_ebitda + addbacks;
    }
    // Fall back to revenue × margin
    if (meetingData.annual_revenue && meetingData.ebitda_margin) {
      const addbacks = this._sumAddbacks(meetingData);
      return (meetingData.annual_revenue * (meetingData.ebitda_margin / 100)) + addbacks;
    }
    return null;
  }

  _sumAddbacks(meetingData) {
    const p = meetingData.owner_perks || {};
    return (p.vehicle_allowance || 0)
         + (p.family_salary     || 0)
         + (p.travel_entertainment || 0)
         + (p.insurance_benefits   || 0);
  }

  // ---------------------------------------------------------------------------
  // Letter builder
  // ---------------------------------------------------------------------------

  _buildLetter(meetingData, buyerResearch, { ownerName, companyName, buyerName, vertical, valuation }) {
    const ownerFirst = ownerName.split(' ')[0] || ownerName;
    const decisionMaker = buyerResearch.decision_makers?.[0]?.name
      || buyerResearch.primary_contact
      || buyerName;

    const p1 = this._buildParagraph1(meetingData, companyName, buyerName, buyerResearch);
    const p2 = this._buildParagraph2(meetingData, companyName, buyerName, buyerResearch, valuation);
    const p3 = this._buildParagraph3(meetingData, companyName, buyerName, buyerResearch, valuation, decisionMaker);
    const closing = this._buildClosing(meetingData, companyName, decisionMaker);

    const lines = [
      `<p class="letter-paragraph" data-section="greeting">Dear ${ownerFirst},</p>`,
      '',
      `<p class="letter-paragraph" data-section="p1">${p1}</p>`,
      '',
      `<p class="letter-paragraph" data-section="p2">${p2}</p>`,
      '',
      `<p class="letter-paragraph" data-section="p3">${p3}</p>`,
      '',
      `<p class="letter-paragraph" data-section="closing">${closing}</p>`,
    ];

    return lines.join('\n');
  }

  _buildParagraph1(meetingData, companyName, buyerName, buyerResearch) {
    const story = meetingData.story_elements || {};

    // Story hook — origin or challenge
    let storyHook = '';
    if (story.origin && story.origin.trim()) {
      storyHook = `${story.origin.trim()} `;
    } else if (story.challenge && story.challenge.trim()) {
      storyHook = `The way you've navigated ${story.challenge.trim()} is exactly the kind of story that gets a buyer's attention. `;
    }

    // Why this buyer
    const strategicRat = buyerResearch.strategic_rationale
      ? `${buyerResearch.strategic_rationale.trim()} `
      : '';

    const buyerContext = this._hasContent(buyerResearch.company_overview)
      ? `${buyerResearch.company_overview.trim()} `
      : '';

    const fitStatement = strategicRat || buyerContext
      ? `That's precisely why ${buyerName} belongs in this conversation — ${strategicRat || buyerContext}`
      : `That combination is exactly what buyers like ${buyerName} are looking for right now. `;

    return `${storyHook}${fitStatement}I wanted to reach out directly because I believe there is a genuine fit between what you've built at ${companyName} and what ${buyerName} is actively pursuing.`;
  }

  _buildParagraph2(meetingData, companyName, buyerName, buyerResearch, valuation) {
    const parts = [];

    // Revenue and margins
    if (meetingData.annual_revenue && meetingData.annual_revenue > 0) {
      const revFormatted = this._formatDollar(meetingData.annual_revenue);
      parts.push(`${companyName} is running ${revFormatted} in annual revenue`);

      if (meetingData.ebitda_margin && meetingData.ebitda_margin > 0) {
        parts.push(`with ${meetingData.ebitda_margin}% EBITDA margins`);
      } else if (valuation.ebitda_used) {
        parts.push(`generating ${this._formatDollar(valuation.ebitda_used)} in adjusted EBITDA`);
      }

      if (meetingData.growth_rate && meetingData.growth_rate > 0) {
        parts.push(`and ${meetingData.growth_rate}% year-over-year growth`);
      }

      parts.push('— numbers that will stand up in any quality of earnings process.');
    }

    // Team structure
    const kp = meetingData.key_people || {};
    const teamNames = [kp.tech_leader, kp.sales_leader, kp.other_key]
      .filter(p => p && p.name && p.name.trim())
      .map(p => p.name.trim());
    if (teamNames.length > 0) {
      parts.push(`The team that built this business — ${teamNames.join(', ')} — is in place and capable of running it without you day one post-close.`);
    }

    // What makes them special (story culture / quirky)
    const story = meetingData.story_elements || {};
    if (story.culture && story.culture.trim()) {
      parts.push(story.culture.trim());
    }

    // Deal-breaker alignment
    const dealBreakers = meetingData.deal_breakers || {};
    const dealBreakersActive = Object.entries(dealBreakers)
      .filter(([, v]) => v === true)
      .map(([k]) => k);

    if (dealBreakersActive.length > 0) {
      const buyerMeetsBreakers = this._hasContent(buyerResearch.deal_breaker_alignment)
        ? buyerResearch.deal_breaker_alignment.trim()
        : `${buyerName} is structured to honor exactly the terms that matter most to you`;
      parts.push(`We know what you need in a deal — ${this._dealBreakerNarrative(dealBreakers)} — and ${buyerMeetsBreakers}.`);
    }

    return parts.join(' ');
  }

  _buildParagraph3(meetingData, companyName, buyerName, buyerResearch, valuation, decisionMaker) {
    const parts = [];

    // Timeline match
    const timeline = meetingData.timeline || meetingData.timeline_type || '';
    const timelinePhrase = this._timelineToPhrase(timeline);
    if (timelinePhrase) {
      const buyerSpeed = this._hasContent(buyerResearch.typical_deal_structure)
        ? `${buyerResearch.typical_deal_structure.trim()}, which aligns precisely with your timeline`
        : `they move quickly when the fit is right, which maps to your timing`;
      parts.push(`Your ${timelinePhrase} maps well to how ${buyerName} operates — ${buyerSpeed}.`);
    }

    // Valuation range
    if (valuation.low && valuation.high) {
      const low  = this._formatDollar(valuation.low);
      const high = this._formatDollar(valuation.high);
      const mult = `${valuation.multiple_floor}x–${valuation.multiple_ceiling}x EBITDA`;
      parts.push(`Based on current market comps in your vertical, a business like ${companyName} is realistically positioned in the ${low}–${high} range at ${mult}.`);
      if (valuation.recurring_premium) {
        parts.push(`Your recurring revenue base is a real premium driver — buyers underwrite that cash flow at the top of the multiple range.`);
      }
    }

    // Specific buyer intro + decision-maker
    const acqHistory = this._hasContent(buyerResearch.acquisition_history)
      ? `${buyerResearch.acquisition_history.trim()} `
      : '';
    parts.push(`${acqHistory}I'd like to introduce you directly to ${decisionMaker} at ${buyerName}. This is not a cattle call — if you're willing to take one conversation, I will make sure the right person is on the other end of it.`);

    return parts.join(' ');
  }

  _buildClosing(meetingData, companyName, decisionMaker) {
    const motivation = meetingData.motivation_type || '';

    if (motivation === 'retirement' || motivation === 'health') {
      return `There's no pressure here and no obligation. When you've spent your life building something as real as ${companyName}, the decision to explore what's next deserves to happen on your terms. Reply to this letter, send an email, or call me directly — whichever feels most comfortable. I'm here when you're ready.`;
    }

    if (motivation === 'growth_capital' || motivation === 'partner') {
      return `You've built something worth growing further, and the right partner can accelerate everything you've already put in motion. A single conversation with ${decisionMaker} costs nothing and could change how you think about what's possible from here. I'll make the introduction — just say the word.`;
    }

    return `This letter costs you nothing and obligates you to nothing. If you're even slightly curious about what ${companyName} is worth in today's market — and what your options actually look like — I hope you'll reach out. I'll make the introduction to ${decisionMaker} the same day.`;
  }

  // ---------------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------------

  _hasContent(val) {
    return val && typeof val === 'string' && val.trim().length > 5;
  }

  _readinessLabel(score) {
    if (score >= this.SCORE_THRESHOLDS.production) return 'Production Ready';
    if (score >= this.SCORE_THRESHOLDS.good)       return 'Good';
    return 'Needs Refinement';
  }

  _formatDollar(n) {
    if (!n || isNaN(n)) return '';
    if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`;
    if (n >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`;
    return `$${n.toLocaleString()}`;
  }

  _timelineToPhrase(timeline) {
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

  _dealBreakerNarrative(dealBreakers) {
    const labels = {
      whole_company:    'selling the whole company',
      not_customer_list: 'not just selling a customer list',
      stay_operator:    'having a path to stay involved as an operator',
      full_proceeds:    'receiving full cash proceeds at close',
      keep_employees:   'protecting your team',
      maintain_location: 'keeping the location intact',
    };
    const active = Object.entries(dealBreakers)
      .filter(([, v]) => v === true)
      .map(([k]) => labels[k] || k.replace(/_/g, ' '));
    if (active.length === 0) return 'the right structure';
    if (active.length === 1) return active[0];
    const last = active.pop();
    return `${active.join(', ')} and ${last}`;
  }

  // ---------------------------------------------------------------------------
  // API call wrapper (used by approval component)
  // ---------------------------------------------------------------------------

  /**
   * Call the /api/letters/generate endpoint and return the result.
   * Falls back to local generation if the endpoint is unavailable.
   *
   * @param {string} companyId
   * @param {Object} meetingData
   * @param {Object} buyerResearchData
   * @param {Object} [opts]        — ownerName, companyName, vertical
   * @returns {Promise<Object>}
   */
  async generateViaAPI(companyId, meetingData, buyerResearchData, opts = {}) {
    try {
      const response = await fetch('/api/letters/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          company_id:          companyId,
          meeting_data:        meetingData,
          buyer_research_data: buyerResearchData,
          opts,
        }),
      });

      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }

      return await response.json();

    } catch (err) {
      console.warn('LetterTemplateEngine: API unavailable, falling back to local generation:', err.message);
      // Local fallback — same logic, no server needed
      return this.generate(meetingData, buyerResearchData, opts);
    }
  }
}

// ---------------------------------------------------------------------------
// Module export + global init
// ---------------------------------------------------------------------------

// CommonJS / Node (for serverless function)
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { LetterTemplateEngine };
}

// Browser global
if (typeof window !== 'undefined') {
  window.LetterTemplateEngine = LetterTemplateEngine;
  window.letterEngine = new LetterTemplateEngine();
}
