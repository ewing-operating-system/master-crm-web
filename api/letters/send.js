/**
 * POST /api/letters/send — Send a physical letter via Lob API
 * Feature #63: Lob API Integration
 *
 * Body: { target_id, letter_html, recipient: { name, line1, city, state, zip } }
 * Returns: { lob_id, tracking_url, cost, status }
 */

const LOB_API_KEY = process.env.LOB_API_KEY || '';
const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || '';
const LOB_COST_PER_LETTER = 1.75;

const NC_RETURN_ADDRESS = {
  name: 'Next Chapter Advisory',
  address_line1: process.env.NC_RETURN_ADDRESS_LINE1 || '',
  address_city: process.env.NC_RETURN_ADDRESS_CITY || '',
  address_state: process.env.NC_RETURN_ADDRESS_STATE || '',
  address_zip: process.env.NC_RETURN_ADDRESS_ZIP || '',
};

async function lobRequest(path, data) {
  const auth = Buffer.from(`${LOB_API_KEY}:`).toString('base64');
  const res = await fetch(`https://api.lob.com/v1/${path}`, {
    method: 'POST',
    headers: {
      'Authorization': `Basic ${auth}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Lob API error ${res.status}: ${err}`);
  }
  return res.json();
}

async function supabaseRequest(method, path, data) {
  const headers = {
    'apikey': SUPABASE_KEY,
    'Authorization': `Bearer ${SUPABASE_KEY}`,
    'Content-Type': 'application/json',
    'Prefer': 'return=representation',
  };
  const opts = { method, headers };
  if (data) opts.body = JSON.stringify(data);
  const res = await fetch(`${SUPABASE_URL}/rest/v1/${path}`, opts);
  return res.json();
}

module.exports = async function handler(req, res) {
  // DISABLED — All letters must go through the approval queue.
  // Use /api/letters/generate to create, /api/letters/approve to approve,
  // then /api/letters/send-to-lob or /api/letters/batch-send to mail.
  return res.status(403).json({
    error: 'Direct letter sending is disabled. Letters must be approved before sending.',
    help: 'Use POST /api/letters/approve to approve a letter, then POST /api/letters/send-to-lob to send it.',
  });
}
