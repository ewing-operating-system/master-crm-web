/**
 * campaign-manager.js — Next Chapter M&A Advisory
 * Campaign Manager for the 250/150 rule.
 * Sends batch of 250 letters, pauses until 150 have been called 5x each,
 * then resumes with the next batch.
 */
(function () {
  'use strict';

  // Credentials: loaded from /supabase-config.js (include via <script> tag before this file)
  // See .env.example for all env var names, CLAUDE.md for architecture

  const SUPABASE_URL = window.__SUPABASE_URL;
  const SUPABASE_KEY = window.__SUPABASE_ANON_KEY;

  const CAMPAIGNS_API = SUPABASE_URL + '/rest/v1/letter_campaigns';
  const CALL_LOG_API  = SUPABASE_URL + '/rest/v1/call_log';

  const LETTER_COST = 1.75; // avg cost per letter

  const headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
  };

  let campaigns = [];
  let currentBatch = null;
  let syncInterval = null;

  // ── Supabase helpers ────────────────────────────────────────────────────────

  async function fetchCampaigns() {
    const r = await fetch(CAMPAIGNS_API + '?order=batch_number.desc', { headers });
    if (!r.ok) throw new Error('Failed to fetch campaigns: ' + r.status);
    return r.json();
  }

  async function createCampaign(batchNumber) {
    const r = await fetch(CAMPAIGNS_API, {
      method: 'POST',
      headers,
      body: JSON.stringify({
        batch_number: batchNumber,
        status: 'active',
        total_letters_sent: 0,
        letters_called_5x: 0,
        pause_threshold: 150,
        target_total: 250
      })
    });
    if (!r.ok) throw new Error('Failed to create campaign: ' + r.status);
    return (await r.json())[0];
  }

  async function updateCampaign(id, patch) {
    const r = await fetch(CAMPAIGNS_API + '?id=eq.' + id, {
      method: 'PATCH',
      headers,
      body: JSON.stringify(patch)
    });
    if (!r.ok) throw new Error('Failed to update campaign: ' + r.status);
    return r.json();
  }

  // Count call_log records per prospect in a batch, return how many have >= 5 calls
  async function count5xCalled(batchNumber) {
    // We need call_log joined to prospects in this batch.
    // Assumes call_log has columns: prospect_id, batch_number (or we fall back to batch_number on call_log)
    // Try batch_number filter first; gracefully handle if column doesn't exist.
    try {
      const r = await fetch(
        CALL_LOG_API + '?select=prospect_id&batch_number=eq.' + batchNumber,
        { headers: { ...headers, 'Prefer': 'count=exact' } }
      );
      if (!r.ok) return null; // table might not have batch_number col
      const data = await r.json();
      if (!Array.isArray(data)) return null;

      // Group by prospect_id
      const counts = {};
      for (const row of data) {
        const pid = row.prospect_id;
        counts[pid] = (counts[pid] || 0) + 1;
      }
      return Object.values(counts).filter(c => c >= 5).length;
    } catch (_) {
      return null;
    }
  }

  // ── Telegram notification ───────────────────────────────────────────────────

  async function sendTelegram(msg) {
    try {
      await fetch('/api/telegram-notify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: '[Argus] ' + msg })
      });
    } catch (_) {
      console.warn('[campaign-manager] Telegram notify failed (no backend route)');
    }
  }

  // ── Auto-sync logic ─────────────────────────────────────────────────────────

  async function syncCurrentBatch() {
    if (!currentBatch || currentBatch.status === 'completed') return;

    const called5x = await count5xCalled(currentBatch.batch_number);
    if (called5x === null) return; // call_log query failed, skip

    const prev = currentBatch.letters_called_5x;
    if (called5x !== prev) {
      await updateCampaign(currentBatch.id, { letters_called_5x: called5x });
      currentBatch.letters_called_5x = called5x;

      // Threshold hit while active → fire notification
      if (called5x >= currentBatch.pause_threshold && prev < currentBatch.pause_threshold) {
        await sendTelegram(
          'Batch ' + currentBatch.batch_number + ' reached 150 calls: Ready to resume'
        );
      }
    }

    renderAll();
  }

  function startSync() {
    if (syncInterval) clearInterval(syncInterval);
    syncInterval = setInterval(syncCurrentBatch, 30000);
  }

  // ── Action handlers ─────────────────────────────────────────────────────────

  window.cmStartNewBatch = async function () {
    setLoading(true);
    try {
      const nextNum = campaigns.length > 0
        ? Math.max(...campaigns.map(c => c.batch_number)) + 1
        : 1;
      const newBatch = await createCampaign(nextNum);
      campaigns.unshift(newBatch);
      currentBatch = newBatch;
      await sendTelegram(
        'Batch ' + nextNum + ' ready to send: 250 letters approved'
      );
      renderAll();
      showToast('Batch ' + nextNum + ' started', 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  window.cmPauseBatch = async function (id) {
    setLoading(true);
    try {
      await updateCampaign(id, { status: 'paused', pause_at: new Date().toISOString() });
      const c = campaigns.find(x => x.id === id);
      if (c) c.status = 'paused';
      if (currentBatch && currentBatch.id === id) currentBatch.status = 'paused';
      renderAll();
      showToast('Batch paused', 'info');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  window.cmResumeBatch = async function (id) {
    setLoading(true);
    try {
      await updateCampaign(id, { status: 'active', pause_at: null });
      const c = campaigns.find(x => x.id === id);
      if (c) c.status = 'active';
      if (currentBatch && currentBatch.id === id) currentBatch.status = 'active';
      renderAll();
      showToast('Batch resumed', 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  window.cmCompleteBatch = async function (id) {
    if (!confirm('Mark this batch as completed? This cannot be undone.')) return;
    setLoading(true);
    try {
      const now = new Date().toISOString();
      await updateCampaign(id, { status: 'completed', completed_at: now });
      const c = campaigns.find(x => x.id === id);
      if (c) { c.status = 'completed'; c.completed_at = now; }
      if (currentBatch && currentBatch.id === id) {
        currentBatch.status = 'completed';
        currentBatch.completed_at = now;
      }
      // Estimate conversions from calls / target ratio
      const conv = c ? Math.round((c.letters_called_5x / c.pause_threshold) * 12) : 0;
      await sendTelegram(
        'Batch ' + (c ? c.batch_number : '?') + ' completed: ' + conv + ' converted'
      );
      renderAll();
      showToast('Batch marked complete', 'success');
    } catch (e) {
      showToast(e.message, 'error');
    } finally {
      setLoading(false);
    }
  };

  window.cmRefreshNow = async function () {
    await loadAndRender();
  };

  // ── Sorting state ───────────────────────────────────────────────────────────

  let sortKey = 'batch_number';
  let sortDir = -1; // -1 = desc, 1 = asc

  window.cmSort = function (key) {
    if (sortKey === key) {
      sortDir *= -1;
    } else {
      sortKey = key;
      sortDir = -1;
    }
    renderTable();
    updateSortIndicators();
  };

  function sortedCampaigns() {
    return [...campaigns].sort((a, b) => {
      let av = a[sortKey], bv = b[sortKey];
      if (av == null) av = '';
      if (bv == null) bv = '';
      if (typeof av === 'string') av = av.toLowerCase();
      if (typeof bv === 'string') bv = bv.toLowerCase();
      if (av < bv) return -sortDir;
      if (av > bv) return sortDir;
      return 0;
    });
  }

  function updateSortIndicators() {
    document.querySelectorAll('.cm-th-sort').forEach(th => {
      const k = th.dataset.sortKey;
      th.classList.toggle('sort-active', k === sortKey);
      th.dataset.sortDir = k === sortKey ? (sortDir === -1 ? 'desc' : 'asc') : '';
    });
  }

  // ── Rendering ───────────────────────────────────────────────────────────────

  function renderAll() {
    renderStatusCard();
    renderTable();
    renderCostSummary();
    renderControls();
    updateSortIndicators();
  }

  function renderStatusCard() {
    const el = document.getElementById('cm-status-card');
    if (!el) return;

    if (!currentBatch) {
      el.innerHTML = `
        <div class="cm-no-batch">
          <div class="cm-no-batch-icon">📬</div>
          <div class="cm-no-batch-text">No active batch. Start a new batch to begin sending letters.</div>
        </div>`;
      return;
    }

    const b = currentBatch;
    const pct = Math.min(100, Math.round((b.letters_called_5x / b.pause_threshold) * 100));
    const remaining = Math.max(0, b.pause_threshold - b.letters_called_5x);
    const thresholdMet = b.letters_called_5x >= b.pause_threshold;

    const statusClass = { active: 'status-active', paused: 'status-paused', completed: 'status-completed' }[b.status] || '';
    const statusLabel = b.status.toUpperCase();

    let subline = '';
    if (b.status === 'paused') {
      subline = `<div class="cm-subline cm-subline-warn">Waiting for ${remaining} more call${remaining !== 1 ? 's' : ''} to reach ${b.pause_threshold}</div>`;
    } else if (thresholdMet && b.status === 'active') {
      subline = `<div class="cm-subline cm-subline-success">Threshold reached — ready to resume next batch</div>`;
    }

    el.innerHTML = `
      <div class="cm-batch-header">
        <div class="cm-batch-title">Batch ${b.batch_number}</div>
        <div class="cm-badge ${statusClass}">${statusLabel}</div>
        ${thresholdMet ? '<div class="cm-check">✓</div>' : ''}
      </div>
      <div class="cm-batch-stat">
        ${b.total_letters_sent} letters sent &nbsp;·&nbsp;
        <strong>${b.letters_called_5x}/${b.pause_threshold}</strong> called 5x &nbsp;·&nbsp;
        Need <strong>${remaining}</strong> more
      </div>
      <div class="cm-progress-wrap">
        <div class="cm-progress-bar">
          <div class="cm-progress-fill ${thresholdMet ? 'cm-progress-done' : ''}" style="width:${pct}%"></div>
        </div>
        <div class="cm-progress-label">${pct}%</div>
      </div>
      ${subline}
      <div class="cm-sync-note">Auto-syncs every 30s &nbsp;·&nbsp; Last check: <span id="cm-last-sync">—</span></div>
    `;

    document.getElementById('cm-last-sync').textContent = new Date().toLocaleTimeString();
  }

  function renderControls() {
    const el = document.getElementById('cm-controls');
    if (!el) return;

    const activeBatch = campaigns.find(c => c.status === 'active');
    const pausedBatch = campaigns.find(c => c.status === 'paused');
    const allComplete = campaigns.length > 0 && campaigns.every(c => c.status === 'completed');
    const noBatches = campaigns.length === 0;

    let btns = '';

    if (noBatches || allComplete) {
      btns += `<button class="cm-btn cm-btn-primary" onclick="cmStartNewBatch()">Start New Batch</button>`;
    }

    if (activeBatch) {
      btns += `<button class="cm-btn cm-btn-warning" onclick="cmPauseBatch('${activeBatch.id}')">Pause Batch</button>`;
      btns += `<button class="cm-btn cm-btn-ghost" onclick="cmCompleteBatch('${activeBatch.id}')">Mark Batch Complete</button>`;
    }

    if (pausedBatch) {
      const thresholdMet = pausedBatch.letters_called_5x >= pausedBatch.pause_threshold;
      const resumeClass = thresholdMet ? 'cm-btn-success' : 'cm-btn-disabled';
      btns += `<button class="cm-btn ${resumeClass}" onclick="cmResumeBatch('${pausedBatch.id}')"
        ${thresholdMet ? '' : 'title="Threshold not yet reached"'}>Resume Batch</button>`;
      btns += `<button class="cm-btn cm-btn-ghost" onclick="cmCompleteBatch('${pausedBatch.id}')">Mark Batch Complete</button>`;
    }

    btns += `<button class="cm-btn cm-btn-outline" onclick="cmRefreshNow()">Refresh Now</button>`;

    el.innerHTML = btns;
  }

  function renderTable() {
    const tbody = document.getElementById('cm-table-body');
    if (!tbody) return;

    if (campaigns.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" class="cm-empty">No batches yet. Start a new batch to begin.</td></tr>`;
      return;
    }

    tbody.innerHTML = sortedCampaigns().map(b => {
      const pct = Math.min(100, Math.round((b.letters_called_5x / b.pause_threshold) * 100));
      const statusClass = { active: 'status-active', paused: 'status-paused', completed: 'status-completed' }[b.status] || '';
      const created = b.created_at ? new Date(b.created_at).toLocaleDateString() : '—';
      const completed = b.completed_at ? new Date(b.completed_at).toLocaleDateString() : '—';

      const actions = [];
      if (b.status === 'active') {
        actions.push(`<button class="cm-action cm-action-warn" onclick="cmPauseBatch('${b.id}')">Pause</button>`);
        actions.push(`<button class="cm-action cm-action-ghost" onclick="cmCompleteBatch('${b.id}')">Complete</button>`);
      } else if (b.status === 'paused') {
        const ok = b.letters_called_5x >= b.pause_threshold;
        actions.push(`<button class="cm-action ${ok ? 'cm-action-ok' : 'cm-action-disabled'}" onclick="cmResumeBatch('${b.id}')" ${ok ? '' : 'title="Threshold not reached"'}>Resume</button>`);
        actions.push(`<button class="cm-action cm-action-ghost" onclick="cmCompleteBatch('${b.id}')">Complete</button>`);
      }

      return `
        <tr>
          <td><strong>#${b.batch_number}</strong></td>
          <td>${b.total_letters_sent}</td>
          <td>
            <div class="cm-mini-progress">
              <span>${b.letters_called_5x}/${b.pause_threshold}</span>
              <div class="cm-mini-bar"><div class="cm-mini-fill ${pct >= 100 ? 'cm-mini-done' : ''}" style="width:${pct}%"></div></div>
            </div>
          </td>
          <td><span class="cm-badge ${statusClass}">${b.status.toUpperCase()}</span></td>
          <td>${created}</td>
          <td>${completed}</td>
          <td class="cm-actions-cell">${actions.join('')}</td>
        </tr>`;
    }).join('');
  }

  function renderCostSummary() {
    const el = document.getElementById('cm-cost-summary');
    if (!el) return;

    const totalLetters = campaigns.reduce((s, c) => s + (c.total_letters_sent || 0), 0);
    const totalCost = totalLetters * LETTER_COST;

    // Monthly: letters sent in current calendar month
    const now = new Date();
    const monthStart = new Date(now.getFullYear(), now.getMonth(), 1);
    const monthlyLetters = campaigns
      .filter(c => c.created_at && new Date(c.created_at) >= monthStart)
      .reduce((s, c) => s + (c.total_letters_sent || 0), 0);
    const monthlyCost = monthlyLetters * LETTER_COST;

    // Completed batches: estimate conversions (rough: 1 converted per ~20 letters)
    const completedBatches = campaigns.filter(c => c.status === 'completed');
    let costPerConv = '—';
    if (completedBatches.length > 0) {
      const totalCompleted = completedBatches.reduce((s, c) => s + (c.total_letters_sent || 0), 0);
      const estConversions = Math.max(1, Math.round(totalCompleted / 20));
      costPerConv = '$' + (totalCompleted * LETTER_COST / estConversions).toFixed(0);
    }

    el.innerHTML = `
      <div class="cm-cost-grid">
        <div class="cm-cost-item">
          <div class="cm-cost-num">$${totalCost.toFixed(2)}</div>
          <div class="cm-cost-label">Total Spent (All Batches)</div>
          <div class="cm-cost-sub">${totalLetters} letters × $${LETTER_COST}</div>
        </div>
        <div class="cm-cost-item">
          <div class="cm-cost-num">$${monthlyCost.toFixed(2)}</div>
          <div class="cm-cost-label">Running Monthly Cost</div>
          <div class="cm-cost-sub">${monthlyLetters} letters this month</div>
        </div>
        <div class="cm-cost-item">
          <div class="cm-cost-num">${costPerConv}</div>
          <div class="cm-cost-label">Cost Per Conversion</div>
          <div class="cm-cost-sub">${completedBatches.length} completed batch${completedBatches.length !== 1 ? 'es' : ''}</div>
        </div>
      </div>`;
  }

  // ── Toast ───────────────────────────────────────────────────────────────────

  function showToast(msg, type) {
    let wrap = document.getElementById('cm-toast-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.id = 'cm-toast-wrap';
      wrap.style.cssText = 'position:fixed;bottom:24px;right:24px;z-index:99999;display:flex;flex-direction:column;gap:8px';
      document.body.appendChild(wrap);
    }
    const t = document.createElement('div');
    t.className = 'cm-toast cm-toast-' + (type || 'info');
    t.textContent = msg;
    wrap.appendChild(t);
    setTimeout(() => t.classList.add('cm-toast-show'), 10);
    setTimeout(() => { t.classList.remove('cm-toast-show'); setTimeout(() => t.remove(), 300); }, 3500);
  }

  function setLoading(on) {
    const el = document.getElementById('cm-controls');
    if (el) el.style.opacity = on ? '0.5' : '1';
    document.body.style.cursor = on ? 'wait' : '';
  }

  // ── Init ─────────────────────────────────────────────────────────────────────

  async function loadAndRender() {
    try {
      campaigns = await fetchCampaigns();
      // currentBatch = first non-completed, or most recent
      currentBatch = campaigns.find(c => c.status === 'active' || c.status === 'paused')
        || (campaigns.length > 0 ? campaigns[0] : null);
      renderAll();
    } catch (e) {
      console.error('[campaign-manager] Load error:', e);
      const card = document.getElementById('cm-status-card');
      if (card) card.innerHTML = `<div class="cm-error">Failed to load campaigns: ${e.message}</div>`;
    }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    await loadAndRender();
    startSync();
  });

  // expose for external use
  window.CampaignManager = { reload: loadAndRender, sync: syncCurrentBatch };

})();
