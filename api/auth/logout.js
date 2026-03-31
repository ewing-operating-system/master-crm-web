/**
 * GET /api/auth/logout
 *
 * Clears the portal_session cookie and redirects to login page.
 */
export default function handler(req, res) {
  res.setHeader('Set-Cookie', [
    'portal_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0',
  ]);
  res.writeHead(302, { Location: '/login.html' });
  res.end();
}
