#!/bin/bash
# rmagent drift watchdog — cron entry.
#
# Catches drift that never reaches a commit: a change made in the LIVE skill
# that was never synced to the repo, or vice versa. The pre-commit hook only
# fires on commit; this runs on a schedule.
#
# Installs:  * * * * * is every minute; hourly is usually enough.
#   crontab -e
#   17 * * * * $HOME/.agents/skills/rmagent-windows/scripts/drift_watch.sh
#
# Writes a one-line status to ~/.rmagent/drift-watch.log (rotated at 200 lines)
# and exits non-zero on drift so a wrapper could alert on it.

LOG="$HOME/.rmagent/drift-watch.log"
mkdir -p "$HOME/.rmagent"

# rotate at 200 lines
if [ -f "$LOG" ] && [ "$(wc -l < "$LOG")" -gt 200 ]; then
  tail -100 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
fi

STAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

# 1. engine drift between the skills (sync_check.py, committed to the repo)
ENGINE_OUT="$(python3 "$HOME/.agents/skills/rmagent-windows/scripts/sync_check.py" 2>&1)"
ENGINE_RC=$?

# 2. live-vs-repo drift across all 8 skills
LIVE_OUT="$(python3 "$HOME/.agents/skills/rmagent-windows/scripts/check_repo_sync.py" 2>&1)"
LIVE_RC=$?

if [ "$ENGINE_RC" -eq 0 ] && [ "$LIVE_RC" -eq 0 ]; then
  echo "$STAMP OK engine=in-sync repo=in-sync" >> "$LOG"
  exit 0
fi

echo "$STAMP DRIFT detected:" >> "$LOG"
[ "$ENGINE_RC" -ne 0 ] && echo "$ENGINE_OUT" | grep -v '^$' | head -12 >> "$LOG"
[ "$LIVE_RC" -ne 0 ] && echo "$LIVE_OUT" | grep -v '^$$' | head -12 >> "$LOG"
echo "$STAMP end-of-drift-report" >> "$LOG"
exit 1