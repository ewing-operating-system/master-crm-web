#!/usr/bin/env bash
# cron_setup.sh — Install cron jobs for sync_call_intel.py
#
# Usage:
#   chmod +x cron_setup.sh
#   ./cron_setup.sh
#
# What it installs:
#   • Every 15 minutes: poll mode (Fireflies — new transcripts)
#   • Daily at 06:00:  sync mode (Salesfinity call_log full sync)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
PYTHON="$(command -v python3)"
SYNC_SCRIPT="$SCRIPT_DIR/sync_call_intel.py"
LOG_FILE="$LOG_DIR/call_sync.log"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Make the sync script executable
chmod +x "$SYNC_SCRIPT"

echo "Installing cron jobs for sync_call_intel.py..."
echo "  Script:   $SYNC_SCRIPT"
echo "  Log file: $LOG_FILE"
echo ""

# Build the cron lines
POLL_JOB="*/15 * * * * $PYTHON $SYNC_SCRIPT --mode=poll >> $LOG_FILE 2>&1"
SYNC_JOB="0 6 * * * $PYTHON $SYNC_SCRIPT --mode=sync >> $LOG_FILE 2>&1"

# Remove any existing entries for this script, then append fresh ones
(
  crontab -l 2>/dev/null | grep -v "sync_call_intel.py" || true
  echo "$POLL_JOB"
  echo "$SYNC_JOB"
) | crontab -

echo "Cron jobs installed:"
echo ""
crontab -l | grep "sync_call_intel"
echo ""
echo "Done. Logs will be written to: $LOG_FILE"
echo ""
echo "To remove these jobs run:"
echo "  crontab -l | grep -v sync_call_intel | crontab -"
