/**
 * GET /api/auth/debug — temporary diagnostic endpoint
 * Returns which portal env vars are set (no values exposed)
 */
export default function handler(req, res) {
  const vars = [
    'PORTAL_PW_ADMIN',
    'PORTAL_PW_HRCOM',
    'PORTAL_PW_AQUASCIENCE',
    'PORTAL_PW_SPRINGER',
    'PORTAL_PW_AIRCONTROL',
    'PORTAL_PW_DESIGNPRECAST',
    'PORTAL_PW_WIESER',
  ];

  const status = {};
  for (const v of vars) {
    status[v] = process.env[v] ? `SET (${process.env[v].length} chars)` : 'MISSING';
  }

  return res.status(200).json({
    envVarStatus: status,
    nodeVersion: process.version,
    timestamp: new Date().toISOString(),
  });
}
