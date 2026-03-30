/**
 * POST /api/letters/send — Send a physical letter via Lob API
 * Feature #63: Lob API Integration
 *
 * Body: { target_id, letter_html, recipient: { name, line1, city, state, zip } }
 * Returns: { lob_id, tracking_url, cost, status }
 */

const LOB_API_KEY = process.env.LOB_API_KEY || '';
const SUPABASE_URL = process.env.SUPABASE_URL || 'https://dwrnfpjcvydhmhnvyzov.supabase.co';
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

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { target_id, letter_html, recipient, entity } = req.body;

    if (!letter_html || !recipient) {
      return res.status(400).json({ error: 'Missing letter_html or recipient' });
    }

    // Validate recipient address
    const required = ['name', 'address_line1', 'address_city', 'address_state', 'address_zip'];
    for (const field of required) {
      if (!recipient[field]) {
        return res.status(400).json({ error: `Missing recipient.${field}` });
      }
    }

    // Send via Lob
    const lobResult = await lobRequest('letters', {
      to: {
        name: recipient.name,
        address_line1: recipient.address_line1,
        address_line2: recipient.address_line2 || '',
        address_city: recipient.address_city,
        address_state: recipient.address_state,
        address_zip: recipient.address_zip,
      },
      from: NC_RETURN_ADDRESS,
      file: letter_html,
      color: false,
      description: `NC Letter — ${recipient.name}`,
      metadata: {
        target_id: target_id || '',
        entity: entity || 'next_chapter',
        sent_at: new Date().toISOString(),
      },
    });

    // Update letter_approvals with Lob tracking
    if (target_id) {
      await supabaseRequest('PATCH',
        `letter_approvals?target_id=eq.${target_id}&status=eq.approved`,
        {
          lob_id: lobResult.id,
          lob_status: 'created',
          lob_url: lobResult.url || '',
          sent_at: new Date().toISOString(),
          status: 'sent',
        }
      );
    }

    // Log cost to cost_ledger
    await supabaseRequest('POST', 'cost_ledger', {
      entity: entity || 'next_chapter',
      service: 'lob',
      operation: 'letter_send',
      cost: LOB_COST_PER_LETTER,
      target_id: target_id || null,
      metadata: JSON.stringify({ lob_id: lobResult.id }),
      created_at: new Date().toISOString(),
    });

    return res.status(200).json({
      lob_id: lobResult.id,
      tracking_url: lobResult.url || '',
      expected_delivery: lobResult.expected_delivery_date || '',
      cost: LOB_COST_PER_LETTER,
      status: 'sent',
    });

  } catch (err) {
    console.error('Letter send error:', err);
    return res.status(500).json({ error: err.message });
  }
}
