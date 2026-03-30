/**
 * Proposal Auto-Generator
 * Converts meeting form data into a full interactive HTML proposal
 * Target: <5 seconds generation time
 */

class ProposalAutoGenerator {
  constructor() {
    this.EBITDA_MULTIPLES = { low: 4, mid: 5, high: 6 };
    this.INDUSTRY_MARGIN_BENCHMARK = 0.22; // 22% home services benchmark
  }

  // ─────────────────────────────────────────────
  // Core: Parse meeting data from URL params or object
  // ─────────────────────────────────────────────
  parseMeetingData(source) {
    if (typeof source === 'string') {
      const params = new URLSearchParams(source);
      return this._paramsToObject(params);
    }
    if (source instanceof URLSearchParams) {
      return this._paramsToObject(source);
    }
    return source; // already an object
  }

  _paramsToObject(params) {
    const d = {};
    for (const [k, v] of params.entries()) {
      d[k] = v;
    }
    return d;
  }

  // ─────────────────────────────────────────────
  // Calculations
  // ─────────────────────────────────────────────
  calcAddbacks(d) {
    return (
      (parseFloat(d.vehicle_allowance) || 0) +
      (parseFloat(d.family_salary) || 0) +
      (parseFloat(d.travel_entertainment) || 0) +
      (parseFloat(d.insurance_benefits) || 0)
    );
  }

  calcAdjEbitda(d) {
    const base = parseFloat(d.estimated_ebitda) || 0;
    return base + this.calcAddbacks(d);
  }

  calcValuation(d) {
    const adj = this.calcAdjEbitda(d);
    return {
      low: adj * this.EBITDA_MULTIPLES.low,
      mid: adj * this.EBITDA_MULTIPLES.mid,
      high: adj * this.EBITDA_MULTIPLES.high,
      adj_ebitda: adj
    };
  }

  calcFee(valuation_mid) {
    // Tiered fee: 1% on first $5M, 0.75% above $5M
    if (valuation_mid <= 5000000) return valuation_mid * 0.01;
    return 5000000 * 0.01 + (valuation_mid - 5000000) * 0.0075;
  }

  calcPersonalizationScore(d) {
    const fields = [
      'company_name', 'annual_revenue', 'estimated_ebitda', 'growth_rate',
      'service_split', 'timeline_type', 'motivation_type', 'story_origin',
      'key_people', 'deal_breakers', 'ebitda_margin', 'industry'
    ];
    const filled = fields.filter(f => d[f] && String(d[f]).trim().length > 0).length;
    return Math.round((filled / fields.length) * 100) / 100;
  }

  // ─────────────────────────────────────────────
  // Timeline dates
  // ─────────────────────────────────────────────
  buildTimeline(d) {
    const today = new Date();
    const fmt = (dt) => dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    const addDays = (n) => { const dt = new Date(today); dt.setDate(dt.getDate() + n); return dt; };

    // Adjust close timeline based on owner preference
    let closeOffset = 120;
    const tl = d.timeline_type || '';
    if (tl === '3months') closeOffset = 90;
    else if (tl === '6months') closeOffset = 120;
    else if (tl === '12months') closeOffset = 150;
    else if (tl === '18months') closeOffset = 180;

    return [
      { label: 'Letter Sent', date: fmt(today), offset: 0, active: true },
      { label: 'Initial Call', date: fmt(addDays(3)), offset: 3 },
      { label: 'First Meeting', date: fmt(addDays(10)), offset: 10 },
      { label: 'Letter of Intent', date: fmt(addDays(30)), offset: 30 },
      { label: 'Due Diligence Complete', date: fmt(addDays(75)), offset: 75 },
      { label: 'Close', date: fmt(addDays(closeOffset)), offset: closeOffset }
    ];
  }

  // ─────────────────────────────────────────────
  // Deal structure logic
  // ─────────────────────────────────────────────
  buildDealStructure(d) {
    const breakers = d.deal_breakers ? d.deal_breakers.split(',') : [];
    const val = this.calcValuation(d);
    const structures = [];

    if (breakers.includes('full-proceeds') || breakers.includes('full_proceeds')) {
      structures.push({
        type: 'All Cash at Close',
        description: `100% of proceeds paid at closing. No earnout, no holdback. Total consideration: ${this.fmt$(val.mid)}.`,
        highlight: true
      });
    } else if (breakers.includes('earnout')) {
      structures.push({
        type: 'Blended Structure',
        description: `${this.fmt$(val.mid * 0.8)} at close (80%) + ${this.fmt$(val.mid * 0.2)} earnout over 24 months tied to revenue targets.`,
        highlight: true
      });
    } else {
      // Default: present both options
      structures.push({
        type: 'Option A — All Cash',
        description: `${this.fmt$(val.mid)} at close. Simple, clean, no contingencies.`,
        highlight: false
      });
      structures.push({
        type: 'Option B — Blended',
        description: `${this.fmt$(val.high * 0.8)} at close + ${this.fmt$(val.high * 0.2)} over 24 months. Higher total proceeds for sellers who can earn into it.`,
        highlight: false
      });
    }

    if (breakers.includes('stay-operator') || breakers.includes('stay_operator')) {
      structures.push({
        type: 'Management Retention',
        description: 'Owner remains as operator with market-rate compensation, equity rollover option, and full operational authority for 24+ months post-close.',
        highlight: false
      });
    }

    return structures;
  }

  // ─────────────────────────────────────────────
  // Formatters
  // ─────────────────────────────────────────────
  fmt$(n) {
    if (!n || isNaN(n)) return '$0';
    if (n >= 1000000) return '$' + (n / 1000000).toFixed(2).replace(/\.?0+$/, '') + 'M';
    if (n >= 1000) return '$' + Math.round(n / 1000) + 'K';
    return '$' + Math.round(n).toLocaleString();
  }

  fmtPct(n) {
    return (parseFloat(n) || 0).toFixed(1) + '%';
  }

  fmtRevenue(n) {
    const v = parseFloat(n) || 0;
    if (v >= 1000000) return '$' + (v / 1000000).toFixed(1) + 'M';
    if (v >= 1000) return '$' + (v / 1000).toFixed(0) + 'K';
    return '$' + v.toLocaleString();
  }

  timelineLabel(type) {
    const map = {
      '3months': '3 months (urgent)',
      '6months': '6 months',
      '12months': '12 months',
      '18months': '18+ months',
      'none': 'Exploring options'
    };
    return map[type] || type || 'Not specified';
  }

  motivationLabel(type) {
    const map = {
      'exit_cashout': 'Looking to exit and cash out',
      'exploring': 'Exploring options',
      'capital': 'Seeking growth capital',
      'burnout': 'Ready to step back',
      'family': 'Family / partner transition',
      'tax': 'Tax planning event'
    };
    return map[type] || type || 'Not specified';
  }

  industryLabel(d) {
    return d.industry || 'Home Services';
  }

  // ─────────────────────────────────────────────
  // Parse key_people (JSON or comma string)
  // ─────────────────────────────────────────────
  parseKeyPeople(d) {
    if (!d.key_people) return [];
    try {
      const parsed = JSON.parse(d.key_people);
      if (Array.isArray(parsed)) return parsed;
      return [parsed];
    } catch (_) {
      // comma-separated names
      return d.key_people.split(',').map(n => ({ name: n.trim(), role: 'Key Person' }));
    }
  }

  // ─────────────────────────────────────────────
  // Main: Generate full HTML string
  // ─────────────────────────────────────────────
  generate(rawData) {
    const startTime = Date.now();
    const d = this.parseMeetingData(rawData);

    const company = d.company_name || 'Your Company';
    const revenue = parseFloat(d.annual_revenue) || 0;
    const growthRate = parseFloat(d.growth_rate) || 0;
    const servicePct = parseFloat(d.service_split) || 60;
    const installPct = 100 - servicePct;
    const ebitdaMargin = parseFloat(d.ebitda_margin) || 0;
    const estimatedEbitda = parseFloat(d.estimated_ebitda) || 0;
    const addbacks = this.calcAddbacks(d);
    const adjEbitda = this.calcAdjEbitda(d);
    const val = this.calcValuation(d);
    const fee = this.calcFee(val.mid);
    const timeline = this.buildTimeline(d);
    const dealStructures = this.buildDealStructure(d);
    const keyPeople = this.parseKeyPeople(d);
    const personalizationScore = this.calcPersonalizationScore(d);

    const generationTime = Date.now() - startTime;

    const html = this._renderHTML({
      d, company, revenue, growthRate, servicePct, installPct,
      ebitdaMargin, estimatedEbitda, addbacks, adjEbitda, val, fee,
      timeline, dealStructures, keyPeople, personalizationScore, generationTime
    });

    return {
      html,
      metadata: {
        company,
        generation_ms: generationTime,
        personalization_score: personalizationScore,
        valuation_mid: val.mid,
        adj_ebitda: adjEbitda,
        fee_estimate: fee,
        created_at: new Date().toISOString()
      }
    };
  }

  // ─────────────────────────────────────────────
  // HTML renderer
  // ─────────────────────────────────────────────
  _renderHTML(ctx) {
    const {
      d, company, revenue, growthRate, servicePct, installPct,
      ebitdaMargin, estimatedEbitda, addbacks, adjEbitda, val, fee,
      timeline, dealStructures, keyPeople, personalizationScore, generationTime
    } = ctx;

    const today = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Confidential Proposal — ${this._esc(company)}</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --navy: #1a365d;
      --blue: #2b6cb0;
      --blue-light: #ebf4ff;
      --green: #276749;
      --green-light: #f0fff4;
      --gold: #b7791f;
      --gold-light: #fffaf0;
      --gray: #718096;
      --gray-light: #f7fafc;
      --border: #e2e8f0;
      --text: #2d3748;
      --text-sm: #4a5568;
      --white: #ffffff;
      --shadow: 0 2px 12px rgba(0,0,0,0.07);
      --shadow-lg: 0 4px 24px rgba(0,0,0,0.1);
    }

    body {
      font-family: 'Georgia', 'Times New Roman', serif;
      background: #f0f4f8;
      color: var(--text);
      line-height: 1.7;
      font-size: 16px;
    }

    /* ── Nav ── */
    .topnav {
      background: #161b22;
      padding: 8px 24px;
      border-bottom: 1px solid #30363d;
      display: flex;
      align-items: center;
      gap: 20px;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .topnav a {
      color: #58a6ff;
      text-decoration: none;
      font-size: 13px;
      font-family: system-ui, sans-serif;
    }
    .topnav a.dim { color: #8b949e; }
    .topnav .gen-meta {
      margin-left: auto;
      font-size: 11px;
      color: #6e7681;
      font-family: system-ui, sans-serif;
    }

    /* ── Container ── */
    .container {
      max-width: 960px;
      margin: 0 auto;
      padding: 40px 24px 80px;
    }

    /* ── Cover / Header ── */
    .cover {
      background: linear-gradient(135deg, var(--navy) 0%, var(--blue) 60%, #2c5282 100%);
      color: white;
      padding: 52px 48px 44px;
      border-radius: 14px;
      margin-bottom: 28px;
      position: relative;
      overflow: hidden;
    }
    .cover::before {
      content: '';
      position: absolute;
      top: -60px; right: -60px;
      width: 220px; height: 220px;
      border-radius: 50%;
      background: rgba(255,255,255,0.05);
    }
    .cover-badge {
      display: inline-block;
      background: rgba(255,255,255,0.15);
      border: 1px solid rgba(255,255,255,0.3);
      color: white;
      padding: 5px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-family: system-ui, sans-serif;
      text-transform: uppercase;
      letter-spacing: 1px;
      margin-bottom: 18px;
    }
    .cover h1 {
      font-size: 32px;
      font-weight: 700;
      line-height: 1.2;
      margin-bottom: 10px;
    }
    .cover .sub {
      font-size: 16px;
      opacity: 0.85;
      margin-bottom: 24px;
    }
    .cover-stats {
      display: flex;
      gap: 32px;
      flex-wrap: wrap;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid rgba(255,255,255,0.2);
    }
    .cover-stat { text-align: center; }
    .cover-stat .num { font-size: 26px; font-weight: 700; }
    .cover-stat .lbl { font-size: 12px; opacity: 0.75; text-transform: uppercase; letter-spacing: 0.5px; font-family: system-ui, sans-serif; }

    /* ── Section card ── */
    .section-card {
      background: var(--white);
      border-radius: 12px;
      box-shadow: var(--shadow);
      margin-bottom: 24px;
      overflow: hidden;
    }
    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 20px 28px 16px;
      border-bottom: 1px solid var(--border);
    }
    .section-title {
      font-size: 20px;
      font-weight: 700;
      color: var(--navy);
      font-family: system-ui, sans-serif;
    }
    .section-number {
      background: var(--navy);
      color: white;
      width: 30px; height: 30px;
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 14px; font-weight: 700;
      font-family: system-ui, sans-serif;
      flex-shrink: 0;
      margin-right: 12px;
    }
    .section-inner {
      padding: 24px 28px;
    }

    /* ── Inline edit hook ── */
    .editable-block {
      position: relative;
      border-radius: 6px;
      transition: background 0.15s;
    }
    .editable-block:hover { background: #f7fafc; }

    /* ── Highlight boxes ── */
    .highlight-box {
      background: var(--blue-light);
      border-left: 4px solid var(--blue);
      border-radius: 4px;
      padding: 16px 20px;
      margin-bottom: 16px;
      font-size: 15px;
    }
    .highlight-box.green {
      background: var(--green-light);
      border-color: var(--green);
    }
    .highlight-box.gold {
      background: var(--gold-light);
      border-color: var(--gold);
    }

    /* ── Stat grid ── */
    .stat-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 16px;
      margin-bottom: 20px;
    }
    .stat-cell {
      background: var(--gray-light);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 16px;
      text-align: center;
    }
    .stat-cell .val {
      font-size: 22px;
      font-weight: 700;
      color: var(--navy);
      font-family: system-ui, sans-serif;
    }
    .stat-cell .lbl {
      font-size: 12px;
      color: var(--gray);
      margin-top: 4px;
      font-family: system-ui, sans-serif;
    }

    /* ── Valuation range bar ── */
    .val-range {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 12px;
      margin: 20px 0;
    }
    .val-band {
      border-radius: 10px;
      padding: 20px 16px;
      text-align: center;
      border: 2px solid transparent;
    }
    .val-band.low { background: #fff5f5; border-color: #fc8181; }
    .val-band.mid { background: #f0fff4; border-color: #68d391; transform: scale(1.04); box-shadow: var(--shadow-lg); }
    .val-band.high { background: #fffff0; border-color: #f6e05e; }
    .val-band .multiple { font-size: 12px; font-family: system-ui, sans-serif; color: var(--gray); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
    .val-band .amount { font-size: 28px; font-weight: 800; color: var(--navy); font-family: system-ui, sans-serif; }
    .val-band .label { font-size: 13px; color: var(--gray); margin-top: 4px; font-family: system-ui, sans-serif; }
    .val-band.mid .label { color: var(--green); font-weight: 600; }

    /* ── Add-backs table ── */
    .addbacks-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 15px;
      margin-bottom: 16px;
    }
    .addbacks-table th {
      background: var(--navy);
      color: white;
      padding: 10px 16px;
      text-align: left;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-family: system-ui, sans-serif;
    }
    .addbacks-table th:first-child { border-radius: 8px 0 0 0; }
    .addbacks-table th:last-child { border-radius: 0 8px 0 0; text-align: right; }
    .addbacks-table td { padding: 10px 16px; border-bottom: 1px solid var(--border); }
    .addbacks-table td:last-child { text-align: right; font-weight: 600; }
    .addbacks-table tr.total td { background: var(--blue-light); font-weight: 700; border-bottom: none; }
    .addbacks-table tr:hover td { background: var(--gray-light); }

    /* ── Timeline ── */
    .timeline-track {
      position: relative;
      padding: 10px 0;
    }
    .timeline-track::before {
      content: '';
      position: absolute;
      left: 20px; top: 0; bottom: 0;
      width: 2px;
      background: var(--border);
    }
    .timeline-step {
      display: flex;
      align-items: flex-start;
      gap: 20px;
      padding: 12px 0;
      position: relative;
    }
    .tl-dot {
      width: 40px; height: 40px;
      border-radius: 50%;
      background: var(--border);
      border: 2px solid var(--border);
      display: flex; align-items: center; justify-content: center;
      flex-shrink: 0;
      font-size: 14px; font-weight: 700;
      color: var(--gray);
      font-family: system-ui, sans-serif;
      position: relative;
      z-index: 1;
    }
    .tl-dot.active {
      background: var(--navy);
      border-color: var(--navy);
      color: white;
    }
    .tl-dot.done {
      background: var(--green);
      border-color: var(--green);
      color: white;
    }
    .tl-content .tl-label { font-weight: 700; color: var(--navy); font-family: system-ui, sans-serif; }
    .tl-content .tl-date { font-size: 13px; color: var(--gray); font-family: system-ui, sans-serif; }
    .tl-content .tl-note { font-size: 13px; color: var(--text-sm); margin-top: 2px; }

    /* ── Deal structure ── */
    .deal-card {
      border: 1.5px solid var(--border);
      border-radius: 10px;
      padding: 18px 20px;
      margin-bottom: 14px;
    }
    .deal-card.highlight { border-color: var(--green); background: var(--green-light); }
    .deal-card .deal-type { font-weight: 700; font-size: 16px; color: var(--navy); font-family: system-ui, sans-serif; margin-bottom: 6px; }
    .deal-card.highlight .deal-type { color: var(--green); }

    /* ── Fee block ── */
    .fee-calc {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: var(--navy);
      color: white;
      border-radius: 10px;
      padding: 20px 28px;
      gap: 16px;
      flex-wrap: wrap;
    }
    .fee-calc .fee-num { font-size: 36px; font-weight: 800; font-family: system-ui, sans-serif; }
    .fee-calc .fee-note { font-size: 13px; opacity: 0.75; margin-top: 4px; font-family: system-ui, sans-serif; }
    .fee-calc .fee-breakdown { text-align: right; }
    .fee-calc .fee-breakdown p { font-size: 14px; opacity: 0.85; font-family: system-ui, sans-serif; }

    /* ── People pills ── */
    .people-list { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 12px; }
    .person-pill {
      display: flex; align-items: center; gap: 8px;
      background: var(--blue-light);
      border: 1px solid #bee3f8;
      border-radius: 24px;
      padding: 6px 14px;
      font-size: 14px;
    }
    .person-pill .pname { font-weight: 600; color: var(--navy); }
    .person-pill .prole { color: var(--gray); font-size: 13px; font-family: system-ui, sans-serif; }

    /* ── Score badge ── */
    .score-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: #f0fff4;
      border: 1px solid #9ae6b4;
      border-radius: 20px;
      padding: 4px 12px;
      font-size: 13px;
      font-family: system-ui, sans-serif;
      color: var(--green);
      font-weight: 600;
    }

    /* ── EBITDA lever bar ── */
    .lever-row {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 10px;
    }
    .lever-row .lever-lbl { width: 180px; font-size: 14px; flex-shrink: 0; }
    .lever-bar-wrap { flex: 1; background: var(--border); border-radius: 4px; height: 8px; }
    .lever-bar { height: 8px; border-radius: 4px; background: var(--blue); }
    .lever-row .lever-val { width: 70px; text-align: right; font-size: 14px; font-weight: 600; font-family: system-ui, sans-serif; color: var(--navy); }

    /* ── Reactive inputs ── */
    .reactive-input {
      display: inline-block;
      border-bottom: 2px dashed var(--blue);
      min-width: 60px;
      color: var(--blue);
      font-weight: 700;
      cursor: pointer;
      outline: none;
    }
    .reactive-input:focus { border-bottom-color: var(--navy); color: var(--navy); background: var(--blue-light); border-radius: 2px; padding: 0 2px; }

    /* ── Confidential footer ── */
    .conf-footer {
      text-align: center;
      margin-top: 40px;
      font-size: 12px;
      color: var(--gray);
      font-family: system-ui, sans-serif;
      line-height: 1.8;
    }

    /* ── Print ── */
    @media print {
      .topnav, .edit-toggle-btn { display: none !important; }
      .section-card { box-shadow: none; border: 1px solid var(--border); }
      body { background: white; }
    }

    /* ── Mobile ── */
    @media (max-width: 640px) {
      .container { padding: 16px 12px 60px; }
      .cover { padding: 32px 24px; }
      .cover h1 { font-size: 24px; }
      .cover-stats { gap: 16px; }
      .cover-stat .num { font-size: 20px; }
      .section-inner { padding: 16px; }
      .section-header { padding: 14px 16px 12px; }
      .val-range { grid-template-columns: 1fr; gap: 8px; }
      .val-band.mid { transform: none; }
      .fee-calc { flex-direction: column; text-align: center; }
      .fee-calc .fee-breakdown { text-align: center; }
      .stat-grid { grid-template-columns: 1fr 1fr; }
      .lever-row .lever-lbl { width: 120px; font-size: 13px; }
    }

    /* ── Inline editor styles (from inline-editing.js) ── */
    .edit-toggle-btn {
      background: transparent;
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--gray);
      cursor: pointer;
      font-size: 11px;
      padding: 2px 7px;
      margin-left: 8px;
      vertical-align: middle;
      transition: all 0.15s;
      font-family: system-ui, sans-serif;
    }
    .edit-toggle-btn:hover { border-color: var(--blue); color: var(--blue); }
    .inline-editor-textarea {
      width: 100%;
      min-height: 80px;
      padding: 10px;
      border: 2px solid var(--blue);
      border-radius: 6px;
      font-size: 15px;
      font-family: Georgia, serif;
      resize: vertical;
    }
    .inline-editor-controls { display: flex; gap: 8px; margin-top: 6px; }
    .editor-save-btn { background: var(--green); color: white; border: none; border-radius: 5px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
    .editor-cancel-btn { background: var(--gray-light); color: var(--text); border: 1px solid var(--border); border-radius: 5px; padding: 6px 14px; cursor: pointer; font-size: 13px; }
    .edit-saved-feedback { display: inline-block; color: var(--green); font-size: 12px; margin-left: 8px; animation: fadeOut 2s forwards; }
    @keyframes fadeOut { 0%{opacity:1} 70%{opacity:1} 100%{opacity:0} }
  </style>
</head>
<body>

<div class="topnav">
  <a href="index.html">← Home</a>
  <a href="meeting-page-v2.html" class="dim">Meeting Page</a>
  <a href="dashboard.html" class="dim">Dashboard</a>
  <span class="gen-meta">
    Generated ${today} &nbsp;|&nbsp;
    ${generationTime}ms &nbsp;|&nbsp;
    Personalization: <span class="score-badge">${Math.round(personalizationScore * 100)}%</span>
  </span>
</div>

<div class="container">

  <!-- ══ COVER ══ -->
  <div class="cover">
    <div class="cover-badge">Confidential — Sell-Side Representation</div>
    <h1>Next Chapter Partners Proposal<br>${this._esc(company)}</h1>
    <div class="sub">Prepared ${today} &nbsp;·&nbsp; ${this._esc(this.industryLabel(d))}</div>
    <div class="cover-stats">
      <div class="cover-stat">
        <div class="num">${this.fmtRevenue(revenue)}</div>
        <div class="lbl">Annual Revenue</div>
      </div>
      <div class="cover-stat">
        <div class="num">${this.fmt$(adjEbitda)}</div>
        <div class="lbl">Adj. EBITDA</div>
      </div>
      <div class="cover-stat">
        <div class="num">${this.fmt$(val.low)}–${this.fmt$(val.high)}</div>
        <div class="lbl">Valuation Range</div>
      </div>
      <div class="cover-stat">
        <div class="num">${this.timelineLabel(d.timeline_type)}</div>
        <div class="lbl">Target Timeline</div>
      </div>
    </div>
  </div>

  <!-- ══ 1. EXECUTIVE SUMMARY ══ -->
  <div class="section-card" id="section-exec-summary">
    <div class="section-header">
      <div style="display:flex;align-items:center">
        <div class="section-number">1</div>
        <div class="section-title">Executive Summary</div>
      </div>
    </div>
    <div class="section-inner">
      <div class="highlight-box editable-block" data-editable="true" data-editable-id="exec-summary-main">
        <strong>${this._esc(company)}</strong> is a ${this.fmtRevenue(revenue)} ${this._esc(this.industryLabel(d))} business with <strong>${growthRate > 0 ? growthRate + '% YoY growth' : 'stable revenue'}</strong>. The company generates approximately ${this.fmt$(estimatedEbitda)} in EBITDA with an adjusted EBITDA of ${this.fmt$(adjEbitda)} after owner add-backs — implying a valuation range of <strong>${this.fmt$(val.low)} to ${this.fmt$(val.high)}</strong>.
      </div>

      ${d.story_origin ? `
      <div class="editable-block" data-editable="true" data-editable-id="exec-summary-story" style="margin-bottom:16px">
        <p style="font-size:15px;color:var(--text-sm);"><strong>Origin:</strong> ${this._esc(d.story_origin)}</p>
      </div>` : ''}

      <div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:16px">
        <div>
          <span style="font-size:12px;color:var(--gray);font-family:system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.5px">Owner Motivation</span>
          <p style="font-weight:600;font-size:15px;margin-top:4px">${this._esc(this.motivationLabel(d.motivation_type))}</p>
        </div>
        <div>
          <span style="font-size:12px;color:var(--gray);font-family:system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.5px">Transaction Timeline</span>
          <p style="font-weight:600;font-size:15px;margin-top:4px">${this._esc(this.timelineLabel(d.timeline_type))}</p>
        </div>
      </div>

      ${d.motivation_quote ? `
      <blockquote style="border-left:3px solid var(--blue);padding:10px 16px;margin:16px 0;font-style:italic;color:var(--text-sm);font-size:15px">
        "${this._esc(d.motivation_quote)}"
      </blockquote>` : ''}
    </div>
  </div>

  <!-- ══ 2. COMPANY SNAPSHOT ══ -->
  <div class="section-card" id="section-company-snapshot">
    <div class="section-header">
      <div style="display:flex;align-items:center">
        <div class="section-number">2</div>
        <div class="section-title">Company Snapshot</div>
      </div>
    </div>
    <div class="section-inner">
      <div class="stat-grid">
        <div class="stat-cell">
          <div class="val">${this.fmtRevenue(revenue)}</div>
          <div class="lbl">Annual Revenue</div>
        </div>
        <div class="stat-cell">
          <div class="val">${growthRate > 0 ? '+' + growthRate + '%' : '—'}</div>
          <div class="lbl">YoY Growth</div>
        </div>
        <div class="stat-cell">
          <div class="val">${servicePct}%</div>
          <div class="lbl">Service Revenue</div>
        </div>
        <div class="stat-cell">
          <div class="val">${installPct}%</div>
          <div class="lbl">New Install</div>
        </div>
        ${d.recurring_revenue ? `
        <div class="stat-cell">
          <div class="val">${d.recurring_revenue}%</div>
          <div class="lbl">Recurring Revenue</div>
        </div>` : ''}
        ${d.owner_dependency ? `
        <div class="stat-cell">
          <div class="val">${d.owner_dependency}/10</div>
          <div class="lbl">Owner Dependency</div>
        </div>` : ''}
      </div>

      ${d.growth_notes ? `
      <div class="highlight-box editable-block" data-editable="true" data-editable-id="growth-drivers">
        <strong>Growth Drivers:</strong> ${this._esc(d.growth_notes)}
      </div>` : ''}

      ${keyPeople.length > 0 ? `
      <div style="margin-top:16px">
        <p style="font-size:13px;font-family:system-ui,sans-serif;color:var(--gray);text-transform:uppercase;letter-spacing:0.5px;margin-bottom:8px">Key Team Members</p>
        <div class="people-list">
          ${keyPeople.map(p => `
          <div class="person-pill">
            <span class="pname">${this._esc(p.name || p)}</span>
            ${p.role ? `<span class="prole">${this._esc(p.role)}</span>` : ''}
            ${p.years ? `<span class="prole">(${p.years}y)</span>` : ''}
          </div>`).join('')}
        </div>
      </div>` : ''}

      ${d.team_readiness ? `
      <div class="editable-block" data-editable="true" data-editable-id="team-readiness" style="margin-top:16px;padding:14px;background:var(--gray-light);border-radius:8px;font-size:14px;color:var(--text-sm)">
        <strong>Transition Readiness:</strong> ${this._esc(d.team_readiness)}
      </div>` : ''}

      ${d.story_challenge ? `
      <div class="editable-block" data-editable="true" data-editable-id="story-challenge" style="margin-top:14px;font-size:15px">
        <strong>Key Challenge Overcome:</strong> ${this._esc(d.story_challenge)}
      </div>` : ''}
    </div>
  </div>

  <!-- ══ 3. VALUATION ══ -->
  <div class="section-card" id="section-valuation">
    <div class="section-header">
      <div style="display:flex;align-items:center">
        <div class="section-number">3</div>
        <div class="section-title">Valuation Analysis</div>
      </div>
    </div>
    <div class="section-inner">
      <p style="font-size:14px;color:var(--gray);font-family:system-ui,sans-serif;margin-bottom:16px">
        Home services transactions trade at <strong>4–6x EBITDA</strong>. Range shown below is based on adjusted EBITDA including all owner add-backs.
      </p>

      <div class="val-range">
        <div class="val-band low">
          <div class="multiple">Conservative · 4x</div>
          <div class="amount" id="val-low">${this.fmt$(val.low)}</div>
          <div class="label">Floor</div>
        </div>
        <div class="val-band mid">
          <div class="multiple">Most Likely · 5x</div>
          <div class="amount" id="val-mid">${this.fmt$(val.mid)}</div>
          <div class="label">Recommended Target</div>
        </div>
        <div class="val-band high">
          <div class="multiple">Optimistic · 6x</div>
          <div class="amount" id="val-high">${this.fmt$(val.high)}</div>
          <div class="label">Ceiling</div>
        </div>
      </div>

      <div style="display:flex;gap:24px;flex-wrap:wrap;margin-top:16px;padding-top:16px;border-top:1px solid var(--border)">
        <div>
          <p style="font-size:12px;color:var(--gray);font-family:system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.5px">Stated EBITDA</p>
          <p style="font-size:20px;font-weight:700;font-family:system-ui,sans-serif;color:var(--navy);margin-top:4px" id="ebitda-stated">${this.fmt$(estimatedEbitda)}</p>
        </div>
        <div>
          <p style="font-size:12px;color:var(--gray);font-family:system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.5px">Add-backs</p>
          <p style="font-size:20px;font-weight:700;font-family:system-ui,sans-serif;color:var(--green);margin-top:4px" id="val-addbacks">+${this.fmt$(addbacks)}</p>
        </div>
        <div style="background:var(--green-light);border:1px solid #9ae6b4;border-radius:8px;padding:10px 16px">
          <p style="font-size:12px;color:var(--green);font-family:system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.5px">Adjusted EBITDA</p>
          <p style="font-size:20px;font-weight:700;font-family:system-ui,sans-serif;color:var(--green);margin-top:4px" id="val-adj-ebitda">${this.fmt$(adjEbitda)}</p>
        </div>
      </div>
    </div>
  </div>

  <!-- ══ 4. EBITDA LEVERS ══ -->
  <div class="section-card" id="section-ebitda-levers">
    <div class="section-header">
      <div style="display:flex;align-items:center">
        <div class="section-number">4</div>
        <div class="section-title">EBITDA Levers &amp; Add-backs</div>
      </div>
    </div>
    <div class="section-inner">

      <div class="highlight-box" style="margin-bottom:20px">
        <strong>EBITDA Margin:</strong> ${this.fmtPct(ebitdaMargin)}
        &nbsp;·&nbsp;
        <strong>Industry Benchmark:</strong> ${this.fmtPct(this.INDUSTRY_MARGIN_BENCHMARK * 100)}
        &nbsp;·&nbsp;
        <strong>${ebitdaMargin >= this.INDUSTRY_MARGIN_BENCHMARK * 100 ? 'Above benchmark' : 'Expansion opportunity'}</strong>
      </div>

      <div style="margin-bottom:8px;font-size:13px;font-family:system-ui,sans-serif;color:var(--gray);text-transform:uppercase;letter-spacing:0.5px">Margin Profile vs. Industry</div>
      <div class="lever-row">
        <div class="lever-lbl">${this._esc(company)}</div>
        <div class="lever-bar-wrap"><div class="lever-bar" style="width:${Math.min(100, ebitdaMargin)}%"></div></div>
        <div class="lever-val">${this.fmtPct(ebitdaMargin)}</div>
      </div>
      <div class="lever-row">
        <div class="lever-lbl" style="color:var(--gray)">Industry Avg.</div>
        <div class="lever-bar-wrap"><div class="lever-bar" style="width:${this.INDUSTRY_MARGIN_BENCHMARK * 100}%;background:var(--border)"></div></div>
        <div class="lever-val" style="color:var(--gray)">${this.fmtPct(this.INDUSTRY_MARGIN_BENCHMARK * 100)}</div>
      </div>

      <div style="margin-top:24px;margin-bottom:8px;font-size:13px;font-family:system-ui,sans-serif;color:var(--gray);text-transform:uppercase;letter-spacing:0.5px">Owner Add-backs</div>
      <table class="addbacks-table">
        <thead>
          <tr>
            <th>Add-back Item</th>
            <th style="text-align:right">Annual Amount</th>
          </tr>
        </thead>
        <tbody>
          ${parseFloat(d.vehicle_allowance) > 0 ? `<tr><td>Vehicle Allowance</td><td>${this.fmt$(d.vehicle_allowance)}</td></tr>` : ''}
          ${parseFloat(d.family_salary) > 0 ? `<tr><td>Family Member Salary</td><td>${this.fmt$(d.family_salary)}</td></tr>` : ''}
          ${parseFloat(d.travel_entertainment) > 0 ? `<tr><td>Travel &amp; Entertainment</td><td>${this.fmt$(d.travel_entertainment)}</td></tr>` : ''}
          ${parseFloat(d.insurance_benefits) > 0 ? `<tr><td>Insurance / Benefits</td><td>${this.fmt$(d.insurance_benefits)}</td></tr>` : ''}
          ${addbacks === 0 ? `<tr><td colspan="2" style="color:var(--gray);font-style:italic">No add-backs captured — update meeting data to populate</td></tr>` : ''}
          <tr class="total">
            <td><strong>Total Add-backs</strong></td>
            <td id="addbacks-total"><strong>${this.fmt$(addbacks)}</strong></td>
          </tr>
        </tbody>
      </table>

      ${d.margins_notes ? `
      <div class="editable-block" data-editable="true" data-editable-id="margins-notes" style="font-size:14px;color:var(--text-sm);margin-top:8px">
        <strong>Notes:</strong> ${this._esc(d.margins_notes)}
      </div>` : ''}

      <div class="highlight-box gold" style="margin-top:20px">
        <strong>Synergy Opportunity:</strong> ${revenue > 0 && ebitdaMargin < 22 ? `Margin expansion of ${(22 - ebitdaMargin).toFixed(1)} points to reach industry benchmark would add ${this.fmt$(revenue * (22 - ebitdaMargin) / 100)} in annual EBITDA.` : `Current margin is at or above the ${this.fmtPct(22)} industry benchmark — a premium multiple is supportable.`}
      </div>
    </div>
  </div>

  <!-- ══ 5. PROCESS TIMELINE ══ -->
  <div class="section-card" id="section-timeline">
    <div class="section-header">
      <div style="display:flex;align-items:center">
        <div class="section-number">5</div>
        <div class="section-title">Process Timeline</div>
      </div>
    </div>
    <div class="section-inner">
      <div class="timeline-track">
        ${timeline.map((step, i) => `
        <div class="timeline-step">
          <div class="tl-dot ${step.active ? 'active' : i === 0 ? 'done' : ''}">${i + 1}</div>
          <div class="tl-content">
            <div class="tl-label">${this._esc(step.label)}</div>
            <div class="tl-date">${step.date}${step.offset > 0 ? ` (+${step.offset} days)` : ''}</div>
            ${step.active ? `<div class="tl-note" style="color:var(--green)">Today — letter delivered</div>` : ''}
          </div>
        </div>`).join('')}
      </div>

      ${d.timeline_notes ? `
      <div class="highlight-box" style="margin-top:16px">
        <strong>Owner Timeline Notes:</strong> ${this._esc(d.timeline_notes)}
      </div>` : ''}
    </div>
  </div>

  <!-- ══ 6. DEAL STRUCTURE ══ -->
  <div class="section-card" id="section-deal-structure">
    <div class="section-header">
      <div style="display:flex;align-items:center">
        <div class="section-number">6</div>
        <div class="section-title">Proposed Deal Structure</div>
      </div>
    </div>
    <div class="section-inner">
      ${dealStructures.map(s => `
      <div class="deal-card ${s.highlight ? 'highlight' : ''}">
        <div class="deal-type">${s.highlight ? '★ ' : ''}${this._esc(s.type)}</div>
        <p style="font-size:15px;color:var(--text-sm)">${this._esc(s.description)}</p>
      </div>`).join('')}

      ${d.deal_killer ? `
      <div class="editable-block" data-editable="true" data-editable-id="deal-considerations" style="margin-top:16px;padding:14px;background:#fff5f5;border:1px solid #fc8181;border-radius:8px;font-size:14px">
        <strong>Considerations to Address:</strong> ${this._esc(d.deal_killer)}
      </div>` : ''}

      ${d.hidden_concerns ? `
      <div class="editable-block" data-editable="true" data-editable-id="hidden-concerns" style="margin-top:12px;padding:14px;background:var(--gold-light);border:1px solid #f6ad55;border-radius:8px;font-size:14px">
        <strong>Unstated Concerns:</strong> ${this._esc(d.hidden_concerns)}
      </div>` : ''}
    </div>
  </div>

  <!-- ══ 7. FEE STRUCTURE ══ -->
  <div class="section-card" id="section-fees">
    <div class="section-header">
      <div style="display:flex;align-items:center">
        <div class="section-number">7</div>
        <div class="section-title">Fee Structure</div>
      </div>
    </div>
    <div class="section-inner">
      <div class="fee-calc">
        <div>
          <div class="fee-num" id="fee-amount">${this.fmt$(fee)}</div>
          <div class="fee-note">Success fee — paid only at close</div>
        </div>
        <div class="fee-breakdown">
          <p>${this.fmt$(val.mid)} valuation × ${val.mid <= 5000000 ? '1.0%' : 'tiered rate'}</p>
          <p style="margin-top:6px;opacity:0.6">No retainer. No monthly fees.</p>
          <p style="margin-top:4px;opacity:0.6">You pay nothing unless we close.</p>
        </div>
      </div>

      <div style="margin-top:20px">
        <div style="font-size:13px;color:var(--gray);font-family:system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:12px">Fee at Different Valuation Outcomes</div>
        <div style="display:flex;gap:12px;flex-wrap:wrap">
          ${[val.low, val.mid, val.high].map((v, i) => `
          <div style="flex:1;min-width:140px;background:var(--gray-light);border:1px solid var(--border);border-radius:8px;padding:14px;text-align:center">
            <div style="font-size:11px;color:var(--gray);font-family:system-ui,sans-serif;text-transform:uppercase;letter-spacing:0.5px">${['Floor', 'Mid', 'Ceiling'][i]}</div>
            <div style="font-size:18px;font-weight:700;color:var(--navy);font-family:system-ui,sans-serif;margin-top:4px">${this.fmt$(this.calcFee(v))}</div>
            <div style="font-size:12px;color:var(--gray);font-family:system-ui,sans-serif">on ${this.fmt$(v)} deal</div>
          </div>`).join('')}
        </div>
      </div>
    </div>
  </div>

  <!-- ══ REACTIVE RECALCULATOR ══ -->
  <div class="section-card" id="section-recalc" style="border:2px dashed var(--blue)">
    <div class="section-header">
      <div style="display:flex;align-items:center">
        <div class="section-number" style="background:var(--blue)">↺</div>
        <div class="section-title" style="color:var(--blue)">Live Recalculator</div>
      </div>
    </div>
    <div class="section-inner">
      <p style="font-size:14px;color:var(--gray);font-family:system-ui,sans-serif;margin-bottom:16px">Change any value — all sections update instantly.</p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px">

        <div>
          <label style="font-size:12px;font-family:system-ui,sans-serif;color:var(--gray);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:6px">Annual Revenue ($)</label>
          <input type="number" id="rc-revenue" value="${revenue}" class="reactive-input" style="width:100%;padding:8px 10px;border:1.5px solid var(--border);border-radius:6px;font-size:15px;font-family:system-ui,sans-serif;color:var(--navy);border-bottom:2px dashed var(--blue)">
        </div>
        <div>
          <label style="font-size:12px;font-family:system-ui,sans-serif;color:var(--gray);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:6px">EBITDA ($)</label>
          <input type="number" id="rc-ebitda" value="${estimatedEbitda}" class="reactive-input" style="width:100%;padding:8px 10px;border:1.5px solid var(--border);border-radius:6px;font-size:15px;font-family:system-ui,sans-serif;color:var(--navy);border-bottom:2px dashed var(--blue)">
        </div>
        <div>
          <label style="font-size:12px;font-family:system-ui,sans-serif;color:var(--gray);text-transform:uppercase;letter-spacing:0.5px;display:block;margin-bottom:6px">Add-backs ($)</label>
          <input type="number" id="rc-addbacks" value="${addbacks}" class="reactive-input" style="width:100%;padding:8px 10px;border:1.5px solid var(--border);border-radius:6px;font-size:15px;font-family:system-ui,sans-serif;color:var(--navy);border-bottom:2px dashed var(--blue)">
        </div>
      </div>
      <div style="margin-top:14px;padding:14px;background:var(--blue-light);border-radius:8px;font-family:system-ui,sans-serif;font-size:14px" id="rc-output">
        Adj. EBITDA: <strong id="rc-adj-ebitda">${this.fmt$(adjEbitda)}</strong> &nbsp;·&nbsp;
        Low: <strong id="rc-val-low">${this.fmt$(val.low)}</strong> &nbsp;·&nbsp;
        Mid: <strong id="rc-val-mid">${this.fmt$(val.mid)}</strong> &nbsp;·&nbsp;
        High: <strong id="rc-val-high">${this.fmt$(val.high)}</strong> &nbsp;·&nbsp;
        Fee: <strong id="rc-fee">${this.fmt$(fee)}</strong>
      </div>
    </div>
  </div>

  <div class="conf-footer">
    <strong>CONFIDENTIAL — FOR RECIPIENT USE ONLY</strong><br>
    This proposal was prepared by Next Chapter Partners on ${today}.<br>
    All valuations are estimates based on information provided. Final terms subject to due diligence.<br>
    Personalization Score: ${Math.round(personalizationScore * 100)}% &nbsp;·&nbsp; Generated in ${generationTime}ms
  </div>

</div>

<script>
// ── Reactive Recalculator ──
(function() {
  const MULTIPLES = { low: 4, mid: 5, high: 6 };

  function fmt(n) {
    n = parseFloat(n) || 0;
    if (n >= 1000000) return '$' + (n / 1000000).toFixed(2).replace(/\\.?0+$/, '') + 'M';
    if (n >= 1000) return '$' + Math.round(n / 1000) + 'K';
    return '$' + Math.round(n).toLocaleString();
  }

  function calcFee(mid) {
    if (mid <= 5000000) return mid * 0.01;
    return 5000000 * 0.01 + (mid - 5000000) * 0.0075;
  }

  function recalc() {
    const ebitda = parseFloat(document.getElementById('rc-ebitda').value) || 0;
    const ab = parseFloat(document.getElementById('rc-addbacks').value) || 0;
    const adj = ebitda + ab;
    const low = adj * MULTIPLES.low;
    const mid = adj * MULTIPLES.mid;
    const high = adj * MULTIPLES.high;
    const fee = calcFee(mid);

    // Update recalc panel
    document.getElementById('rc-adj-ebitda').textContent = fmt(adj);
    document.getElementById('rc-val-low').textContent = fmt(low);
    document.getElementById('rc-val-mid').textContent = fmt(mid);
    document.getElementById('rc-val-high').textContent = fmt(high);
    document.getElementById('rc-fee').textContent = fmt(fee);

    // Update valuation section
    if (document.getElementById('val-low')) document.getElementById('val-low').textContent = fmt(low);
    if (document.getElementById('val-mid')) document.getElementById('val-mid').textContent = fmt(mid);
    if (document.getElementById('val-high')) document.getElementById('val-high').textContent = fmt(high);
    if (document.getElementById('val-adj-ebitda')) document.getElementById('val-adj-ebitda').textContent = fmt(adj);
    if (document.getElementById('val-addbacks')) document.getElementById('val-addbacks').textContent = '+' + fmt(ab);
    if (document.getElementById('ebitda-stated')) document.getElementById('ebitda-stated').textContent = fmt(ebitda);
    if (document.getElementById('addbacks-total')) document.getElementById('addbacks-total').innerHTML = '<strong>' + fmt(ab) + '</strong>';
    if (document.getElementById('fee-amount')) document.getElementById('fee-amount').textContent = fmt(fee);
  }

  ['rc-revenue', 'rc-ebitda', 'rc-addbacks'].forEach(function(id) {
    var el = document.getElementById(id);
    if (el) el.addEventListener('input', recalc);
  });

  // ── Smooth section scroll ──
  document.querySelectorAll('a[href^="#"]').forEach(function(a) {
    a.addEventListener('click', function(e) {
      var target = document.querySelector(this.getAttribute('href'));
      if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    });
  });
})();
</script>

<script src="inline-editing.js"></script>

</body>
</html>`;
  }

  // HTML escape
  _esc(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
}

// ─────────────────────────────────────────────
// Browser: expose globally
// ─────────────────────────────────────────────
if (typeof window !== 'undefined') {
  window.ProposalAutoGenerator = ProposalAutoGenerator;

  // If opened with ?meeting_data=... URL param, auto-generate and render
  document.addEventListener('DOMContentLoaded', function () {
    const params = new URLSearchParams(window.location.search);
    if (params.has('meeting_data')) {
      try {
        const raw = JSON.parse(decodeURIComponent(params.get('meeting_data')));
        const gen = new ProposalAutoGenerator();
        const result = gen.generate(raw);
        document.open();
        document.write(result.html);
        document.close();
      } catch (e) {
        console.error('[ProposalAutoGenerator] Failed to parse meeting_data param:', e);
      }
    }
  });
}

// ─────────────────────────────────────────────
// Node.js: export for API route
// ─────────────────────────────────────────────
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { ProposalAutoGenerator };
}
