#!/usr/bin/env bash
# attest — alive + smoke digest for a Linux witness. Watch-only, capped.
# Engine injects: TRACK (comma list), SINCE_HOURS, LIMIT
# Emits ONE JSON object.
since_s=$(( ${SINCE_HOURS%.*} * 3600 )); [ "$since_s" -lt 60 ] && since_s=60
now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)
uptime_s=$(awk '{print int($1)}' /proc/uptime 2>/dev/null || echo 0)
load=$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || echo "?")
failed_sudo=$( (grep -h 'authentication failure' /var/log/auth.log 2>/dev/null; \
  journalctl -q --since "@$(( $(date +%s) - since_s ))" 2>/dev/null | grep -i 'authentication failure') \
  | grep -ci 'fail' )
root_logins=$( last -F -n 200 root 2>/dev/null | head -100 | wc -l )
sudoers=$( getent group sudo wheel adm 2>/dev/null | cut -d: -f4 | tr ',' '\n' | sort -u | grep -v '^$' | head -20 | tr '\n' ' ' | sed 's/ $//' )
new_users=$( find /home -maxdepth 1 -type d -newermt '-1 day' 2>/dev/null | sed 's|/home/||' | grep -v '^$' | head -5 | tr '\n' ' ' | sed 's/ $//' )
printf '{"skill":"attest","host":"%s","utc":"%s","uptime_s":%s,"load":"%s","failed_sudo_window":%s,"root_logins_recent":%s,"sudoers":"%s","new_home_dirs_24h":"%s"}\n' \
  "$host" "$now" "$uptime_s" "$load" "$failed_sudo" "$root_logins" "$sudoers" "$new_users"
