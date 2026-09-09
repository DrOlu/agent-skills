#!/usr/bin/env bash
# Lock a local account (never delete). Undo: usermod -U.
set -euo pipefail
u="${TARGET:?}"
cmd="usermod -L ${u}"
if [ "${APPLY:-0}" = "1" ]; then
  usermod -L "$u"
  echo "{\"ok\":true,\"action\":\"disable_user\",\"target\":\"$u\",\"applied\":true,\"cmd\":\"$cmd\"}"
else
  echo "{\"ok\":true,\"action\":\"disable_user\",\"target\":\"$u\",\"would\":\"$cmd\"}"
fi
