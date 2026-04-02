/**
 * GET /api/meetings/media-url?id=<fireflies_id>
 *
 * Returns audio/video URLs for a meeting transcript.
 * Reads from Supabase meeting_transcripts table where URLs are stored
 * and refreshed by the local meeting_pages.py cron (hourly 9am-5pm).
 *
 * Response (200):
 *   { audio_url: string, video_url: string, transcript_url: string }
 *
 * Credentials: all keys come from env vars. See .env.example for names.
 * Env vars required: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */

'use strict';

function supabaseHeaders() {
  return {
    'apikey':        process.env.SUPABASE_SERVICE_ROLE_KEY,
    'Authorization': `Bearer ${process.env.SUPABASE_SERVICE_ROLE_KEY}`,
    'Content-Type':  'application/json',
  };
}

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(204).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const id = req.query.id;
  if (!id) {
    return res.status(400).json({ error: 'id query parameter is required (Fireflies transcript ID)' });
  }

  try {
    const url = `${process.env.SUPABASE_URL}/rest/v1/meeting_transcripts`
      + `?fireflies_id=eq.${encodeURIComponent(id)}`
      + '&select=audio_url,fireflies_id'
      + '&limit=1';

    const resp = await fetch(url, { headers: supabaseHeaders() });
    if (!resp.ok) {
      throw new Error(`Supabase error: ${resp.status}`);
    }

    const rows = await resp.json();
    const row = rows[0];

    if (!row) {
      return res.status(404).json({ error: 'Transcript not found' });
    }

    // audio_url stores a JSON string with both URLs if available
    let audio_url = null;
    let video_url = null;

    // Try to parse as JSON (new format: {audio: "...", video: "..."})
    try {
      const media = JSON.parse(row.audio_url);
      audio_url = media.audio || null;
      video_url = media.video || null;
    } catch {
      // Old format: plain URL string
      audio_url = row.audio_url || null;
    }

    return res.status(200).json({
      audio_url,
      video_url,
      transcript_url: `https://app.fireflies.ai/view/${id}`,
    });
  } catch (err) {
    return res.status(200).json({
      audio_url: null,
      video_url: null,
      transcript_url: `https://app.fireflies.ai/view/${id}`,
      error: 'Could not fetch media URLs',
    });
  }
};
