/**
 * Letter Approval Queue Component — Master CRM
 *
 * Intercepts generated letters before they go to Lob.
 * Renders a pending-letter banner at the top of any company page.
 *
 * Usage:
 *   <link rel="stylesheet" href="/letter-approvals.css">
 *   <script src="/letter-approval-component.js"></script>
 *
 *   Then in page JS (after DOM ready):
 *     LetterApprovalQueue.init({ companyId: 'uuid-here', mountSelector: '#approval-mount' });
 *
 *   Or with auto-detect:
 *     LetterApprovalQueue.autoInit();   // reads data-company-id from <body>
 */
(function(global) {
  'use strict';

  const SUPABASE_URL = 'https://dwrnfpjcvydhmhnvyzov.supabase.co';
  const SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR3cm5mcGpjdnlkaG1obnZ5em92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3NTcyOTAsImV4cCI6MjA5MDMzMzI5MH0.z0Gu1TWdGPcdptB5W7efnYMmxBbvD353ExG99ftQivY';

  const BASE = SUPABASE_URL + '/rest/v1/letter_approvals';
  const HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': 'Bearer ' + SUPABASE_KEY,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation'
  };

  // ── Supabase helpers ────────────────────────────────────────────────────────

  async function sbFetch(url, options) {
    const res = await fetch(url, Object.assign({ headers: HEADERS }, options));
    if (!res.ok) {
      const text = await res.text();
      throw new Error('Supabase error ' + res.status + ': ' + text);
    }
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json') && res.status !== 204) return res.json();
    return null;
  }

  async function getPendingLetters(companyId) {
    const url = BASE
      + '?company_id=eq.' + encodeURIComponent(companyId)
      + '&status=eq.pending'
      + '&order=created_at.desc'
      + '&select=*';
    return sbFetch(url);
  }

  async function approveRecord(approvalId, approvedBy) {
    const url = BASE + '?id=eq.' + encodeURIComponent(approvalId);
    return sbFetch(url, {
      method: 'PATCH',
      body: JSON.stringify({
        status: 'approved',
        approved_by: approvedBy || null,
        approved_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      })
    });
  }

  async function rejectRecord(approvalId, reason) {
    const url = BASE + '?id=eq.' + encodeURIComponent(approvalId);
    return sbFetch(url, {
      method: 'PATCH',
      body: JSON.stringify({
        status: 'rejected',
        rejected_reason: reason || '',
        updated_at: new Date().toISOString()
      })
    });
  }

  async function updateLetterText(approvalId, newText) {
    const url = BASE + '?id=eq.' + encodeURIComponent(approvalId);
    return sbFetch(url, {
      method: 'PATCH',
      body: JSON.stringify({
        letter_text: newText,
        updated_at: new Date().toISOString()
      })
    });
  }

  async function triggerLobSend(approvalId) {
    const res = await fetch('/api/letters/send-to-lob', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approval_id: approvalId })
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error('Lob send failed ' + res.status + ': ' + text);
    }
    return res.json();
  }

  // ── Utilities ───────────────────────────────────────────────────────────────

  function getCurrentUser() {
    return localStorage.getItem('crm_user') || null;
  }

  function formatScore(score) {
    if (score == null) return null;
    const pct = Math.round(parseFloat(score) * 100);
    return pct + '%';
  }

  function timeAgo(iso) {
    if (!iso) return '';
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
    if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
    return Math.floor(diff / 86400) + 'd ago';
  }

  function escapeHtml(s) {
    if (!s) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── DOM builders ────────────────────────────────────────────────────────────

  function buildCard(approval) {
    const card = document.createElement('div');
    card.className = 'approval-card status-pending';
    card.dataset.approvalId = approval.id;

    const scoreHtml = approval.personalization_score != null
      ? '<span class="approval-score-badge">Score: ' + formatScore(approval.personalization_score) + '</span>'
      : '';

    card.innerHTML = `
      <div class="approval-header">
        <div class="approval-header-left">
          <span class="approval-status-icon">✉</span>
          <span>Letter Pending Approval</span>
          <span class="approval-meta">${timeAgo(approval.created_at)}</span>
        </div>
        ${scoreHtml}
      </div>
      <div class="approval-body">
        <div class="letter-preview" data-preview>${escapeHtml(approval.letter_text)}</div>
        <button class="preview-toggle" data-toggle-preview>Show full letter</button>
        <div class="rejection-reason-wrap" data-reject-wrap>
          <label class="rejection-reason-label">Reason for rejection</label>
          <textarea class="rejection-reason-input" data-reject-input placeholder="Explain why this letter needs to be regenerated..."></textarea>
        </div>
        <textarea class="approval-notes" data-notes-input placeholder="Optional notes (saved with record)..."></textarea>
        <div class="approval-actions">
          <button class="btn-approve" data-btn-approve>&#10003; Approve &amp; Send</button>
          <button class="btn-edit" data-btn-edit>&#9999; Edit</button>
          <button class="btn-reject" data-btn-reject>&#10005; Reject with reason</button>
        </div>
      </div>
    `;

    // Wire up preview expand/collapse
    const preview = card.querySelector('[data-preview]');
    const toggleBtn = card.querySelector('[data-toggle-preview]');
    toggleBtn.addEventListener('click', function() {
      const expanded = preview.classList.toggle('expanded');
      toggleBtn.textContent = expanded ? 'Collapse letter' : 'Show full letter';
    });

    // Wire up reject reason toggle
    const rejectBtn = card.querySelector('[data-btn-reject]');
    const rejectWrap = card.querySelector('[data-reject-wrap]');
    const rejectInput = card.querySelector('[data-reject-input]');
    rejectBtn.addEventListener('click', function() {
      const showing = rejectWrap.classList.toggle('visible');
      if (showing) {
        rejectBtn.textContent = '✕ Confirm rejection';
        rejectBtn.classList.add('btn-confirm-reject');
        rejectInput.focus();
        // Second click on same button = confirm
        rejectBtn.dataset.confirmMode = 'true';
      } else {
        rejectBtn.textContent = '✕ Reject with reason';
        rejectBtn.classList.remove('btn-confirm-reject');
        delete rejectBtn.dataset.confirmMode;
      }
    });

    // Approve handler
    const approveBtn = card.querySelector('[data-btn-approve]');
    approveBtn.addEventListener('click', async function() {
      if (approveBtn.disabled) return;
      setButtonsDisabled(card, true);
      approveBtn.innerHTML = '<span class="approval-spinner"></span> Sending...';
      try {
        const notesInput = card.querySelector('[data-notes-input]');
        if (notesInput && notesInput.value.trim()) {
          await sbFetch(BASE + '?id=eq.' + encodeURIComponent(approval.id), {
            method: 'PATCH',
            body: JSON.stringify({ notes: notesInput.value.trim(), updated_at: new Date().toISOString() })
          });
        }
        await approveRecord(approval.id, getCurrentUser());
        await triggerLobSend(approval.id);
        markCardApproved(card);
        updatePendingCountBadge(-1);
      } catch (err) {
        approveBtn.innerHTML = '&#10003; Approve &amp; Send';
        setButtonsDisabled(card, false);
        showCardError(card, 'Failed to send: ' + err.message);
      }
    });

    // Reject confirm (re-attached on dynamic state)
    card.addEventListener('click', async function(e) {
      const btn = e.target.closest('[data-btn-reject]');
      if (!btn || !btn.dataset.confirmMode) return;
      if (btn.disabled) return;
      const reason = rejectInput.value.trim();
      if (!reason) {
        rejectInput.style.borderColor = '#dc2626';
        rejectInput.placeholder = 'Please enter a reason before confirming.';
        rejectInput.focus();
        return;
      }
      setButtonsDisabled(card, true);
      btn.textContent = 'Rejecting...';
      try {
        await rejectRecord(approval.id, reason);
        markCardRejected(card, reason);
        updatePendingCountBadge(-1);
      } catch (err) {
        btn.textContent = '✕ Confirm rejection';
        setButtonsDisabled(card, false);
        showCardError(card, 'Failed to reject: ' + err.message);
      }
    });

    // Edit handler — opens inline edit modal
    const editBtn = card.querySelector('[data-btn-edit]');
    editBtn.addEventListener('click', function() {
      openEditModal(approval, card);
    });

    return card;
  }

  function setButtonsDisabled(card, disabled) {
    card.querySelectorAll('button').forEach(function(b) { b.disabled = disabled; });
  }

  function markCardApproved(card) {
    card.className = 'approval-card status-approved';
    const header = card.querySelector('.approval-header');
    header.querySelector('.approval-status-icon').textContent = '✓';
    header.querySelector('span:nth-child(2)').textContent = 'Letter Approved — Sending to Lob';
    const body = card.querySelector('.approval-body');
    body.innerHTML = '<div class="approved-confirmation">&#10003; Approved and queued for mailing.</div>';
  }

  function markCardRejected(card, reason) {
    card.className = 'approval-card status-rejected';
    const header = card.querySelector('.approval-header');
    header.querySelector('.approval-status-icon').textContent = '✕';
    header.querySelector('span:nth-child(2)').textContent = 'Letter Rejected';
    const body = card.querySelector('.approval-body');
    body.innerHTML = `
      <div class="rejection-reason-display">
        <strong>Rejection reason</strong>
        ${escapeHtml(reason)}
      </div>
      <p style="font-size:13px;color:#6b7280;margin:0;">Rep can regenerate a new letter from the letter engine.</p>
    `;
  }

  function showCardError(card, message) {
    let err = card.querySelector('.approval-error');
    if (!err) {
      err = document.createElement('p');
      err.className = 'approval-error';
      err.style.cssText = 'font-size:12px;color:#ef4444;margin:8px 0 0;';
      card.querySelector('.approval-body').appendChild(err);
    }
    err.textContent = message;
  }

  // ── Edit modal ──────────────────────────────────────────────────────────────

  function openEditModal(approval, card) {
    const overlay = document.createElement('div');
    overlay.className = 'letter-edit-modal-overlay';
    overlay.innerHTML = `
      <div class="letter-edit-modal">
        <div class="letter-edit-modal-header">
          <h3>&#9999; Edit Letter</h3>
          <button class="letter-edit-modal-close" data-close>&times;</button>
        </div>
        <div class="letter-edit-modal-body">
          <textarea class="letter-edit-textarea" data-edit-text>${escapeHtml(approval.letter_text)}</textarea>
        </div>
        <div class="letter-edit-modal-footer">
          <button class="btn-cancel-edit" data-close>Cancel</button>
          <button class="btn-save-edit" data-save>Save changes</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);

    overlay.querySelectorAll('[data-close]').forEach(function(btn) {
      btn.addEventListener('click', function() { overlay.remove(); });
    });

    overlay.addEventListener('click', function(e) {
      if (e.target === overlay) overlay.remove();
    });

    const saveBtn = overlay.querySelector('[data-save]');
    const editTextarea = overlay.querySelector('[data-edit-text]');

    saveBtn.addEventListener('click', async function() {
      const newText = editTextarea.value.trim();
      if (!newText) return;
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';
      try {
        await updateLetterText(approval.id, newText);
        approval.letter_text = newText;
        // Update preview in card
        const preview = card.querySelector('[data-preview]');
        if (preview) preview.textContent = newText;
        overlay.remove();
      } catch (err) {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save changes';
        const body = overlay.querySelector('.letter-edit-modal-body');
        let errEl = body.querySelector('.edit-error');
        if (!errEl) {
          errEl = document.createElement('p');
          errEl.className = 'edit-error';
          errEl.style.cssText = 'font-size:12px;color:#ef4444;margin:8px 0 0;';
          body.appendChild(errEl);
        }
        errEl.textContent = 'Save failed: ' + err.message;
      }
    });
  }

  // ── Pending count badge in header ───────────────────────────────────────────

  let _pendingCount = 0;

  function updatePendingCountBadge(delta) {
    _pendingCount = Math.max(0, _pendingCount + delta);
    document.querySelectorAll('.letter-pending-count').forEach(function(el) {
      el.textContent = _pendingCount;
      el.classList.toggle('hidden', _pendingCount === 0);
    });
  }

  function injectHeaderBadges(count) {
    _pendingCount = count;
    // Look for existing badge mounts first
    document.querySelectorAll('[data-letter-badge]').forEach(function(el) {
      el.textContent = count;
      el.classList.toggle('hidden', count === 0);
    });

    // Auto-inject next to h1 if none exist
    if (!document.querySelector('[data-letter-badge]') && count > 0) {
      const h1 = document.querySelector('h1');
      if (h1) {
        const badge = document.createElement('span');
        badge.className = 'letter-pending-count';
        badge.dataset.letterBadge = '';
        badge.textContent = count;
        if (count === 0) badge.classList.add('hidden');
        h1.appendChild(badge);
      }
    }
  }

  // ── Main init ───────────────────────────────────────────────────────────────

  async function init(options) {
    const companyId = options && options.companyId;
    if (!companyId) {
      console.warn('[LetterApprovalQueue] No companyId provided.');
      return;
    }

    // Find or create mount point
    let mount = options.mountSelector
      ? document.querySelector(options.mountSelector)
      : document.getElementById('letter-approval-queue');

    if (!mount) {
      mount = document.createElement('div');
      mount.id = 'letter-approval-queue';
      mount.className = 'letter-approval-queue';
      // Insert at top of <main> or <body>
      const main = document.querySelector('main') || document.body;
      main.insertBefore(mount, main.firstChild);
    }

    mount.className = 'letter-approval-queue';

    // Show loading state
    mount.innerHTML = '<p style="font-size:13px;color:#9ca3af;">Checking for pending letters...</p>';

    let pending;
    try {
      pending = await getPendingLetters(companyId);
    } catch (err) {
      mount.innerHTML = '<p style="font-size:13px;color:#ef4444;">Could not load approvals: ' + escapeHtml(err.message) + '</p>';
      return;
    }

    mount.innerHTML = '';

    if (!pending || pending.length === 0) {
      // Nothing pending — render nothing (banner stays invisible)
      return;
    }

    injectHeaderBadges(pending.length);

    pending.forEach(function(approval) {
      mount.appendChild(buildCard(approval));
    });
  }

  // Auto-init if body carries data-company-id attribute
  function autoInit() {
    const companyId = document.body.dataset.companyId
      || document.querySelector('[data-company-id]') && document.querySelector('[data-company-id]').dataset.companyId;
    if (companyId) init({ companyId: companyId });
  }

  // ── Public API ──────────────────────────────────────────────────────────────

  global.LetterApprovalQueue = {
    init: init,
    autoInit: autoInit
  };

  // Kick off on DOMContentLoaded if not already ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

})(window);
