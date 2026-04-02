/**
 * POST /api/meetings/approve-learning
 *
 * Approves or rejects a meeting learning extraction.
 * When approved, optionally writes the learning value to its target table/column.
 *
 * Request body:
 *   { learning_id: string, approved: boolean }
 *
 * Response (200):
 *   { success: true, learning_id: string, approved: boolean }
 *
 * Credentials: all keys come from env vars. See .env.example for names.
 * Vercel injects these at runtime. Local dev: copy .env.example to .env
 *
 * Env vars required:
 *   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

'use strict';

function supabaseHeaders() {
  return {
    'apikey':        process.env.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
    'Content-Type':  'application/json',
    'Prefer':        'return=representation',
  };
}

async function getLearning(learningId) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/meeting_learnings`
    + `?id=eq.${encodeURIComponent(learningId)}`
    + '&select=*'
    + '&limit=1';

  const res = await fetch(url, { headers: supabaseHeaders() });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase fetch failed (${res.status}): ${body}`);
  }
  const rows = await res.json();
  return rows[0] || null;
}

async function patchLearning(learningId, updates) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/meeting_learnings`
    + `?id=eq.${encodeURIComponent(learningId)}`;

  const res = await fetch(url, {
    method:  'PATCH',
    headers: supabaseHeaders(),
    body:    JSON.stringify(updates),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase patch failed (${res.status}): ${body}`);
  }
  return await res.json();
}

async function writeToTarget(learning) {
  const { target_table, target_column, target_value, entity } = learning;

  // Only write if all target fields are specified
  if (!target_table || !target_column || !target_value || !entity) {
    return { written: false, reason: 'Missing target fields' };
  }

  // Safety: only allow writing to known tables
  const allowedTables = ['dossier_final', 'buyer_contacts', 'targets', 'contacts'];
  if (!allowedTables.includes(target_table)) {
    return { written: false, reason: `Table ${target_table} not in allowlist` };
  }

  // Attempt to update the matching row
  const url = `${process.env.SUPABASE_URL}/rest/v1/${target_table}`
    + `?entity=eq.${encodeURIComponent(entity)}&limit=1`;

  const res = await fetch(url, {
    method:  'PATCH',
    headers: supabaseHeaders(),
    body:    JSON.stringify({ [target_column]: target_value }),
  });

  if (!res.ok) {
    const body = await res.text();
    return { written: false, reason: `PATCH failed (${res.status}): ${body}` };
  }

  return { written: true };
}

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

  const { learning_id, approved } = body || {};

  if (!learning_id) {
    return res.status(400).json({ error: 'learning_id is required' });
  }
  if (typeof approved !== 'boolean') {
    return res.status(400).json({ error: 'approved must be a boolean' });
  }

  // 1. Verify the learning exists
  let learning;
  try {
    learning = await getLearning(learning_id);
  } catch (err) {
    return res.status(502).json({ error: 'Database error: ' + err.message });
  }

  if (!learning) {
    return res.status(404).json({ error: `No meeting_learnings record found for id: ${learning_id}` });
  }

  // 2. Update the learning
  const now = new Date().toISOString();
  try {
    await patchLearning(learning_id, {
      approved: approved,
      approved_at: now,
    });
  } catch (err) {
    return res.status(502).json({ error: 'Failed to update: ' + err.message });
  }

  // 3. If approved, write to target table
  let writeResult = { written: false, reason: 'Not approved' };
  if (approved) {
    try {
      writeResult = await writeToTarget(learning);
    } catch (err) {
      writeResult = { written: false, reason: err.message };
    }
  }

  return res.status(200).json({
    success: true,
    learning_id: learning_id,
    approved: approved,
    target_write: writeResult,
  });
};
