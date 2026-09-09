#!/usr/bin/env bash
# attest — alive + smoke digest + blind_check for a Linux witness. Watch-only, capped.
# Engine injects: TRACK (comma list), SINCE_HOURS, LIMIT
# Emits ONE JSON object. Empty + blind = false negative — never omit blind_check.
since_s=$(( ${SINCE_HOURS%.*} * 3600 )); [ "$since_s" -lt 60 ] && since_s=60
now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
host=$(hostname)
os=linux
if [ "$(uname -s)" = "Darwin" ]; then os=darwin; fi
# uptime
if [ -r /proc/uptime ]; then
  uptime_s=$(awk '{print int($1)}' /proc/uptime 2>/dev/null)
else
  boot=$(sysctl -n kern.boottime 2>/dev/null | sed -n 's/^ *{ *sec = \([0-9]*\).*/\1/p' | head -1)
  if [ -n "$boot" ]; then uptime_s=$(( $(date +%s) - boot )); else uptime_s=0; fi
fi
case "$uptime_s" in ''|*[!0-9]*) uptime_s=0;; esac
if [ -r /proc/loadavg ]; then
  load=$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || echo "?")
else
  load=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2, $3, $4}')
fi
[ -z "$load" ] && load="?"
failed_sudo=$( (grep -h 'authentication failure' /var/log/auth.log /var/log/secure 2>/dev/null; \
  journalctl -q --since "@$(( $(date +%s) - since_s ))" 2>/dev/null | grep -i 'authentication failure') \
  | grep -ci 'fail' )
root_logins=$( last -F -n 200 root 2>/dev/null | head -100 | wc -l | tr -d ' ' )
sudoers=$( getent group sudo wheel adm 2>/dev/null | cut -d: -f4 | tr ',' '\n' | sort -u | grep -v '^$' | head -20 | tr '\n' ' ' | sed 's/ $//' )
new_users=$( find /home -maxdepth 1 -type d -newermt '-1 day' 2>/dev/null | sed 's|/home/||' | grep -v '^$' | head -5 | tr '\n' ' ' | sed 's/ $//' )

# blind_check — can this witness see? (same standing rule as Windows attest)
# journald | auth.log | sudoers readable | ss | auditd rules | oldest auth event
j_ok=BLIND
if command -v journalctl >/dev/null 2>&1; then
  if journalctl -q -n 1 >/dev/null 2>&1; then j_ok=ok; fi
fi
auth_ok=BLIND
if [ -r /var/log/auth.log ] || [ -r /var/log/secure ] || [ -r /var/log/system.log ]; then auth_ok=ok; fi
if [ "$j_ok" = "ok" ]; then auth_ok=ok; fi
sudo_ok=BLIND
if getent group sudo wheel adm >/dev/null 2>&1; then sudo_ok=ok; fi
ss_ok=BLIND
if command -v ss >/dev/null 2>&1 && ss -H -t state established >/dev/null 2>&1; then ss_ok=ok; fi
if command -v netstat >/dev/null 2>&1 && [ "$ss_ok" != "ok" ]; then ss_ok=ok; fi
audit_ok=unknown
if [ "$os" = "darwin" ]; then
  audit_ok=macos-experimental
else
  if command -v auditctl >/dev/null 2>&1; then
    if auditctl -l >/dev/null 2>&1; then audit_ok=ok; else audit_ok=BLIND; fi
  else
    audit_ok=BLIND
  fi
fi
oldest=""
if [ "$j_ok" = "ok" ]; then
  oldest=$(journalctl -q -n 1 --output=short-iso -r 2>/dev/null | head -1 | awk '{print $1" "$2}' | sed 's/"/\\"/g')
fi

blind_count=0
for v in "$j_ok" "$auth_ok" "$sudo_ok" "$ss_ok" "$audit_ok"; do
  case "$v" in BLIND*) blind_count=$((blind_count+1));; esac
done

# macOS: do not pretend journalctl worked — hole the experimental sources
if [ "$os" = "darwin" ]; then
  j_ok=macos-experimental
fi

printf '{"skill":"attest","host":"%s","os":"%s","utc":"%s","uptime_s":%s,"load":"%s","failed_sudo_window":%s,"root_logins_recent":%s,"sudoers":"%s","new_home_dirs_24h":"%s","blind_check":{"journald":"%s","auth_log":"%s","sudoers":"%s","ss":"%s","auditd":"%s"},"blind_count":%s,"oldest_auth_event":"%s"}\n' \
  "$host" "$os" "$now" "$uptime_s" "$load" "$failed_sudo" "$root_logins" "$sudoers" "$new_users" \
  "$j_ok" "$auth_ok" "$sudo_ok" "$ss_ok" "$audit_ok" "$blind_count" "$oldest"
