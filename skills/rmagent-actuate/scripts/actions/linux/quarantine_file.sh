#!/usr/bin/env bash
# Deny-execute on one absolute path (chmod a-x). Never rm.
set -euo pipefail
p="${TARGET:?}"
cmd="chmod a-x ${p}"
if [ "${APPLY:-0}" = "1" ]; then
  chmod a-x "$p"
  echo "{\"ok\":true,\"action\":\"quarantine_file\",\"target\":\"$p\",\"applied\":true,\"cmd\":\"$cmd\"}"
else
  echo "{\"ok\":true,\"action\":\"quarantine_file\",\"target\":\"$p\",\"would\":\"$cmd\"}"
fi
