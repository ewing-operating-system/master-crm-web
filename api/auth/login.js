import { authenticatePassword, COMPANIES } from '../../lib/portal-config.js';

/**
 * POST /api/auth/login
 *
 * Accepts: { password: "..." }
 * Returns: { ok: true, company: "HR.com Ltd", redirect: "/hrcom-ltd-hub.html" }
 * Sets:    portal_session cookie (HttpOnly, Secure, 7 days)
 *
 * The password itself identifies the company — no username needed.
 */

export default function handler(req, res) {
  // Only POST
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { password, redirect } = req.body || {};

  if (!password) {
    return res.status(400).json({ error: 'Password required' });
  }

  // Authenticate
  const role = authenticatePassword(password, process.env);

  if (!role) {
    return res.status(401).json({ error: 'Invalid password' });
  }

  // Build session cookie
  const session = {
    role,
    ts: Math.floor(Date.now() / 1000),
  };

  const cookieValue = Buffer.from(JSON.stringify(session)).toString('base64');

  // Set cookie — 7 days, HttpOnly, Secure
  res.setHeader('Set-Cookie', [
    `portal_session=${cookieValue}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=604800`,
  ]);

  // Determine redirect target
  let redirectTo = redirect || '/';
  if (role !== 'admin' && (!redirect || redirect === '/')) {
    // Send company users to their hub page
    const company = COMPANIES[role];
    if (company) {
      // Find the hub page — use first prefix + "-hub.html" pattern
      const hubPages = {
        hrcom: '/hrcom-ltd-hub.html',
        aquascience: '/aquascience-hub.html',
        springer: '/springer-floor-hub.html',
        aircontrol: '/air-control-hub.html',
        designprecast: '/design-precast-and-pipe-inc-hub.html',
        wieser: '/wieser-concrete-products-inc-hub.html',
      };
      redirectTo = hubPages[role] || '/';
    }
  }

  return res.status(200).json({
    ok: true,
    company: role === 'admin' ? 'Admin' : COMPANIES[role]?.name || role,
    redirect: redirectTo,
  });
}
