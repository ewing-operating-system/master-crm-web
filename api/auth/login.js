/**
 * POST /api/auth/login
 *
 * Accepts: { password: "..." }
 * Returns: { ok: true, company: "HR.com Ltd", redirect: "/hrcom-ltd-hub.html" }
 * Sets:    portal_session cookie (HttpOnly, Secure, 7 days)
 *
 * The password itself identifies the company — no username needed.
 */

const COMPANIES = {
  hrcom: {
    name: 'HR.com Ltd',
    envVar: 'PORTAL_PW_HRCOM',
    hub: '/hrcom-ltd-hub.html',
  },
  aquascience: {
    name: 'AquaScience',
    envVar: 'PORTAL_PW_AQUASCIENCE',
    hub: '/aquascience-hub.html',
  },
  springer: {
    name: 'Springer Floor',
    envVar: 'PORTAL_PW_SPRINGER',
    hub: '/springer-floor-hub.html',
  },
  aircontrol: {
    name: 'Air Control',
    envVar: 'PORTAL_PW_AIRCONTROL',
    hub: '/air-control-hub.html',
  },
  designprecast: {
    name: 'Design Precast & Pipe',
    envVar: 'PORTAL_PW_DESIGNPRECAST',
    hub: '/design-precast-and-pipe-inc-hub.html',
  },
  wieser: {
    name: 'Wieser Concrete Products',
    envVar: 'PORTAL_PW_WIESER',
    hub: '/wieser-concrete-products-inc-hub.html',
  },
};

const ADMIN_ENV_VAR = 'PORTAL_PW_ADMIN';

function authenticatePassword(password, env) {
  // Check admin password first
  const adminPw = env[ADMIN_ENV_VAR];
  if (adminPw && password === adminPw) {
    return 'admin';
  }
  // Check each company password
  for (const [slug, config] of Object.entries(COMPANIES)) {
    const pw = env[config.envVar];
    if (pw && password === pw) {
      return slug;
    }
  }
  return null;
}

export default function handler(req, res) {
  // Only POST
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { password, redirect } = req.body || {};

  if (!password) {
    return res.status(400).json({ error: 'Password required' });
  }

  // Debug: log which env vars are set (no values)
  const envCheck = Object.entries(COMPANIES).map(([slug, c]) => `${slug}:${process.env[c.envVar] ? 'SET' : 'MISSING'}`);
  console.log('Portal auth attempt. Env vars:', envCheck.join(', '), 'Admin:', process.env[ADMIN_ENV_VAR] ? 'SET' : 'MISSING');

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
    const company = COMPANIES[role];
    if (company) {
      redirectTo = company.hub;
    }
  }

  return res.status(200).json({
    ok: true,
    company: role === 'admin' ? 'Admin' : COMPANIES[role]?.name || role,
    redirect: redirectTo,
  });
}
