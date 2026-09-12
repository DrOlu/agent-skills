#!/usr/bin/env bash
# explain — what changed? users/groups, cron, systemd units, packages, audit rules.
since_s=$(( ${SINCE_HOURS%.*} * 3600 )); [ "$since_s" -lt 60 ] && since_s=60
L=${LIMIT:-50}
since_iso=$(date -u -d "@$(( $(date +%s) - since_s ))" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || date -u -v-"$since_s"S '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo '')
user_changes=$( (journalctl -q --since "@$(( $(date +%s) - since_s ))" 2>/dev/null; grep -h 'useradd\|userdel\|usermod\|groupadd' /var/log/auth.log 2>/dev/null) \
  | grep -E 'useradd|userdel|usermod|groupadd' | tail -n "$L" | sed 's/"/\\"/g' | tr '\n' ';' )
new_units=$( (journalctl -q --since "@$(( $(date +%s) - since_s ))" 2>/dev/null | grep -E 'systemd-unit-file|Created new' ; find /etc/systemd/system -name '*.service' -newermt "@$(( $(date +%s) - since_s ))" 2>/dev/null) | head -n "$L" | sed 's/"/\\"/g' | tr '\n' ';' )
pkg_installs=$( (grep -h ' install ' /var/log/dpkg.log 2>/dev/null; grep -h 'Installed:' /var/log/dnf.log /var/log/yum.log 2>/dev/null) | tail -n "$L" | sed 's/"/\\"/g' | tr '\n' ';' )
audit_rules=$( (journalctl -q --since "@$(( $(date +%s) - since_s ))" 2>/dev/null | grep -i 'audit.*rule'; grep -h 'auditctl' /var/log/auth.log 2>/dev/null) | tail -n "$L" | sed 's/"/\\"/g' | tr '\n' ';' )
new_cron=$( find /etc/cron.d /var/spool/cron -newermt "@$(( $(date +%s) - since_s ))" -type f 2>/dev/null | head -n "$L" | sed 's/"/\\"/g' | tr '\n' ';' )
printf '{"skill":"explain","host":"%s","utc":"%s","since":"%s","user_changes":"%s","new_systemd_units":"%s","package_installs":"%s","audit_rule_changes":"%s","new_cron":"%s"}\n' \
  "$(hostname)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$since_iso" \
  "$user_changes" "$new_units" "$pkg_installs" "$audit_rules" "$new_cron"
