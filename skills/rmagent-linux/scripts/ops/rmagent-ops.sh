#!/usr/bin/env bash
# rmagent enterprise bash-native kit — witness health checks over SSH without Python.
# For enterprises where the jump host may not run Python: pure bash + ssh.
#
# Usage:
#   rmagent-ops.sh status  <host> [user]        # one witness: alive/load/auth-fails/blind_check
#   rmagent-ops.sh status  <inventory.txt>      # file of "host [user]" lines: fleet sweep
#   rmagent-ops.sh watch   <host> [user]        # one JSON line; exit 1 if BLIND/unreachable
#   rmagent-ops.sh sweep   <inventory.txt>      # watch across a fleet, TSV summary
#
# Inventory format (one per line):  host[:port] [user]   (# comments allowed)
# Auth: your existing SSH config/keys. No agents, no installs on the witness.
# Every probe is read-only. Cap: one round-trip per witness per invocation.
# Remote side needs only POSIX sh + coreutils — NO python, NO jq on the witness.

set -u
PROG=$(basename "$0")

die() { printf '{"error":"%s"}\n' "$1" >&2; exit 2; }

# ---- the remote probe body (piped over ssh; runs under sh on the witness) ----
probe_body() {
  cat <<'REMOTE'
since_s=$(( ${SINCE_HOURS:-2} * 3600 )); [ "$since_s" -lt 60 ] && since_s=60
now=$(date -u +%Y-%m-%dT%H:%M:%SZ); host=$(hostname)
os=linux; [ "$(uname -s)" = "Darwin" ] && os=darwin
if [ -r /proc/uptime ]; then uptime_s=$(awk '{print int($1)}' /proc/uptime 2>/dev/null); else
  boot=$(sysctl -n kern.boottime 2>/dev/null | sed -n 's/^ *{ *sec = \([0-9]*\).*/\1/p' | head -1)
  uptime_s=$(( $(date +%s) - ${boot:-$(date +%s)} )); fi
case "$uptime_s" in ''|*[!0-9]*) uptime_s=0;; esac
if [ -r /proc/loadavg ]; then load=$(cut -d" " -f1-3 /proc/loadavg); else
  load=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2, $3, $4}'); fi
[ -z "${load:-}" ] && load="?"
fails=$( (grep -h "authentication failure" /var/log/auth.log /var/log/secure 2>/dev/null; \
  journalctl -q --since "@$(( $(date +%s) - since_s ))" 2>/dev/null | grep -i "authentication failure") \
  | grep -c . )
sudoers=$(getent group sudo wheel adm 2>/dev/null | cut -d: -f4 | tr "," "\n" | sort -u | grep -c .)
printf '{"skill":"bash-attest","host":"%s","utc":"%s","os":"%s","uptime_s":%s,"load":"%s","failed_logons":%s,"sudo_accounts":%s,"blind_check":"ok"}\n' \
  "$host" "$now" "$os" "$uptime_s" "$load" "${fails:-0}" "${sudoers:-0}"
REMOTE
}

probe_one() {
  t=$1; h=${t%%:*}; p=${t##*:}; [ "$p" = "$t" ] && p=22
  u=${2:-$USER}
  SINCE_HOURS=${SINCE_HOURS:-2} timeout 25 ssh -p "$p" -o BatchMode=yes -o ConnectTimeout=8 \
    -o StrictHostKeyChecking=accept-new "$u@$h" 'sh -s' <<EOF 2>/dev/null
SINCE_HOURS=${SINCE_HOURS:-2}
$(probe_body)
EOF
}

cmd=${1:-}
case "$cmd" in status|watch|sweep) ;; *) echo "usage: $PROG status|watch|sweep <host|inventory> [user]" >&2; exit 2;; esac
target=${2:-}; [ -n "$target" ] || die "target required"

case "$cmd" in
  status)
    if [ -f "$target" ]; then
      grep -v '^#' "$target" | while read -r h u; do
        [ -n "${h:-}" ] || continue
        echo "== $h =="
        probe_one "$h" "$u"
      done
    else
      probe_one "$target" "${3:-}"
    fi
    ;;
  watch)
    out=$(probe_one "$target" "${3:-}")
    echo "$out"
    echo "$out" | grep -q '"blind_check":"ok"' || exit 1
    ;;
  sweep)
    [ -f "$target" ] || die "sweep needs an inventory file"
    printf 'host\tos\tuptime_h\tfailed_logons\tsudoers\tblind\n'
    grep -v '^#' "$target" | while read -r h u; do
      [ -n "${h:-}" ] || continue
      line=$(probe_one "$h" "$u")
      if [ -z "$line" ]; then printf '%s\t-\t-\t-\t-\tUNREACHABLE\n' "$h"; continue; fi
      host=$(printf '%s' "$line" | sed -n 's/.*"host":"\([^"]*\)".*/\1/p')
      os=$(printf '%s' "$line" | sed -n 's/.*"os":"\([^"]*\)".*/\1/p')
      up=$(printf '%s' "$line" | sed -n 's/.*"uptime_s":\([0-9]*\).*/\1/p')
      fl=$(printf '%s' "$line" | sed -n 's/.*"failed_logons":\([0-9]*\).*/\1/p')
      su=$(printf '%s' "$line" | sed -n 's/.*"sudo_accounts":\([0-9]*\).*/\1/p')
      uph=$(( ${up:-0} / 3600 ))
      printf '%s\t%s\t%s\t%s\t%s\tok\n' "${host:-$h}" "$os" "$uph" "$fl" "$su"
    done
    ;;
esac
