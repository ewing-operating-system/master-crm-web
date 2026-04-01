/**
 * POST /api/letters/approve
 *
 * Sets a letter_approvals record to status='approved' WITHOUT triggering
 * Lob send. The actual mailing happens later via /api/letters/batch-send.
 *
 * Request body:
 *   { letter_id: string, action: "approved"|"rejected", approved_by?: string, rejected_reason?: string }
 *
 * Response (200):
 *   { success: true, status: "approved"|"rejected", approval_id: string }
 *
 * Idempotent: if the letter is already in the requested status, returns 200.
 *
 * Env vars required:
 *   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

'use strict';

// ---------------------------------------------------------------------------
// Supabase helpers (service role — bypasses RLS)
// ---------------------------------------------------------------------------

function supabaseHeaders() {
  return {
    'apikey':        process.env.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
    'Content-Type':  'application/json',
    'Prefer':        'return=representation',
  };
}

async function getApproval(letterId) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/letter_approvals`
    + `?id=eq.${encodeURIComponent(letterId)}`
    + '&select=id,status'
    + '&limit=1';

  const res = await fetch(url, { headers: supabaseHeaders() });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase fetch failed (${res.status}): ${body}`);
  }
  const rows = await res.json();
  return rows[0] || null;
}

async function patchApproval(letterId, updates) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/letter_approvals`
    + `?id=eq.${encodeURIComponent(letterId)}`;

  const res = await fetch(url, {
    method:  'PATCH',
    headers: supabaseHeaders(),
    body:    JSON.stringify(updates),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase patch failed (${res.status}): ${body}`);
  }
  const rows = await res.json();
  return rows[0] || null;
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

module.exports = async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST')   return res.status(405).json({ error: 'Method not allowed' });

  let body;
  try {
    body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  } catch {
    return res.status(400).json({ error: 'Invalid JSON body' });
  }

  const { letter_id, action, approved_by, rejected_reason } = body || {};

  if (!letter_id) {
    return res.status(400).json({ error: 'letter_id is required' });
  }

  const validActions = ['approved', 'rejected'];
  const resolvedAction = validActions.includes(action) ? action : 'approved';

  // 1. Verify the record exists
  let existing;
  try {
    existing = await getApproval(letter_id);
  } catch (err) {
    return res.status(502).json({ error: 'Database error: ' + err.message });
  }

  if (!existing) {
    return res.status(404).json({ error: `No letter_approvals record found for id: ${letter_id}` });
  }

  // 2. Idempotent — if already in requested status, return success
  if (existing.status === resolvedAction) {
    return res.status(200).json({
      success: true,
      status: resolvedAction,
      approval_id: letter_id,
      note: 'Already in requested status',
    });
  }

  // 3. Block if already sent
  if (existing.status === 'sent') {
    return res.status(409).json({ error: 'Letter already sent — cannot change status' });
  }

  // 4. Build the update
  const now = new Date().toISOString();
  const updates = {
    status:     resolvedAction,
    updated_at: now,
  };

  if (resolvedAction === 'approved') {
    updates.approved_by = approved_by || null;
    updates.approved_at = now;
  } else if (resolvedAction === 'rejected') {
    updates.rejected_reason = rejected_reason || '';
  }

  // 5. Patch
  try {
    const updated = await patchApproval(letter_id, updates);
    return res.status(200).json({
      success:     true,
      status:      resolvedAction,
      approval_id: letter_id,
      record:      updated,
    });
  } catch (err) {
    return res.status(502).json({ error: 'Failed to update: ' + err.message });
  }
};
