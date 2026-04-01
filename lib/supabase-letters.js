/**
 * supabase-letters.js — Letter Approval Queue client methods
 * Master CRM — Next Chapter M&A Advisory
 *
 * Wraps the letter_approvals table in clean async functions.
 * Designed for use in both browser and Node (via fetch API / node-fetch).
 *
 * Usage (ESM):
 *   import { createApprovalRecord, getPendingLetters, approveAndSend, rejectLetter, getApprovalHistory } from '../lib/supabase-letters.js';
 *
 * Usage (CommonJS):
 *   const { createApprovalRecord, ... } = require('./supabase-letters');
 */

// Credentials: all keys come from env vars. See .env.example for names.
// Vercel injects these at runtime. Local dev: copy .env.example to .env

const SUPABASE_URL = typeof window !== 'undefined' ? window.__SUPABASE_URL : (typeof process !== 'undefined' ? process.env.SUPABASE_URL : '');
const SUPABASE_KEY = typeof window !== 'undefined' ? window.__SUPABASE_ANON_KEY : (typeof process !== 'undefined' ? process.env.SUPABASE_ANON_KEY : '');

const BASE_URL = SUPABASE_URL + '/rest/v1/letter_approvals';

const DEFAULT_HEADERS = {
  'apikey': SUPABASE_KEY,
  'Authorization': 'Bearer ' + SUPABASE_KEY,
  'Content-Type': 'application/json',
  'Prefer': 'return=representation'
};

// ── Internal helper ─────────────────────────────────────────────────────────

async function request(url, options = {}) {
  const res = await fetch(url, {
    headers: DEFAULT_HEADERS,
    ...options
  });

  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase ${res.status}: ${body}`);
  }

  if (res.status === 204) return null;
  const ct = res.headers.get('content-type') || '';
  if (ct.includes('application/json')) return res.json();
  return null;
}

// ── Public methods ───────────────────────────────────────────────────────────

/**
 * createApprovalRecord
 * Called by the Letter Template Engine immediately after rendering a letter.
 * Saves to letter_approvals with status='pending'.
 *
 * @param {string} company_id           — UUID from companies table
 * @param {string} letter_text          — Full rendered letter body
 * @param {number|null} personalization_score — 0.00–1.00 quality score
 * @param {string|null} created_by      — UUID of rep who triggered generation (optional)
 * @returns {Promise<object>}           — The created approval record
 */
async function createApprovalRecord(company_id, letter_text, personalization_score = null, created_by = null) {
  if (!company_id) throw new Error('company_id is required');
  if (!letter_text) throw new Error('letter_text is required');

  const payload = {
    company_id,
    letter_text,
    status: 'pending',
    ...(personalization_score !== null && { personalization_score }),
    ...(created_by !== null && { created_by })
  };

  const records = await request(BASE_URL, {
    method: 'POST',
    body: JSON.stringify(payload)
  });

  // Supabase returns an array with Prefer: return=representation
  return Array.isArray(records) ? records[0] : records;
}

/**
 * getPendingLetters
 * Fetch all letters awaiting approval for a given company.
 * Used by company pages on load to decide whether to show the approval banner.
 *
 * @param {string} company_id
 * @returns {Promise<object[]>}  — Array of approval records (may be empty)
 */
async function getPendingLetters(company_id) {
  if (!company_id) throw new Error('company_id is required');

  const url = BASE_URL
    + '?company_id=eq.' + encodeURIComponent(company_id)
    + '&status=eq.pending'
    + '&order=created_at.desc'
    + '&select=*';

  return request(url);
}

/**
 * approveAndSend
 * Mark an approval record as approved and trigger the Lob mailing.
 * Calls the internal /api/letters/send-to-lob route.
 *
 * @param {string} approval_id   — UUID of the letter_approvals row
 * @param {string|null} approved_by — Rep UUID (optional, stored for audit trail)
 * @returns {Promise<object>}    — { approval, lob } combined result
 */
async function approveAndSend(approval_id, approved_by = null) {
  if (!approval_id) throw new Error('approval_id is required');

  // 1. Update Supabase record
  const updateUrl = BASE_URL + '?id=eq.' + encodeURIComponent(approval_id);
  const patch = {
    status: 'approved',
    approved_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    ...(approved_by !== null && { approved_by })
  };

  const updated = await request(updateUrl, {
    method: 'PATCH',
    body: JSON.stringify(patch)
  });

  const approval = Array.isArray(updated) ? updated[0] : updated;

  // 2. Trigger Lob send
  const lobRes = await fetch('/api/letters/send-to-lob', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approval_id })
  });

  if (!lobRes.ok) {
    const lobBody = await lobRes.text();
    throw new Error(`Lob send failed ${lobRes.status}: ${lobBody}`);
  }

  const lob = await lobRes.json();

  return { approval, lob };
}

/**
 * rejectLetter
 * Mark a letter as rejected and store the reason.
 * The rep can then regenerate from the Letter Template Engine.
 *
 * @param {string} approval_id
 * @param {string} reason       — Human-readable rejection reason (required)
 * @returns {Promise<object>}   — Updated approval record
 */
async function rejectLetter(approval_id, reason) {
  if (!approval_id) throw new Error('approval_id is required');
  if (!reason || !reason.trim()) throw new Error('reason is required when rejecting a letter');

  const url = BASE_URL + '?id=eq.' + encodeURIComponent(approval_id);
  const patch = {
    status: 'rejected',
    rejected_reason: reason.trim(),
    updated_at: new Date().toISOString()
  };

  const updated = await request(url, {
    method: 'PATCH',
    body: JSON.stringify(patch)
  });

  return Array.isArray(updated) ? updated[0] : updated;
}

/**
 * getApprovalHistory
 * Returns all approval records for a company, all statuses, newest first.
 * Useful for the "Letter History" section of a company page.
 *
 * @param {string} company_id
 * @param {object} [opts]
 * @param {number} [opts.limit=50]
 * @param {string} [opts.status]  — Filter by status ('pending'|'approved'|'rejected')
 * @returns {Promise<object[]>}
 */
async function getApprovalHistory(company_id, opts = {}) {
  if (!company_id) throw new Error('company_id is required');

  const limit = opts.limit || 50;
  let url = BASE_URL
    + '?company_id=eq.' + encodeURIComponent(company_id)
    + '&order=created_at.desc'
    + '&limit=' + limit
    + '&select=*';

  if (opts.status) {
    url += '&status=eq.' + encodeURIComponent(opts.status);
  }

  return request(url);
}

/**
 * updateNotes
 * Attach optional rep notes to an approval record without changing status.
 *
 * @param {string} approval_id
 * @param {string} notes
 * @returns {Promise<object>}
 */
async function updateNotes(approval_id, notes) {
  if (!approval_id) throw new Error('approval_id is required');

  const url = BASE_URL + '?id=eq.' + encodeURIComponent(approval_id);
  const updated = await request(url, {
    method: 'PATCH',
    body: JSON.stringify({ notes, updated_at: new Date().toISOString() })
  });

  return Array.isArray(updated) ? updated[0] : updated;
}

/**
 * updateLetterText
 * Replace the letter body for a pending approval (in-place edit before approval).
 *
 * @param {string} approval_id
 * @param {string} letter_text
 * @returns {Promise<object>}
 */
async function updateLetterText(approval_id, letter_text) {
  if (!approval_id) throw new Error('approval_id is required');
  if (!letter_text) throw new Error('letter_text is required');

  const url = BASE_URL + '?id=eq.' + encodeURIComponent(approval_id);
  const updated = await request(url, {
    method: 'PATCH',
    body: JSON.stringify({ letter_text, updated_at: new Date().toISOString() })
  });

  return Array.isArray(updated) ? updated[0] : updated;
}

// ── Exports (ESM — loaded as <script type="module"> in browser) ─────────────

export {
  createApprovalRecord,
  getPendingLetters,
  approveAndSend,
  rejectLetter,
  getApprovalHistory,
  updateNotes,
  updateLetterText
};

export default {
  createApprovalRecord,
  getPendingLetters,
  approveAndSend,
  rejectLetter,
  getApprovalHistory,
  updateNotes,
  updateLetterText
};
