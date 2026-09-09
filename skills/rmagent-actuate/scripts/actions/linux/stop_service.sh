#!/usr/bin/env bash
# Stop + disable a systemd unit. Not mask. Undo: enable --now.
set -euo pipefail
u="${TARGET:?}"
cmd="systemctl stop ${u} && systemctl disable ${u}"
if [ "${APPLY:-0}" = "1" ]; then
  systemctl stop "$u"
  systemctl disable "$u"
  echo "{\"ok\":true,\"action\":\"stop_service\",\"target\":\"$u\",\"applied\":true,\"cmd\":\"$cmd\"}"
else
  echo "{\"ok\":true,\"action\":\"stop_service\",\"target\":\"$u\",\"would\":\"$cmd\"}"
fi
