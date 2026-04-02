/**
 * GET /api/meetings/media-url?id=<fireflies_id>
 *
 * Returns fresh signed audio/video URLs from Fireflies.
 * CDN URLs expire after ~3 days, so this endpoint fetches on demand.
 *
 * Response (200):
 *   { audio_url: string, video_url: string, transcript_url: string }
 *
 * Credentials: Uses Claude CLI to invoke Fireflies MCP tools.
 * Env vars required: none (Claude CLI inherits from shell)
 */

'use strict';

const { execSync } = require('child_process');

// Simple in-memory cache (survives within a single serverless instance)
const cache = new Map();
const CACHE_TTL = 60 * 60 * 1000; // 1 hour

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

  // Check cache
  const cached = cache.get(id);
  if (cached && Date.now() - cached.ts < CACHE_TTL) {
    return res.status(200).json(cached.data);
  }

  // Fetch from Fireflies via Claude CLI
  const prompt = `Use the Fireflies MCP tool mcp__claude_ai_Fireflies__fireflies_get_transcript to fetch transcript with ID "${id}".
Return ONLY a JSON object with these exact fields:
{"audio_url": "the audio URL", "video_url": "the video URL", "transcript_url": "the transcript URL"}
No markdown, no prose. ONLY the JSON object.`;

  try {
    const result = execSync(
      `echo ${JSON.stringify(prompt)} | claude -p --output-format text`,
      { timeout: 60000, encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] }
    );

    // Parse response — strip markdown fences
    let raw = result.trim()
      .replace(/^```(?:json)?\s*/m, '')
      .replace(/\s*```$/m, '');

    const match = raw.match(/\{[^}]+\}/s);
    if (!match) {
      return res.status(502).json({ error: 'Could not parse Fireflies response' });
    }

    const data = JSON.parse(match[0]);
    const response = {
      audio_url: data.audio_url || null,
      video_url: data.video_url || null,
      transcript_url: data.transcript_url || `https://app.fireflies.ai/view/${id}`,
    };

    // Cache it
    cache.set(id, { data: response, ts: Date.now() });

    return res.status(200).json(response);
  } catch (err) {
    // Fallback: return the Fireflies view URL
    return res.status(200).json({
      audio_url: null,
      video_url: null,
      transcript_url: `https://app.fireflies.ai/view/${id}`,
      error: 'Could not fetch fresh media URLs',
    });
  }
};
