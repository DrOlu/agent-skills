#!/usr/bin/env bash
# Kill one PID. Undo = none (honest).
set -euo pipefail
pid="${TARGET:?}"
cmd="kill -TERM ${pid}"
if [ "${APPLY:-0}" = "1" ]; then
  kill -TERM "$pid"
  echo "{\"ok\":true,\"action\":\"kill_process\",\"target\":\"$pid\",\"applied\":true,\"cmd\":\"$cmd\"}"
else
  echo "{\"ok\":true,\"action\":\"kill_process\",\"target\":\"$pid\",\"would\":\"$cmd\"}"
fi
