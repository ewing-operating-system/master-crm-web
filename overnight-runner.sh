#!/bin/bash
# OVERNIGHT RUNNER — Set it and forget it
# Run this from your regular terminal (NOT inside Claude Code):
#   chmod +x ~/Projects/master-crm-web/overnight-runner.sh
#   ~/Projects/master-crm-web/overnight-runner.sh
#
# This script runs Builds 1-3 and 5-8 sequentially on Sonnet.
# Each build gets its own Claude session with a pre-written prompt.
# No human input needed. Results logged to ~/Projects/master-crm-web/overnight-logs/
#
# Estimated cost: ~$3-5 total on Sonnet
# Estimated time: 2-4 hours

set -e

export CLAUDE_CODE_DISABLE_1M_CONTEXT=1
LOGDIR=~/Projects/master-crm-web/overnight-logs
mkdir -p "$LOGDIR"

echo "$(date): Starting overnight CRM buildout" | tee "$LOGDIR/runner.log"

# ============================================================
# BUILD 1: Letter Template Engine
# ============================================================
echo "$(date): Starting Build 1 — Letter Template Engine" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build1.txt)" > "$LOGDIR/build1.log" 2>&1
echo "$(date): Build 1 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# BUILD 2: Lob API Integration
# ============================================================
echo "$(date): Starting Build 2 — Lob API Integration" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build2.txt)" > "$LOGDIR/build2.log" 2>&1
echo "$(date): Build 2 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# BUILD 3: Letter Campaign Manager (250/150 Rule)
# ============================================================
echo "$(date): Starting Build 3 — Campaign Manager" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build3.txt)" > "$LOGDIR/build3.log" 2>&1
echo "$(date): Build 3 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# BUILD 5: Mobile URL Polish
# ============================================================
echo "$(date): Starting Build 5 — Mobile URL Polish" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build5.txt)" > "$LOGDIR/build5.log" 2>&1
echo "$(date): Build 5 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# BUILD 6: Auto-Regeneration Pipeline
# ============================================================
echo "$(date): Starting Build 6 — Auto-Regeneration" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build6.txt)" > "$LOGDIR/build6.log" 2>&1
echo "$(date): Build 6 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# BUILD 7: Salesfinity Integration
# ============================================================
echo "$(date): Starting Build 7 — Salesfinity Integration" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build7.txt)" > "$LOGDIR/build7.log" 2>&1
echo "$(date): Build 7 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# BUILD 8: Source Attribution
# ============================================================
echo "$(date): Starting Build 8 — Source Attribution" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build8.txt)" > "$LOGDIR/build8.log" 2>&1
echo "$(date): Build 8 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# BUILD 1.25: Company Story Template (Lovable-style)
# ============================================================
echo "$(date): Starting Build 1.25 — Company Story Template" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build1.25.txt)" > "$LOGDIR/build1.25.log" 2>&1
echo "$(date): Build 1.25 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# BUILD 1.5: Meeting Page v2 — Data Collection Engine
# ============================================================
echo "$(date): Starting Build 1.5 — Meeting Page v2" | tee -a "$LOGDIR/runner.log"
claude --model claude-sonnet-4-6 --allowedTools '*' -p "$(cat ~/Projects/master-crm-web/prompts/build1.5.txt)" > "$LOGDIR/build1.5.log" 2>&1
echo "$(date): Build 1.5 complete" | tee -a "$LOGDIR/runner.log"

# ============================================================
# DONE
# ============================================================
echo ""
echo "============================================"
echo "$(date): OVERNIGHT BUILD COMPLETE"
echo "============================================"
echo ""
echo "Logs are in: $LOGDIR/"
echo "  build1.log — Letter Template Engine"
echo "  build2.log — Lob API Integration"
echo "  build3.log — Campaign Manager (250/150)"
echo "  build5.log — Mobile URL Polish"
echo "  build6.log — Auto-Regeneration Pipeline"
echo "  build7.log — Salesfinity Integration"
echo "  build8.log — Source Attribution"
echo ""
echo "Review each log in the morning."
echo "Then run Tier 3 Sonnet tasks (S1-S5) for the OpenClaw infrastructure."
echo ""
