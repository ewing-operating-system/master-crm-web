/**
 * POST /api/letters/send-to-lob
 *
 * Fetches a letter_approval record, sends the letter via Lob,
 * then updates the record with lob_letter_id + status='sent'.
 *
 * Request body:
 *   { approval_id: string }
 *
 * Response (200):
 *   { lob_letter_id, lob_status, tracking_url, expected_delivery_date, cost_incurred }
 *
 * NOTE: letter_approvals table requires address columns:
 *   recipient_name, recipient_address_line1, recipient_city,
 *   recipient_state, recipient_zip
 * If absent, falls back to the companies table address.
 *
 * Env vars required:
 *   SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, LOB_API_KEY
 *   LOB_FROM_NAME, LOB_FROM_ADDRESS, LOB_FROM_CITY, LOB_FROM_STATE, LOB_FROM_ZIP
 */

'use strict';

const { sendPhysicalLetter } = require('../../lib/lob-integration');

// ---------------------------------------------------------------------------
// Supabase fetch helpers (service role — bypasses RLS)
// ---------------------------------------------------------------------------

function supabaseServiceHeaders() {
  return {
    'apikey':        process.env.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
    'Content-Type':  'application/json',
    'Prefer':        'return=representation',
  };
}

async function getApprovalRecord(approvalId) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/letter_approvals`
    + `?id=eq.${encodeURIComponent(approvalId)}`
    + '&select=*'
    + '&limit=1';

  const res = await fetch(url, { headers: supabaseServiceHeaders() });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase fetch approval failed (${res.status}): ${body}`);
  }
  const rows = await res.json();
  return rows[0] || null;
}

async function getCompanyAddress(companyId) {
  if (!companyId) return null;
  const url = `${process.env.SUPABASE_URL}/rest/v1/companies`
    + `?id=eq.${encodeURIComponent(companyId)}`
    + '&select=owner_name,address_line1,city,state,zip'
    + '&limit=1';

  const res = await fetch(url, { headers: supabaseServiceHeaders() });
  if (!res.ok) return null;
  const rows = await res.json();
  return rows[0] || null;
}

async function patchApprovalRecord(approvalId, updates) {
  const url = `${process.env.SUPABASE_URL}/rest/v1/letter_approvals`
    + `?id=eq.${encodeURIComponent(approvalId)}`;

  const res = await fetch(url, {
    method:  'PATCH',
    headers: supabaseServiceHeaders(),
    body:    JSON.stringify(updates),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Supabase patch approval failed (${res.status}): ${body}`);
  }
}

// ---------------------------------------------------------------------------
// Handler
// ---------------------------------------------------------------------------

module.exports = async function handler(req, res) {
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

  // Kill switch — letter sending is OFF unless explicitly enabled
  if (process.env.LETTER_SENDING_ENABLED !== 'true') {
    return res.status(403).json({
      error: 'Letter sending is disabled. Set LETTER_SENDING_ENABLED=true in Vercel env vars to enable.',
    });
  }

  const { approval_id } = body || {};
  if (!approval_id) {
    return res.status(400).json({ error: 'approval_id is required' });
  }

  // 1. Load the approval record
  const approval = await getApprovalRecord(approval_id);
  if (!approval) {
    return res.status(404).json({ error: `No approval record found for id: ${approval_id}` });
  }
  if (approval.status === 'sent' || approval.lob_letter_id) {
    return res.status(409).json({ error: 'Letter already sent', lob_letter_id: approval.lob_letter_id });
  }
  if (approval.status !== 'approved') {
    return res.status(422).json({ error: `Letter must be approved before sending (current status: ${approval.status})` });
  }

  // 2. Resolve recipient address — prefer columns on letter_approvals, fall back to companies
  let recipientName         = approval.recipient_name;
  let recipientAddressLine1 = approval.recipient_address_line1;
  let recipientCity         = approval.recipient_city;
  let recipientState        = approval.recipient_state;
  let recipientZip          = approval.recipient_zip;

  if (!recipientAddressLine1 && approval.company_id) {
    const company = await getCompanyAddress(approval.company_id);
    if (company) {
      recipientName         = recipientName         || company.owner_name;
      recipientAddressLine1 = recipientAddressLine1 || company.address_line1;
      recipientCity         = recipientCity         || company.city;
      recipientState        = recipientState        || company.state;
      recipientZip          = recipientZip          || company.zip;
    }
  }

  if (!recipientAddressLine1 || !recipientCity || !recipientState || !recipientZip) {
    return res.status(422).json({
      error: 'Recipient address is incomplete. Add address columns to letter_approvals or ensure companies table has address data.',
    });
  }

  // 3. Send via Lob
  let lobResult;
  try {
    lobResult = await sendPhysicalLetter({
      letter_id:              approval_id,
      recipient_name:         recipientName || 'Business Owner',
      recipient_address_line1: recipientAddressLine1,
      recipient_city:         recipientCity,
      recipient_state:        recipientState,
      recipient_zip:          recipientZip,
      letter_html:            approval.letter_text,
    });
  } catch (err) {
    const statusCode = err.code === 'INVALID_ADDRESS' ? 422
      : err.code === 'AUTH_FAILURE' ? 503
      : 502;
    return res.status(statusCode).json({ error: err.message, code: err.code });
  }

  // 4. Update the approval record
  await patchApprovalRecord(approval_id, {
    status:        'sent',
    lob_letter_id: lobResult.lob_letter_id,
    lob_status:    lobResult.lob_status,
    tracking_url:  lobResult.tracking_url,
    sent_at:       new Date().toISOString(),
    updated_at:    new Date().toISOString(),
  });

  return res.status(200).json(lobResult);
};
