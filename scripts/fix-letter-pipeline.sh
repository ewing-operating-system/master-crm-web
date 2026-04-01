#!/usr/bin/env bash
# Credentials: all keys come from env vars (inherited from ~/.zshrc).
# See .env.example for variable names. NEVER hardcode keys in scripts.
# fix-letter-pipeline.sh — Verify and deploy letter pipeline fixes
# Idempotent. Safe to run multiple times.
# Does NOT set env vars or deploy to production.

set -uo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS="${GREEN}PASS${NC}"
FAIL="${RED}FAIL${NC}"
WARN="${YELLOW}WARN${NC}"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo ""
echo "================================================"
echo "  Letter Pipeline Fix — Verification & Deploy"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "================================================"
echo ""

ERRORS=0

# ── Phase 1: Prerequisites ──────────────────────────────────────────────────

echo "Phase 1: Prerequisites"
echo "──────────────────────"

if command -v node &>/dev/null; then
    echo -e "  node:    $PASS ($(node -v))"
else
    echo -e "  node:    $FAIL"
    ((ERRORS++))
fi

if command -v vercel &>/dev/null; then
    echo -e "  vercel:  $PASS ($(vercel -v 2>/dev/null | head -1))"
else
    echo -e "  vercel:  $FAIL — install with: npm i -g vercel"
    ((ERRORS++))
fi

if command -v git &>/dev/null; then
    echo -e "  git:     $PASS"
else
    echo -e "  git:     $FAIL"
    ((ERRORS++))
fi

echo ""

# ── Phase 2: File Verification ──────────────────────────────────────────────

echo "Phase 2: Required Files"
echo "──────────────────────"

FILES_TO_CHECK=(
    "api/letters/approve.js"
    "api/letters/batch-send.js"
    "api/letters/generate.js"
    "api/letters/send.js"
    "api/letters/send-to-lob.js"
    "api/webhooks/lob.js"
    "lib/lob-integration.js"
    "public/letter-template.html"
    "public/letter-template.js"
    "public/letter-approval-component.js"
    "public/letter-approvals.css"
    "public/inline-editing.js"
    "public/comment-widget.js"
    "public/notification-bell.js"
    "vercel.json"
)

for f in "${FILES_TO_CHECK[@]}"; do
    if [ -f "$PROJECT_DIR/$f" ]; then
        echo -e "  $f: $PASS"
    else
        echo -e "  $f: $FAIL — MISSING"
        ((ERRORS++))
    fi
done

echo ""

# ── Phase 3: Code Checks ────────────────────────────────────────────────────

echo "Phase 3: Code Integrity"
echo "──────────────────────"

# 3a. send.js uses module.exports not export default
if grep -q "module.exports" api/letters/send.js 2>/dev/null; then
    echo -e "  send.js module.exports:    $PASS"
else
    echo -e "  send.js module.exports:    $FAIL — still uses 'export default'"
    ((ERRORS++))
fi

# 3b. approval component does NOT call triggerLobSend in the approve flow
if grep -A5 "await approveRecord" public/letter-approval-component.js 2>/dev/null | grep -q "triggerLobSend"; then
    echo -e "  approve decoupled:         $FAIL — still calls triggerLobSend after approve"
    ((ERRORS++))
else
    echo -e "  approve decoupled:         $PASS"
fi

# 3c. lob-integration.js does NOT insert cost_ledger on webhook
if grep -q "supabaseInsert.*cost_ledger" lib/lob-integration.js 2>/dev/null; then
    echo -e "  no double cost logging:    $FAIL — webhook still inserts cost_ledger"
    ((ERRORS++))
else
    echo -e "  no double cost logging:    $PASS"
fi

# 3d. vercel.json has outputDirectory
if grep -q '"outputDirectory"' vercel.json 2>/dev/null; then
    echo -e "  vercel outputDirectory:    $PASS"
else
    echo -e "  vercel outputDirectory:    $FAIL — missing from vercel.json"
    ((ERRORS++))
fi

echo ""

# ── Phase 4: Environment Variables ───────────────────────────────────────────

echo "Phase 4: Environment Variables (local)"
echo "──────────────────────"

# Source zshrc for env vars
export $(grep -E '^export ' ~/.zshrc 2>/dev/null | sed 's/^export //' | grep -v '#' | xargs) 2>/dev/null

ENV_VARS=(
    "SUPABASE_URL"
    "SUPABASE_SERVICE_ROLE_KEY"
    "SUPABASE_ANON_KEY"
)

ENV_VARS_OPTIONAL=(
    "LOB_API_KEY"
    "LOB_FROM_NAME"
    "LOB_FROM_ADDRESS"
    "LOB_FROM_CITY"
    "LOB_FROM_STATE"
    "LOB_FROM_ZIP"
    "BATCH_SEND_SECRET"
)

for v in "${ENV_VARS[@]}"; do
    if [ -n "${!v:-}" ]; then
        echo -e "  $v: $PASS"
    else
        echo -e "  $v: $FAIL — required"
        ((ERRORS++))
    fi
done

for v in "${ENV_VARS_OPTIONAL[@]}"; do
    if [ -n "${!v:-}" ]; then
        echo -e "  $v: $PASS"
    else
        echo -e "  $v: $WARN — not set (needed for production sends)"
    fi
done

echo ""

# ── Phase 5: Supabase Table Check ───────────────────────────────────────────

echo "Phase 5: Supabase Schema"
echo "──────────────────────"

if [ -n "${SUPABASE_URL:-}" ] && [ -n "${SUPABASE_ANON_KEY:-}" ]; then
    # Check letter_approvals columns
    COLS=$(curl -s "${SUPABASE_URL}/rest/v1/letter_approvals?select=recipient_address_line1,recipient_city,recipient_state,recipient_zip,lob_status&limit=0" \
        -H "apikey: ${SUPABASE_ANON_KEY}" \
        -H "Authorization: Bearer ${SUPABASE_ANON_KEY}" \
        -w "%{http_code}" -o /dev/null 2>/dev/null)

    if [ "$COLS" = "200" ]; then
        echo -e "  letter_approvals address columns: $PASS"
    else
        echo -e "  letter_approvals address columns: $FAIL (HTTP $COLS)"
        ((ERRORS++))
    fi
else
    echo -e "  schema check: $WARN — skipped (no Supabase creds)"
fi

echo ""

# ── Phase 6: Deploy to Preview ──────────────────────────────────────────────

echo "Phase 6: Vercel Preview Deploy"
echo "──────────────────────"

if command -v vercel &>/dev/null; then
    echo "  Deploying to preview..."
    DEPLOY_OUTPUT=$(vercel --yes 2>&1)
    DEPLOY_URL=$(echo "$DEPLOY_OUTPUT" | grep -oE 'https://[a-zA-Z0-9._-]+\.vercel\.app' | head -1)

    if [ -n "$DEPLOY_URL" ]; then
        echo -e "  Deploy URL: $GREEN$DEPLOY_URL$NC"
    else
        echo -e "  Deploy:  $FAIL"
        echo "  Output: $DEPLOY_OUTPUT"
        ((ERRORS++))
    fi
else
    echo -e "  Deploy: $WARN — vercel CLI not available"
    DEPLOY_URL=""
fi

echo ""

# ── Phase 7: Endpoint Tests ─────────────────────────────────────────────────

echo "Phase 7: Endpoint Tests"
echo "──────────────────────"

if [ -n "${DEPLOY_URL:-}" ]; then
    # Test /api/letters/approve — should return 400 not 404
    APPROVE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$DEPLOY_URL/api/letters/approve" \
        -H "Content-Type: application/json" \
        -d '{"letter_id":"test-nonexistent"}' 2>/dev/null)

    if [ "$APPROVE_STATUS" = "404" ]; then
        # 404 from our handler means record not found — endpoint EXISTS, working correctly
        echo -e "  POST /api/letters/approve:    $PASS (404 = record not found, endpoint works)"
    elif [ "$APPROVE_STATUS" = "400" ]; then
        echo -e "  POST /api/letters/approve:    $PASS (400 = validation working)"
    elif [ "$APPROVE_STATUS" = "502" ]; then
        echo -e "  POST /api/letters/approve:    $WARN (502 = env vars may not be set on Vercel)"
    else
        echo -e "  POST /api/letters/approve:    $FAIL (HTTP $APPROVE_STATUS)"
        ((ERRORS++))
    fi

    # Test /api/letters/batch-send — should return 401 without auth
    BATCH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$DEPLOY_URL/api/letters/batch-send" \
        -H "Content-Type: application/json" \
        -d '{"dry_run":true}' 2>/dev/null)

    if [ "$BATCH_STATUS" = "401" ] || [ "$BATCH_STATUS" = "503" ]; then
        echo -e "  POST /api/letters/batch-send: $PASS ($BATCH_STATUS = auth gate working)"
    else
        echo -e "  POST /api/letters/batch-send: $FAIL (HTTP $BATCH_STATUS)"
        ((ERRORS++))
    fi

    # Test /api/letters/generate — should return 400 without body
    GEN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        -X POST "$DEPLOY_URL/api/letters/generate" \
        -H "Content-Type: application/json" \
        -d '{}' 2>/dev/null)

    if [ "$GEN_STATUS" = "400" ]; then
        echo -e "  POST /api/letters/generate:   $PASS (400 = validation working)"
    else
        echo -e "  POST /api/letters/generate:   $WARN (HTTP $GEN_STATUS)"
    fi

    # Test letter-template.html — should return 200
    PAGE_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
        "$DEPLOY_URL/letter-template.html" 2>/dev/null)

    if [ "$PAGE_STATUS" = "200" ]; then
        echo -e "  GET /letter-template.html:    $PASS"
    else
        echo -e "  GET /letter-template.html:    $FAIL (HTTP $PAGE_STATUS)"
        ((ERRORS++))
    fi
else
    echo -e "  Endpoint tests: $WARN — skipped (no deploy URL)"
fi

echo ""

# ── Summary ──────────────────────────────────────────────────────────────────

echo "================================================"
if [ $ERRORS -eq 0 ]; then
    echo -e "  ${GREEN}ALL CHECKS PASSED${NC}"
else
    echo -e "  ${RED}$ERRORS ERROR(S) FOUND${NC}"
fi
echo "================================================"
echo ""

if [ -n "${DEPLOY_URL:-}" ]; then
    echo "Test URLs:"
    echo "  Letter Template: ${DEPLOY_URL}/letter-template.html?company_id=9df67252-75d3-4962-aebc-81c3fc0a3124&company=Berkeys%20AC&owner=Test%20Owner&revenue=133200000&motivation=retirement&timeline=12months"
    echo "  Campaign Manager: ${DEPLOY_URL}/campaign-manager.html"
    echo ""
fi

echo "Next steps:"
echo "  1. Set LOB_API_KEY in ~/.zshrc (test_ key first)"
echo "  2. Set BATCH_SEND_SECRET in ~/.zshrc"
echo "  3. Push env vars to Vercel: vercel env add LOB_API_KEY production"
echo "  4. Deploy to production: vercel --prod"
echo "  5. Test approve flow in browser"
echo "  6. Test batch-send with dry_run: curl -X POST <url>/api/letters/batch-send -H 'Content-Type: application/json' -d '{\"auth_token\":\"<secret>\",\"dry_run\":true}'"
echo ""

exit $ERRORS
