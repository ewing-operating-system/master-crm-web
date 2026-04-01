/**
 * Supabase Configuration — Single Source of Truth for Frontend
 *
 * All frontend JS files read from these globals instead of hardcoding keys.
 * The anon key is intentionally public (Supabase design — it is visible in
 * every browser network tab). Service role keys must NEVER appear here.
 *
 * To rotate: update this file and redeploy. All widgets pick up the change.
 */
(function() {
  window.__SUPABASE_URL = 'https://dwrnfpjcvydhmhnvyzov.supabase.co';
  window.__SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImR3cm5mcGpjdnlkaG1obnZ5em92Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzQ3NTcyOTAsImV4cCI6MjA5MDMzMzI5MH0.z0Gu1TWdGPcdptB5W7efnYMmxBbvD353ExG99ftQivY';
})();
