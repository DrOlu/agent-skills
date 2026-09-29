#!/usr/bin/env bash
# Ask the chinook instance inside a Microsandbox sandbox a question.
#
# usage: ask.sh [--name chinook-ms] [--dir /opt/chinook] "question"
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
NAME="chinook-ms"; DIR="/opt/chinook"
while [ $# -gt 0 ]; do
  case "$1" in
    --name) NAME="$2"; shift 2;;
    --dir) DIR="$2"; shift 2;;
    *) Q="$1"; shift;;
  esac
done
[ -z "${Q:-}" ] && { echo "usage: ask.sh [--name SB] [--dir DIR] \"question\""; exit 1; }

msb exec "$NAME" -- sh -c "cd $DIR && python3 ask.py $DIR \"$Q\" 2>/dev/null"
