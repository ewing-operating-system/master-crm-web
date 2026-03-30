/**
 * POST /api/webhooks/lob
 *
 * Receives Lob delivery status webhooks and updates letter_approvals
 * + cost_ledger in Supabase. Triggers Salesfinity call task on delivery.
 *
 * Vercel requires the raw body for HMAC verification — body parsing is
 * disabled for this route via vercel.json bodyParser config.
 *
 * Env vars required:
 *   LOB_WEBHOOK_SECRET, SUPABASE_URL, SUPABASE_SERVICE_KEY
 *   SALESFINITY_API_KEY (optional — enables call task on delivery)
 *   EWING_TELEGRAM_CHAT_ID (optional — enables 401 alerts)
 */

'use strict';

const { handleLobWebhook } = require('../../lib/lob-integration');

/**
 * Collect raw body from the readable stream (Vercel does NOT auto-parse
 * when bodyParser is false, so req.body will be undefined).
 */
function getRawBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end',  () => resolve(Buffer.concat(chunks)));
    req.on('error', reject);
  });
}

module.exports = async function handler(req, res) {
  // Attach raw body for signature verification
  const rawBuffer = await getRawBody(req);
  req.rawBody = rawBuffer.toString('utf8');

  return handleLobWebhook(req, res);
};
