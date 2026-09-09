#!/usr/bin/env bash
# Named drop rule only — never iptables -F, never a subnet.
set -euo pipefail
ip="${TARGET:?}"
name="RMAgent-Block-${ip}"
if command -v nft >/dev/null 2>&1; then
  cmd="nft add rule inet filter input ip saddr ${ip} drop comment ${name}"
else
  cmd="iptables -I INPUT -s ${ip} -j DROP -m comment --comment ${name}"
fi
if [ "${APPLY:-0}" = "1" ]; then
  eval "$cmd"
  echo "{\"ok\":true,\"action\":\"block_ip\",\"target\":\"$ip\",\"applied\":true,\"cmd\":\"$cmd\"}"
else
  echo "{\"ok\":true,\"action\":\"block_ip\",\"target\":\"$ip\",\"would\":\"$cmd\"}"
fi
