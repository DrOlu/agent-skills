#!/usr/bin/env bash
# attackmap — persistence STATE check for Linux. Watch-only, capped.
# cron, systemd timers, rc files, authorized_keys mtime, ld.so.preload.
L=${LIMIT:-50}
now=$(date -u +%Y-%m-%dT%H:%M:%SZ)
cron_all=$( (for u in $(cut -d: -f1 /etc/passwd); do crontab -l -u "$u" 2>/dev/null | sed "s/^/$u: /"; done; cat /etc/crontab 2>/dev/null; ls /etc/cron.d/ 2>/dev/null | sed 's/^/cron.d:/') | head -n "$L" | sed 's/"/\\"/g' )
n_cron=$(echo "$cron_all" | grep -c .)
timers=$( systemctl list-timers --all --no-pager 2>/dev/null | head -n "$L" | sed 's/"/\\"/g' )
n_timers=$(echo "$timers" | grep -c .)
rc_recent=$( find /root /home -maxdepth 2 -name '.*rc' -o -maxdepth 2 -name '.profile' 2>/dev/null | head -n "$L" | sed 's/"/\\"/g' )
n_rc=$(echo "$rc_recent" | grep -c .)
ak_mtime=$( stat -c '%y %n' /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys 2>/dev/null | head -n "$L" | sed 's/"/\\"/g' )
n_ak=$(echo "$ak_mtime" | grep -c .)
preload=$( [ -f /etc/ld.so.preload ] && cat /etc/ld.so.preload | head -n "$L" || echo '(absent)' )
preload=$(echo "$preload" | sed 's/"/\\"/g' | tr '\n' ';')
printf '{"skill":"attackmap","host":"%s","utc":"%s","cron":"%s","n_cron":%s,"timers":"%s","n_timers":%s,"rc_files":"%s","n_rc":%s,"authorized_keys_mtime":"%s","n_ak":%s,"ld_so_preload":"%s"}\n' \
  "$(hostname)" "$now" \
  "$(echo "$cron_all" | tr '\n' ';')" "${n_cron:-0}" \
  "$(echo "$timers" | tr '\n' ';')" "${n_timers:-0}" \
  "$(echo "$rc_recent" | tr '\n' ';')" "${n_rc:-0}" \
  "$(echo "$ak_mtime" | tr '\n' ';')" "${n_ak:-0}" \
  "$preload"
