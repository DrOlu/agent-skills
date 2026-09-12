#!/usr/bin/env bash
# edges — who did this witness touch? SSH logins + sudo + root outbound conns.
# Engine injects: TRACK, SINCE_HOURS, LIMIT
since_s=$(( ${SINCE_HOURS%.*} * 3600 )); [ "$since_s" -lt 60 ] && since_s=60
L=${LIMIT:-50}
# accepted SSH logins in window (journalctl preferred, auth.log fallback)
logins=$( (journalctl -q _COMM=sshd --since "@$(( $(date +%s) - since_s ))" 2>/dev/null; \
  grep -h 'Accepted' /var/log/auth.log 2>/dev/null) \
  | grep 'Accepted' | tail -n "$L" \
  | awk '{print $1" "$2" "$3" user="$9" src="$11}' | sed 's/"/\\"/g' )
n_logins=$(echo "$logins" | grep -c 'user=' )
# sudo escalations
sudo_ev=$( (journalctl -q --since "@$(( $(date +%s) - since_s ))" 2>/dev/null; \
  grep -h 'sudo:' /var/log/auth.log 2>/dev/null) \
  | grep -E 'session opened|COMMAND=' | tail -n "$L" | sed 's/"/\\"/g' )
n_sudo=$(echo "$sudo_ev" | grep -c . )
# root-owned outbound connections (snapshot, like Windows edges)
conns=$( ss -tunp state established 2>/dev/null | awk '$1=="ESTAB" || /ESTAB/ {print}' \
  | grep -E 'users:\(\("(root|sudo)' | tail -n "$L" \
  | awk '{print $5" "$6}' | sed 's/"/\\"/g' )
n_conns=$(echo "$conns" | grep -c . )
printf '{"skill":"edges","host":"%s","utc":"%s","logons":"%s","n_logons":%s,"sudo_events":"%s","n_sudo":%s,"conns":"%s","n_conns":%s}\n' \
  "$(hostname)" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "$(echo "$logins" | tr '\n' ';')" "${n_logins:-0}" \
  "$(echo "$sudo_ev" | tr '\n' ';')" "${n_sudo:-0}" \
  "$(echo "$conns" | tr '\n' ';')" "${n_conns:-0}"
