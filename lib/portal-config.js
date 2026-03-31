/**
 * Client Portal Configuration
 * Maps company slugs to URL path prefixes and password env vars.
 *
 * To add a new client:
 * 1. Add entry here with their slug, path prefixes, and display name
 * 2. Set PORTAL_PW_<SLUG> in Vercel env vars
 * 3. Send the client their password
 */

export const COMPANIES = {
  hrcom: {
    name: 'HR.com Ltd',
    prefixes: ['hrcom', 'hr-com', 'dataroom-hrcom', 'interactive-hrcom', 'meeting-hrcom'],
    envVar: 'PORTAL_PW_HRCOM',
  },
  aquascience: {
    name: 'AquaScience',
    prefixes: ['aquascience', 'dataroom-aquascience', 'interactive-aquascience', 'meeting-aquascience'],
    envVar: 'PORTAL_PW_AQUASCIENCE',
  },
  springer: {
    name: 'Springer Floor',
    prefixes: ['springer', 'dataroom-springer', 'interactive-springer', 'meeting-springer'],
    envVar: 'PORTAL_PW_SPRINGER',
  },
  aircontrol: {
    name: 'Air Control',
    prefixes: ['air-control', 'dataroom-air-control', 'interactive-air-control', 'meeting-air-control'],
    envVar: 'PORTAL_PW_AIRCONTROL',
  },
  designprecast: {
    name: 'Design Precast & Pipe',
    prefixes: ['design-precast', 'dataroom-design-precast', 'interactive-design-precast', 'meeting-design-precast'],
    envVar: 'PORTAL_PW_DESIGNPRECAST',
  },
  wieser: {
    name: 'Wieser Concrete Products',
    prefixes: ['wieser', 'dataroom-wieser', 'interactive-wieser', 'meeting-wieser'],
    envVar: 'PORTAL_PW_WIESER',
  },
};

// Admin password grants access to ALL pages
export const ADMIN_ENV_VAR = 'PORTAL_PW_ADMIN';

// Pages that are never gated (public assets, login, API)
export const PUBLIC_PATHS = [
  '/login.html',
  '/api/',
  '/favicon.ico',
  '/_vercel/',
  '/outputs/',
  '/running-log.html',
  '/system-overview.html',
  '/version-history.html',
  '/feature-roadmap.html',
];

// File extensions that should never be gated
export const PUBLIC_EXTENSIONS = ['.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf', '.eot'];

/**
 * Given a URL pathname like "/hr-com-ltd_salesforce.html",
 * return the company slug it belongs to, or null if it's a shared page.
 */
export function getCompanyForPath(pathname) {
  const filename = pathname.split('/').pop().toLowerCase();
  for (const [slug, config] of Object.entries(COMPANIES)) {
    for (const prefix of config.prefixes) {
      if (filename.startsWith(prefix)) {
        return slug;
      }
    }
  }
  return null; // shared/internal page
}

/**
 * Given a password, return the company slug it authenticates for,
 * or 'admin' for admin password, or null if invalid.
 */
export function authenticatePassword(password, env) {
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
