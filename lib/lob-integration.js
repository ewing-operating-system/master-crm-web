/**
 * lob-integration.js — Next Chapter M&A Advisory
 *
 * Lob API integration for physical letter delivery.
 * Handles sendPhysicalLetter(), webhook processing, cost tracking,
 * Salesfinity task creation, and error/retry logic.
 *
 * Environment variables required:
 *   LOB_API_KEY          — Live key (starts with live_)
 *   LOB_WEBHOOK_SECRET   — For signature verification on inbound webhooks
 *   SUPABASE_URL         — Supabase project URL
 *   SUPABASE_SERVICE_KEY — Supabase service role key (server-side only)
 *   SALESFINITY_API_KEY  — For downstream call task creation
 *   EWING_TELEGRAM_CHAT_ID — For 401 / auth failure alerts
 */

'use strict';

const https = require('https');
const crypto = require('crypto');

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

const LOB_BASE_URL = 'https://api.lob.com/v1';

// Return address — loaded from environment variables at send time
function getFromAddress() {
  return {
    name:            process.env.LOB_FROM_NAME    || 'Next Chapter Capital',
    address_line1:   process.env.LOB_FROM_ADDRESS || '123 Main Street',
    address_city:    process.env.LOB_FROM_CITY    || 'New York',
    address_state:   process.env.LOB_FROM_STATE   || 'NY',
    address_zip:     process.env.LOB_FROM_ZIP     || '10001',
    address_country: 'US',
  };
}

// Estimated cost per letter in USD (color + paper + postage)
const LOB_COST_PER_LETTER = 1.75;

// Retry settings for 5xx errors
const RETRY_MAX_ATTEMPTS = 3;
const RETRY_BASE_DELAY_MS = 1000; // doubles each attempt

// ---------------------------------------------------------------------------
// Internal helpers
// ---------------------------------------------------------------------------

/**
 * Minimal HTTPS request wrapper — no external deps required.
 * Returns { statusCode, body } where body is parsed JSON or raw text.
 */
function httpRequest(options, postData) {
  return new Promise((resolve, reject) => {
    const req = https.request(options, (res) => {
      let raw = '';
      res.on('data', (chunk) => { raw += chunk; });
      res.on('end', () => {
        let body;
        try { body = JSON.parse(raw); } catch (_) { body = raw; }
        resolve({ statusCode: res.statusCode, body });
      });
    });
    req.on('error', reject);
    if (postData) req.write(postData);
    req.end();
  });
}

/** Basic auth header: Lob uses HTTP Basic with API key as the username. */
function lobAuthHeader(apiKey) {
  return 'Basic ' + Buffer.from(apiKey + ':').toString('base64');
}

/** Sleep helper for exponential backoff. */
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Send a Telegram alert for critical errors (401, auth failures). */
async function sendTelegramAlert(message) {
  const chatId = process.env.EWING_TELEGRAM_CHAT_ID;
  if (!chatId) return; // silently skip if not configured

  try {
    // Uses openclaw CLI via child_process to stay consistent with project patterns
    const { exec } = require('child_process');
    const escaped = message.replace(/"/g, '\\"');
    exec(
      `openclaw message send --channel telegram --target "${chatId}" --message "[Argus] ${escaped}"`,
      () => {} // fire and forget
    );
  } catch (_) {
    // Never let alerting crash the main flow
  }
}

// ---------------------------------------------------------------------------
// Supabase helpers (lightweight — avoids pulling in @supabase/supabase-js)
// ---------------------------------------------------------------------------

function supabaseHeaders() {
  return {
    'apikey': process.env.SUPABASE_SERVICE_KEY,
    'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_KEY}`,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
  };
}

async function supabaseUpsert(table, record, conflictColumn) {
  const url = new URL(`${process.env.SUPABASE_URL}/rest/v1/${table}`);
  const payload = JSON.stringify(record);
  const headers = {
    ...supabaseHeaders(),
    'Prefer': `resolution=merge-duplicates,return=representation`,
  };

  const options = {
    hostname: url.hostname,
    path: url.pathname + (conflictColumn ? `?on_conflict=${conflictColumn}` : ''),
    method: 'POST',
    headers: { ...headers, 'Content-Length': Buffer.byteLength(payload) },
  };

  const result = await httpRequest(options, payload);
  if (result.statusCode >= 300) {
    throw new Error(`Supabase upsert failed (${table}): ${JSON.stringify(result.body)}`);
  }
  return result.body;
}

async function supabasePatch(table, id, updates) {
  const url = new URL(`${process.env.SUPABASE_URL}/rest/v1/${table}?id=eq.${id}`);
  const payload = JSON.stringify(updates);
  const headers = supabaseHeaders();

  const options = {
    hostname: url.hostname,
    path: url.pathname + url.search,
    method: 'PATCH',
    headers: { ...headers, 'Content-Length': Buffer.byteLength(payload) },
  };

  const result = await httpRequest(options, payload);
  if (result.statusCode >= 300) {
    throw new Error(`Supabase patch failed (${table}, id=${id}): ${JSON.stringify(result.body)}`);
  }
  return result.body;
}

async function supabaseInsert(table, record) {
  const url = new URL(`${process.env.SUPABASE_URL}/rest/v1/${table}`);
  const payload = JSON.stringify(record);
  const headers = supabaseHeaders();

  const options = {
    hostname: url.hostname,
    path: url.pathname,
    method: 'POST',
    headers: { ...headers, 'Content-Length': Buffer.byteLength(payload) },
  };

  const result = await httpRequest(options, payload);
  if (result.statusCode >= 300) {
    throw new Error(`Supabase insert failed (${table}): ${JSON.stringify(result.body)}`);
  }
  return result.body;
}

// ---------------------------------------------------------------------------
// Salesfinity: create follow-up call task after letter delivery
// ---------------------------------------------------------------------------

async function createSalesffinityCallTask({ recipientName, recipientPhone, letterId, lobLetterId }) {
  const apiKey = process.env.SALESFINITY_API_KEY;
  if (!apiKey) return null; // non-fatal if not configured

  const payload = JSON.stringify({
    task_type: 'call',
    contact_name: recipientName,
    contact_phone: recipientPhone || null,
    notes: `Call ${recipientName} about their letter. Lob letter ID: ${lobLetterId}. Internal letter ID: ${letterId}.`,
    source: 'lob_delivery_webhook',
    metadata: { letter_id: letterId, lob_letter_id: lobLetterId },
  });

  const salesfinityUrl = new URL('https://api.salesfinity.com/v1/tasks');
  const options = {
    hostname: salesfinityUrl.hostname,
    path: salesfinityUrl.pathname,
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(payload),
    },
  };

  try {
    const result = await httpRequest(options, payload);
    if (result.statusCode === 201 || result.statusCode === 200) {
      return result.body;
    }
    // Log but don't throw — Salesfinity failure shouldn't kill webhook processing
    console.error(`Salesfinity task creation failed (${result.statusCode}):`, result.body);
    return null;
  } catch (err) {
    console.error('Salesfinity task creation error:', err.message);
    return null;
  }
}

// ---------------------------------------------------------------------------
// Core: sendPhysicalLetter
// ---------------------------------------------------------------------------

/**
 * Send a physical letter via Lob API.
 *
 * @param {Object} params
 * @param {string} params.letter_id               — Internal tracking ID (letter_approvals.id)
 * @param {string} params.recipient_name          — Full name on the envelope
 * @param {string} params.recipient_address_line1 — Street address
 * @param {string} params.recipient_city
 * @param {string} params.recipient_state         — 2-letter abbreviation
 * @param {string} params.recipient_zip
 * @param {string} params.letter_html             — Rendered HTML from LetterEngine
 * @param {number} [params.expected_cost]         — Pre-calculated cost for validation (USD)
 *
 * @returns {Promise<{
 *   lob_letter_id: string,
 *   lob_status: string,
 *   tracking_url: string|null,
 *   expected_delivery_date: string|null,
 *   cost_incurred: number
 * }>}
 *
 * @throws {Error} with .code set to 'INVALID_ADDRESS', 'AUTH_FAILURE', or 'SERVICE_ERROR'
 */
async function sendPhysicalLetter({
  letter_id,
  recipient_name,
  recipient_address_line1,
  recipient_city,
  recipient_state,
  recipient_zip,
  letter_html,
  expected_cost,
}) {
  const apiKey = process.env.LOB_API_KEY;
  if (!apiKey) {
    throw Object.assign(new Error('LOB_API_KEY not set in environment'), { code: 'AUTH_FAILURE' });
  }

  const payload = JSON.stringify({
    to: {
      name: recipient_name,
      address_line1: recipient_address_line1,
      address_city: recipient_city,
      address_state: recipient_state,
      address_zip: recipient_zip,
      address_country: 'US',
    },
    from: getFromAddress(),
    file: letter_html,
    color: false,           // B&W to stay at the lower cost tier
    double_sided: false,
    address_placement: 'top_first_page',
    metadata: {
      letter_id,
      source: 'master-crm',
    },
  });

  const options = {
    hostname: 'api.lob.com',
    path: '/v1/letters',
    method: 'POST',
    headers: {
      'Authorization': lobAuthHeader(apiKey),
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(payload),
      'Lob-Version': '2020-02-11',
    },
  };

  let attempt = 0;
  while (attempt < RETRY_MAX_ATTEMPTS) {
    attempt++;
    const { statusCode, body } = await httpRequest(options, payload);

    // --- Success ---
    if (statusCode === 200 || statusCode === 201) {
      const costIncurred = body.price
        ? parseFloat(body.price)
        : LOB_COST_PER_LETTER;

      return {
        lob_letter_id: body.id,
        lob_status: body.status || 'processing',
        tracking_url: body.url || null,
        expected_delivery_date: body.expected_delivery_date || null,
        cost_incurred: costIncurred,
      };
    }

    // --- Invalid address or bad request (400/422) — do not retry, do not charge ---
    if (statusCode === 400 || statusCode === 422) {
      const detail = body.error ? body.error.message : JSON.stringify(body);
      const err = new Error(`Invalid address or bad request: ${detail}`);
      err.code = 'INVALID_ADDRESS';
      err.lob_error = body;
      throw err;
    }

    // --- Auth failure (401) — alert immediately, do not retry ---
    if (statusCode === 401) {
      await sendTelegramAlert(
        'LOB_API_KEY rejected (401). Physical letter sending is down. Check environment secrets.'
      );
      const err = new Error('Lob API authentication failed (401)');
      err.code = 'AUTH_FAILURE';
      throw err;
    }

    // --- Lob service error (5xx) — retry with exponential backoff ---
    if (statusCode >= 500) {
      if (attempt < RETRY_MAX_ATTEMPTS) {
        const delay = RETRY_BASE_DELAY_MS * Math.pow(2, attempt - 1);
        console.warn(`Lob 5xx (attempt ${attempt}/${RETRY_MAX_ATTEMPTS}), retrying in ${delay}ms...`);
        await sleep(delay);
        continue;
      }
      const err = new Error(`Lob service error after ${RETRY_MAX_ATTEMPTS} attempts: ${statusCode}`);
      err.code = 'SERVICE_ERROR';
      err.lob_error = body;
      throw err;
    }

    // --- Unexpected status ---
    const err = new Error(`Unexpected Lob response: ${statusCode}`);
    err.code = 'SERVICE_ERROR';
    err.lob_error = body;
    throw err;
  }
}

// ---------------------------------------------------------------------------
// Webhook handler: POST /api/webhooks/lob
// ---------------------------------------------------------------------------

/**
 * Lob webhook status map — normalize Lob event types to our lob_status values.
 *
 * Lob event types:  letter.created, letter.mailed, letter.in_transit,
 *                   letter.in_local_area, letter.processed_for_delivery,
 *                   letter.delivered, letter.re_routed, letter.returned_to_sender,
 *                   letter.failed
 */
const LOB_EVENT_TO_STATUS = {
  'letter.created': 'processing',
  'letter.mailed': 'in_production',
  'letter.in_transit': 'in_transit',
  'letter.in_local_area': 'in_transit',
  'letter.processed_for_delivery': 'in_transit',
  'letter.delivered': 'delivered',
  'letter.re_routed': 'in_transit',
  'letter.returned_to_sender': 'failed',
  'letter.failed': 'failed',
};

/**
 * Verify Lob webhook signature.
 * Lob signs payloads with HMAC-SHA256 using the webhook secret.
 * Header: Lob-Signature
 */
function verifyLobSignature(rawBody, signatureHeader) {
  const secret = process.env.LOB_WEBHOOK_SECRET;
  if (!secret) {
    // If no secret configured, skip verification (dev/test mode)
    console.warn('LOB_WEBHOOK_SECRET not set — skipping signature verification');
    return true;
  }
  if (!signatureHeader) return false;

  const expected = crypto
    .createHmac('sha256', secret)
    .update(rawBody)
    .digest('hex');

  // Lob may send "t=<timestamp>,v1=<sig>" format — extract sig portion
  let received = signatureHeader;
  const v1Match = signatureHeader.match(/v1=([a-f0-9]+)/);
  if (v1Match) received = v1Match[1];

  // Reject if lengths differ — padEnd would allow short/malformed signatures to pass
  if (received.length !== expected.length) return false;

  return crypto.timingSafeEqual(
    Buffer.from(expected, 'hex'),
    Buffer.from(received, 'hex')
  );
}

/**
 * handleLobWebhook — process a Lob webhook POST.
 *
 * Designed to work as a standalone Vercel serverless function or be called
 * from any Node.js HTTP handler.
 *
 * @param {Object} req — must expose: req.method, req.rawBody (Buffer/string), req.headers
 * @param {Object} res — must expose: res.status(n).json({...})
 */
async function handleLobWebhook(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const rawBody = req.rawBody || req.body;
  const signature = req.headers['lob-signature'] || req.headers['x-lob-signature'];

  // Verify signature
  if (!verifyLobSignature(
    typeof rawBody === 'string' ? rawBody : JSON.stringify(rawBody),
    signature
  )) {
    console.error('Lob webhook signature verification failed');
    return res.status(401).json({ error: 'Invalid signature' });
  }

  // Parse event
  let event;
  try {
    event = typeof rawBody === 'string' ? JSON.parse(rawBody) : rawBody;
  } catch (_) {
    return res.status(400).json({ error: 'Invalid JSON body' });
  }

  const eventType = event.event_type?.id || event.event_type;
  const lobObject = event.body || event.object || {};
  const lobLetterId = lobObject.id;
  const lobStatus = LOB_EVENT_TO_STATUS[eventType] || 'unknown';
  const trackingUrl = lobObject.url || null;
  const deliveredAt = eventType === 'letter.delivered'
    ? (lobObject.date_modified || new Date().toISOString())
    : null;

  // Retrieve our internal letter_id from Lob metadata
  const letterId = lobObject.metadata?.letter_id;

  if (!lobLetterId) {
    console.warn('Lob webhook missing letter ID, ignoring:', event);
    return res.status(200).json({ received: true });
  }

  try {
    // 1. Update letter_approvals
    if (letterId) {
      const updates = {
        lob_letter_id: lobLetterId,
        lob_status: lobStatus,
        tracking_url: trackingUrl,
      };
      if (lobStatus === 'processing' || lobStatus === 'in_production') {
        updates.status = 'sent';
      }
      if (deliveredAt) {
        updates.delivered_at = deliveredAt;
        updates.lob_status = 'delivered';
      }

      await supabasePatch('letter_approvals', letterId, updates);
    }

    // 2. Log to cost_ledger on first mailing event (avoid double-counting)
    if (eventType === 'letter.mailed' && letterId) {
      const costAmount = lobObject.price
        ? parseFloat(lobObject.price)
        : LOB_COST_PER_LETTER;

      await supabaseInsert('cost_ledger', {
        cost_source: 'lob',
        cost_amount: costAmount,
        letter_id: letterId,
        lob_letter_id: lobLetterId,
        description: `Physical letter mailed — Lob ID: ${lobLetterId}`,
        recorded_at: new Date().toISOString(),
      });
    }

    // 3. Trigger Salesfinity call task on delivery
    if (eventType === 'letter.delivered' && letterId) {
      const recipientName = lobObject.to?.name || 'Unknown';
      const recipientPhone = lobObject.metadata?.recipient_phone || null;

      await createSalesffinityCallTask({
        recipientName,
        recipientPhone,
        letterId,
        lobLetterId,
      });
    }

    return res.status(200).json({ received: true, lob_status: lobStatus });
  } catch (err) {
    console.error('Lob webhook processing error:', err.message);
    // Return 200 to prevent Lob from retrying for data errors;
    // return 500 for infrastructure errors so Lob will retry.
    const isInfraError = err.message.includes('Supabase');
    return res.status(isInfraError ? 500 : 200).json({ error: err.message });
  }
}

// ---------------------------------------------------------------------------
// Test mode helper
// ---------------------------------------------------------------------------

/**
 * Returns true when running against Lob test keys.
 * Test letters render with a SPECIMEN watermark and are never physically mailed.
 * Lob test keys start with "test_".
 */
function isTestMode() {
  const key = process.env.LOB_API_KEY || '';
  return key.startsWith('test_');
}

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

module.exports = {
  sendPhysicalLetter,
  handleLobWebhook,
  verifyLobSignature,
  isTestMode,
  // Exported for unit testing
  _internal: {
    createSalesffinityCallTask,
    lobAuthHeader,
    LOB_EVENT_TO_STATUS,
    DEFAULT_FROM_ADDRESS,
    LOB_COST_PER_LETTER,
  },
};
