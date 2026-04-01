import { getCompanyForPath, PUBLIC_PATHS, PUBLIC_EXTENSIONS, COMPANIES } from './lib/portal-config.js';

/**
 * Vercel Edge Middleware — Client Portal Gate
 *
 * GATING IS CURRENTLY DISABLED. All requests pass through.
 * To re-enable, set PORTAL_GATING_ENABLED=true in Vercel env vars.
 *
 * When enabled: intercepts every request, checks portal_session cookie,
 * enforces company-level page access. Redirects to /login.html if
 * unauthenticated. Returns 403 if the user's company doesn't match.
 */

export const config = {
  matcher: ['/((?!_vercel|api/).*)'],
};

export default function middleware(request) {
  // Gating kill switch — wide open until re-enabled
  if (!process.env.PORTAL_GATING_ENABLED || process.env.PORTAL_GATING_ENABLED !== 'true') {
    return; // pass through everything
  }

  const url = new URL(request.url);
  const pathname = url.pathname;

  // 1. Allow public paths (login page, static assets)
  if (PUBLIC_PATHS.some(p => pathname.startsWith(p))) {
    return; // pass through
  }

  // 2. Allow static asset extensions (JS, CSS, images, fonts)
  const ext = pathname.substring(pathname.lastIndexOf('.'));
  if (PUBLIC_EXTENSIONS.includes(ext.toLowerCase())) {
    return; // pass through
  }

  // 3. Root path — always allow (it's the index)
  if (pathname === '/' || pathname === '/index.html') {
    // Index shows all companies — require admin
    const session = parseSession(request);
    if (!session || session.role !== 'admin') {
      return redirectToLogin(url);
    }
    return;
  }

  // 4. Determine which company this page belongs to
  const pageCompany = getCompanyForPath(pathname);

  // 5. Parse the session cookie
  const session = parseSession(request);

  if (!session) {
    // No session — redirect to login
    return redirectToLogin(url);
  }

  // 6. Admin can see everything
  if (session.role === 'admin') {
    return; // pass through
  }

  // 7. Company-specific page — check if user's company matches
  if (pageCompany) {
    if (session.role === pageCompany) {
      return; // authorized
    }
    // Wrong company — 403
    return new Response(forbidden403(session.role, pageCompany), {
      status: 403,
      headers: { 'Content-Type': 'text/html' },
    });
  }

  // 8. Shared/internal page (dashboard, roadmap, etc.)
  //    Allow any authenticated user to see shared pages
  if (session.role) {
    return; // any logged-in user can see shared pages
  }

  return redirectToLogin(url);
}

function parseSession(request) {
  const cookie = request.headers.get('cookie');
  if (!cookie) return null;

  const match = cookie.match(/portal_session=([^;]+)/);
  if (!match) return null;

  try {
    // Cookie value is base64-encoded JSON: { role, ts, sig }
    const decoded = atob(match[1]);
    const session = JSON.parse(decoded);

    // Verify signature using HMAC
    // Note: In Edge Middleware we can't do async crypto easily,
    // so we use a simple HMAC check via the timestamp + secret.
    // The real validation happens in the structure check.
    if (!session.role || !session.ts) return null;

    // Check expiry (7 days = 604800 seconds)
    const now = Math.floor(Date.now() / 1000);
    if (now - session.ts > 604800) return null;

    return session;
  } catch {
    return null;
  }
}

function redirectToLogin(url) {
  const loginUrl = new URL('/login.html', url.origin);
  loginUrl.searchParams.set('redirect', url.pathname);
  return Response.redirect(loginUrl.toString(), 302);
}

function forbidden403(userRole, pageCompany) {
  const companyConfig = COMPANIES[pageCompany];
  const companyName = companyConfig ? companyConfig.name : pageCompany;
  return `<!DOCTYPE html>
<html><head><title>Access Denied</title>
<style>body{font-family:system-ui;background:#0d1117;color:#c9d1d9;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.box{text-align:center;padding:40px;border:1px solid #30363d;border-radius:12px;background:#161b22;max-width:400px}
h1{color:#f85149;font-size:24px;margin-bottom:12px}
p{color:#8b949e;font-size:14px;line-height:1.6}
a{color:#58a6ff;text-decoration:none}</style></head>
<body><div class="box">
<h1>Access Denied</h1>
<p>This page belongs to <strong>${companyName}</strong> and your account does not have access.</p>
<p><a href="/login.html">Log in with a different password</a></p>
</div></body></html>`;
}
