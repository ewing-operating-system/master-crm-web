/**
 * interactive-proposal-template.js — Buy-Side Interactive Proposal Engine
 * Feature #41: Target criteria sliders, fee selection, buyer match scoring.
 *
 * Usage: new InteractiveProposal({ containerId: 'app', proposalId: '...' })
 */
(function () {
  'use strict';

  const SUPABASE_URL = window.__SUPABASE_URL;
  const SUPABASE_KEY = window.__SUPABASE_ANON_KEY;

  const headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
    'Content-Type': 'application/json',
  };

  // Fee modes
  const FEE_MODES = [
    { id: 'standard', name: 'Standard', desc: '5% of transaction value', rate: '5%' },
    { id: 'performance', name: 'Performance', desc: '3% base + 2% bonus above floor', rate: '3-5%' },
    { id: 'hybrid', name: 'Hybrid', desc: '2% retainer + 3% success', rate: '2%+3%' },
    { id: 'flat', name: 'Flat Fee', desc: 'Fixed advisory fee', rate: 'Fixed' },
    { id: 'success_only', name: 'Success Only', desc: 'No fee unless deal closes', rate: '6%' },
  ];

  class InteractiveProposal {
    constructor(opts) {
      this.containerId = opts.containerId || 'app';
      this.proposalId = opts.proposalId || new URLSearchParams(window.location.search).get('proposal_id');
      this.sellers = [];
      this.criteria = {
        revenueMin: 1000000,
        revenueMax: 50000000,
        ebitdaMin: 10,
        ebitdaMax: 40,
        employeesMin: 5,
        employeesMax: 500,
        verticals: [],
        geography: [],
      };
      this.selectedFee = 'standard';
      this.emailGated = false;

      this.init();
    }

    async init() {
      const container = document.getElementById(this.containerId);
      if (!container) return;
      container.innerHTML = '<div style="text-align:center;padding:60px;color:#8b949e">Loading proposal...</div>';

      if (this.proposalId) {
        await this.loadProposal();
      }
      this.render();
    }

    async loadProposal() {
      try {
        const r = await fetch(`${SUPABASE_URL}/rest/v1/proposals?id=eq.${this.proposalId}&select=*`, { headers });
        const data = await r.json();
        if (data.length) {
          this.proposal = data[0];
        }

        // Load sellers/targets for this proposal
        const s = await fetch(`${SUPABASE_URL}/rest/v1/engagement_buyers?proposal_id=eq.${this.proposalId}&select=*&order=fit_score.desc`, { headers });
        this.sellers = await s.json();
      } catch (e) {
        console.error('Load error:', e);
      }
    }

    matchScore(seller) {
      let score = 0;
      let factors = 0;

      // Revenue match
      const rev = parseFloat(seller.estimated_revenue || 0);
      if (rev >= this.criteria.revenueMin && rev <= this.criteria.revenueMax) {
        score += 30;
      } else if (rev > 0) {
        const dist = Math.min(
          Math.abs(rev - this.criteria.revenueMin),
          Math.abs(rev - this.criteria.revenueMax)
        );
        score += Math.max(0, 30 - (dist / this.criteria.revenueMax) * 30);
      }
      factors++;

      // EBITDA margin match
      const ebitda = parseFloat(seller.ebitda_margin || 0);
      if (ebitda >= this.criteria.ebitdaMin && ebitda <= this.criteria.ebitdaMax) {
        score += 25;
      }
      factors++;

      // Employee count match
      const emp = parseInt(seller.employee_count || 0);
      if (emp >= this.criteria.employeesMin && emp <= this.criteria.employeesMax) {
        score += 20;
      }
      factors++;

      // Fit score from buyer research
      const fit = parseInt(seller.fit_score || 0);
      score += (fit / 8) * 25;
      factors++;

      return Math.round(score);
    }

    renderSlider(label, id, min, max, value, unit, step) {
      return `
        <div style="margin-bottom:15px">
          <label style="color:#8b949e;font-size:12px;display:block;margin-bottom:5px">${label}</label>
          <input type="range" id="${id}" min="${min}" max="${max}" value="${value}" step="${step || 1}"
            style="width:100%;accent-color:#58a6ff" oninput="document.getElementById('${id}_val').textContent=this.value">
          <span id="${id}_val" style="color:#58a6ff;font-size:13px">${value}</span>
          <span style="color:#8b949e;font-size:11px">${unit}</span>
        </div>`;
    }

    renderFeeSelector() {
      return FEE_MODES.map(f => `
        <div onclick="window._proposal.selectFee('${f.id}')" id="fee_${f.id}"
          style="background:${f.id === this.selectedFee ? '#1a3a5c' : '#21262d'};border:1px solid ${f.id === this.selectedFee ? '#58a6ff' : '#30363d'};
          border-radius:8px;padding:12px;margin-bottom:8px;cursor:pointer;transition:all 0.2s">
          <div style="color:#f0f6fc;font-weight:600;font-size:14px">${f.name} <span style="float:right;color:#58a6ff">${f.rate}</span></div>
          <div style="color:#8b949e;font-size:12px;margin-top:4px">${f.desc}</div>
        </div>
      `).join('');
    }

    renderSellerCard(seller) {
      const score = this.matchScore(seller);
      const color = score >= 70 ? '#27ae60' : score >= 40 ? '#f39c12' : '#e74c3c';
      const name = seller.company_name || seller.buyer_name || 'Unknown';
      const rev = seller.estimated_revenue ? `$${(seller.estimated_revenue / 1000000).toFixed(1)}M` : 'N/A';
      const fit = seller.fit_score || 'N/A';

      return `
        <div style="background:#21262d;border:1px solid #30363d;border-radius:8px;padding:15px;margin-bottom:10px">
          <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
              <div style="color:#f0f6fc;font-weight:600">${name}</div>
              <div style="color:#8b949e;font-size:12px">${seller.city || ''} ${seller.state || ''} | Revenue: ${rev} | Fit: ${fit}/8</div>
            </div>
            <div style="background:${color}20;color:${color};padding:5px 12px;border-radius:20px;font-weight:bold;font-size:14px">
              ${score}%
            </div>
          </div>
          <div style="background:#161b22;border-radius:4px;height:6px;margin-top:10px;overflow:hidden">
            <div style="background:${color};height:100%;width:${score}%;border-radius:4px;transition:width 0.3s"></div>
          </div>
        </div>`;
    }

    render() {
      const container = document.getElementById(this.containerId);
      const sorted = [...this.sellers].sort((a, b) => this.matchScore(b) - this.matchScore(a));
      const proposalName = this.proposal?.company_name || 'Buy-Side Proposal';

      container.innerHTML = `
        <div style="max-width:1200px;margin:0 auto;padding:20px">
          <div style="display:grid;grid-template-columns:350px 1fr;gap:20px">
            <!-- Left: Criteria -->
            <div>
              <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:20px">
                <h2 style="color:#58a6ff;font-size:16px;margin-bottom:15px;padding-bottom:8px;border-bottom:1px solid #30363d">Target Criteria</h2>
                ${this.renderSlider('Revenue Range (Min)', 'rev_min', 500000, 100000000, this.criteria.revenueMin, '$', 500000)}
                ${this.renderSlider('Revenue Range (Max)', 'rev_max', 1000000, 200000000, this.criteria.revenueMax, '$', 1000000)}
                ${this.renderSlider('EBITDA Margin (Min %)', 'ebitda_min', 0, 50, this.criteria.ebitdaMin, '%')}
                ${this.renderSlider('EBITDA Margin (Max %)', 'ebitda_max', 5, 60, this.criteria.ebitdaMax, '%')}
                ${this.renderSlider('Employees (Min)', 'emp_min', 1, 200, this.criteria.employeesMin, '')}
                ${this.renderSlider('Employees (Max)', 'emp_max', 10, 1000, this.criteria.employeesMax, '')}
                <button onclick="window._proposal.applyFilters()" style="width:100%;padding:10px;background:#58a6ff;color:#0d1117;border:none;border-radius:8px;font-weight:bold;cursor:pointer;margin-top:10px">
                  Apply Filters
                </button>
              </div>
              <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px">
                <h2 style="color:#58a6ff;font-size:16px;margin-bottom:15px;padding-bottom:8px;border-bottom:1px solid #30363d">Fee Structure</h2>
                ${this.renderFeeSelector()}
              </div>
            </div>
            <!-- Right: Results -->
            <div>
              <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-bottom:20px">
                <h2 style="color:#58a6ff;font-size:16px;margin-bottom:5px">${proposalName}</h2>
                <p style="color:#8b949e;font-size:13px">${sorted.length} matching targets ranked by fit</p>
              </div>
              <div id="seller_list">
                ${sorted.length ? sorted.map(s => this.renderSellerCard(s)).join('') :
                  '<div style="text-align:center;padding:40px;color:#8b949e">No matching targets. Adjust criteria.</div>'}
              </div>
              <div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:20px;margin-top:20px;text-align:center">
                <h3 style="color:#f0f6fc;margin-bottom:10px">Ready to Get Started?</h3>
                <p style="color:#8b949e;font-size:13px;margin-bottom:15px">Schedule a call to discuss these targets and our approach.</p>
                <button style="padding:12px 30px;background:#27ae60;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:bold;cursor:pointer">
                  Schedule a Call
                </button>
              </div>
            </div>
          </div>
        </div>`;
    }

    applyFilters() {
      this.criteria.revenueMin = parseInt(document.getElementById('rev_min')?.value || 0);
      this.criteria.revenueMax = parseInt(document.getElementById('rev_max')?.value || 50000000);
      this.criteria.ebitdaMin = parseInt(document.getElementById('ebitda_min')?.value || 0);
      this.criteria.ebitdaMax = parseInt(document.getElementById('ebitda_max')?.value || 40);
      this.criteria.employeesMin = parseInt(document.getElementById('emp_min')?.value || 5);
      this.criteria.employeesMax = parseInt(document.getElementById('emp_max')?.value || 500);
      this.render();
    }

    selectFee(id) {
      this.selectedFee = id;
      this.render();
    }
  }

  window.InteractiveProposal = InteractiveProposal;
  window._proposal = null;

  // Auto-init if container exists
  if (document.getElementById('app')) {
    window._proposal = new InteractiveProposal({ containerId: 'app' });
  }
})();
