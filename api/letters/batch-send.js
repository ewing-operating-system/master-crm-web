/**
 * POST /api/letters/batch-send
 *
 * Picks up all letter_approvals records with status='approved' and sends
 * them via Lob. Letters without a complete address are marked 'address_missing'.
 *
 * Request body:
 *   {
 *     limit?:      number,   // max letters to process (default 10, cap 15)
 *     dry_run?:    boolean,  // if true, log what would send but don't call Lob
 *     auth_token:  string    // must match BATCH_SEND_SECRET env var
 *   }
 *
 * Response (200):
 *   {
 *     sent:     number,
 *     skipped:  number,
 *     failed:   number,
 *     dry_run:  boolean,
 *     details:  Array<{ id, company_id, status, lob_letter_id?, error? }>
 *   }
 *
 * Security: requires auth_token === process.env.BATCH_SEND_SECRET
 *
 * Env vars required:
 *   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BATCH_SEND_SECRET,
 *   LOB_API_KEY, LOB_FROM_NAME, LOB_FROM_ADDRESS, LOB_FROM_CITY,
 *   LOB_FROM_STATE, LOB_FROM_ZIP
 */

'use strict';

// Credentials: all keys come from env vars. See .env.example for names.
// Vercel injects these at runtime. Local dev: copy .env.example to .env

const { sendPhysicalLetter } = require('../../lib/lob-integration');

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_BATCH_SIZE = 15;  // Vercel 30s timeout ÷ ~2s per Lob call
const DEFAULT_BATCH_SIZE = 10;
const LOB_COST_PER_LETTER = 1.75;

// ---------------------------------------------------------------------------
// Supabase helpers
// ---------------------------------------------------------------------------

function supabaseHeaders() {
  return {
    'apikey':        process.env.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
    'Content-Type':  'application/json',
    'Prefer':        'return=representation',
  };
}

async function fetchApprovedLetters(limit) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/letter_approvals`
    + '?status=eq.approved'
    + '&order=approved_at.asc'
    + `&limit=${limit}`
    + '&select=*';

  const res = await fetch(url, { headers: supabaseHeaders() });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase fetch approved letters failed (${res.status}): ${body}`);
  }
  return res.json();
}

async function fetchCompanyAddress(companyId) {
  if (!companyId) return null;

  const url = `${process.env.SUPABASE_URL}/rest/v1/companies`
    + `?id=eq.${encodeURIComponent(companyId)}`
    + '&select=company_name,address,city,state,zip'
    + '&limit=1';

  const res = await fetch(url, { headers: supabaseHeaders() });
  if (!res.ok) return null;
  const rows = await res.json();
  return rows[0] || null;
}

async function patchApproval(approvalId, updates) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/letter_approvals`
    + `?id=eq.${encodeURIComponent(approvalId)}`;

  await fetch(url, {
    method:  'PATCH',
    headers: supabaseHeaders(),
    body:    JSON.stringify(updates),
  });
}

async function logCost(letterId, lobLetterId, cost) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/cost_ledger`;

  await fetch(url, {
    method:  'POST',
    headers: supabaseHeaders(),
    body: JSON.stringify({
      entity: 'next_chapter',
      service: 'lob',
      operation: 'letter_send',
      cost: cost,
      target_id: letterId,
      metadata: JSON.stringify({ lob_id: lobLetterId, source: 'batch-send' }),
      created_at: new Date().toISOString(),
    }),
  }).catch(() => {
    // Non-fatal — cost logging failure should not block sending
  });
}

// ---------------------------------------------------------------------------
// Address resolution — same logic as send-to-lob.js
// ---------------------------------------------------------------------------

async function resolveAddress(approval) {
  let name   = approval.recipient_name;
  let line1  = approval.recipient_address_line1;
  let city   = approval.recipient_city;
  let state  = approval.recipient_state;
  let zip    = approval.recipient_zip;

  // If address is not on the approval record, fall back to companies table
  if (!line1 && approval.company_id) {
    const company = await fetchCompanyAddress(approval.company_id);
    if (company) {
      name  = name  || company.company_name;
      line1 = line1 || company.address;
      city  = city  || company.city;
      state = state || company.state;
      zip   = zip   || company.zip;
    }
  }

  if (!line1 || !city || !state || !zip) {
    return null;  // incomplete address
  }

  return {
    recipient_name:          name || 'Business Owner',
    recipient_address_line1: line1,
    recipient_city:          city,
    recipient_state:         state,
    recipient_zip:           zip,
  };
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

module.exports = async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'POST')   return res.status(405).json({ error: 'Method not allowed' });

  // Parse body
  let body;
  try {
    body = typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  } catch {
    return res.status(400).json({ error: 'Invalid JSON body' });
  }

  const { auth_token, dry_run, limit } = body || {};

  // Kill switch — letter sending is OFF unless explicitly enabled
  if (process.env.LETTER_SENDING_ENABLED !== 'true') {
    return res.status(403).json({
      error: 'Letter sending is disabled. Set LETTER_SENDING_ENABLED=true in Vercel env vars to enable.',
    });
  }

  // Auth check
  const secret = process.env.BATCH_SEND_SECRET;
  if (!secret) {
    return res.status(503).json({ error: 'BATCH_SEND_SECRET not configured on server' });
  }
  if (auth_token !== secret) {
    return res.status(401).json({ error: 'Invalid auth_token' });
  }

  // Resolve batch size
  const batchSize = Math.min(
    Math.max(1, parseInt(limit, 10) || DEFAULT_BATCH_SIZE),
    MAX_BATCH_SIZE
  );
  const isDryRun = !!dry_run;

  // Fetch approved letters
  let letters;
  try {
    letters = await fetchApprovedLetters(batchSize);
  } catch (err) {
    return res.status(502).json({ error: 'Failed to fetch approved letters: ' + err.message });
  }

  if (!letters || letters.length === 0) {
    return res.status(200).json({
      sent: 0, skipped: 0, failed: 0,
      dry_run: isDryRun,
      details: [],
      message: 'No approved letters in queue',
    });
  }

  // Process each letter
  const results = [];
  let sentCount = 0;
  let skippedCount = 0;
  let failedCount = 0;

  for (const letter of letters) {
    const detail = { id: letter.id, company_id: letter.company_id };

    // 1. Resolve address
    const address = await resolveAddress(letter);
    if (!address) {
      // Mark as address_missing so it doesn't get picked up again
      await patchApproval(letter.id, {
        status:     'address_missing',
        updated_at: new Date().toISOString(),
      });
      detail.status = 'address_missing';
      detail.error = 'Incomplete mailing address';
      skippedCount++;
      results.push(detail);
      continue;
    }

    // 2. Dry run — log but don't send
    if (isDryRun) {
      detail.status = 'would_send';
      detail.address = address;
      sentCount++;
      results.push(detail);
      continue;
    }

    // 3. Send via Lob
    try {
      const lobResult = await sendPhysicalLetter({
        letter_id:              letter.id,
        recipient_name:         address.recipient_name,
        recipient_address_line1: address.recipient_address_line1,
        recipient_city:         address.recipient_city,
        recipient_state:        address.recipient_state,
        recipient_zip:          address.recipient_zip,
        letter_html:            letter.letter_text,
      });

      // 4. Update approval record
      await patchApproval(letter.id, {
        status:        'sent',
        lob_letter_id: lobResult.lob_letter_id,
        lob_status:    lobResult.lob_status,
        tracking_url:  lobResult.tracking_url,
        sent_at:       new Date().toISOString(),
        updated_at:    new Date().toISOString(),
      });

      // 5. Log cost
      await logCost(letter.id, lobResult.lob_letter_id, lobResult.cost_incurred || LOB_COST_PER_LETTER);

      detail.status = 'sent';
      detail.lob_letter_id = lobResult.lob_letter_id;
      sentCount++;

    } catch (err) {
      // Mark as failed so it doesn't retry infinitely
      await patchApproval(letter.id, {
        status:     'send_failed',
        updated_at: new Date().toISOString(),
      });

      detail.status = 'send_failed';
      detail.error = err.message;
      failedCount++;
    }

    results.push(detail);
  }

  return res.status(200).json({
    sent:     sentCount,
    skipped:  skippedCount,
    failed:   failedCount,
    dry_run:  isDryRun,
    details:  results,
  });
};
