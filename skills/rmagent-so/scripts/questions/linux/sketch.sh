#!/usr/bin/env bash
# sketch — anything odd? new users, sudo-group adds, world-writable /etc, SUID changes.
since_s=$(( ${SINCE_HOURS%.*} * 3600 )); [ "$since_s" -lt 60 ] && since_s=60
L=${LIMIT:-50}
new_users=$( find /home -maxdepth 1 -type d -newermt '-1 day' 2>/dev/null | sed 's|/home/||' | grep -v '^$' | head -n "$L" | tr '\n' ' ' | sed 's/ $//' )
sudo_adds=$( (journalctl -q --since "@$(( $(date +%s) - since_s ))" 2>/dev/null; grep -h 'useradd\|gpasswd\|usermod' /var/log/auth.log 2>/dev/null) \
  | grep -E 'sudo group|wheel|useradd|usermod -aG' | tail -n "$L" | sed 's/"/\\"/g' | tr '\n' ';' )
ww_etc=$( find /etc -maxdepth 2 -perm -o+w -type f 2>/dev/null | head -n "$L" | tr '\n' ' ' | sed 's/ $//' )
suid_recent=$( find /usr /bin /sbin -perm -4000 -type f -newermt '-7 days' 2>/dev/null | head -n "$L" | tr '\n' ' ' | sed 's/ $//' )
printf '{"skill":"sketch","host":"%s","utc":"%s","new_users_24h":"%s","sudo_group_adds":"%s","world_writable_etc":"%s","suid_recent":"%s"}\n' \
  "$(hostname)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$new_users" "$sudo_adds" "$ww_etc" "$suid_recent"
