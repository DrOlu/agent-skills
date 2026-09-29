#!/usr/bin/env bash
# doctor.sh — environment + connectivity diagnostic for a neuralOS A2A edge.
# macOS / Linux. Prints PASS/FAIL per layer with the exact command that failed.
# Usage: bash doctor.sh            (reads parameters from the environment)
set -u

PASS=0; FAIL=0
ok()   { echo "  PASS  $*"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
warn() { echo "  WARN  $*"; }
sec()  { echo; echo "== $* =="; }

: "${NATS_URL:=}"; : "${NATS_CREDS:=}"; : "${NATS_NKEY:=}"; : "${NATS_MON:=}"
: "${GATEWAY_MESH_ID:=}"; : "${NEEDLE_ENGINE_DIR:=}"
: "${LIVEAGENT_GATEWAY_TOKEN:=}"; : "${MESH_TRUSTED_PEERS:=}"
GW="http://127.0.0.1:3000"

sec "1. Host"
ok "os: $(uname -srm)"
ok "host: $(hostname)"
if command -v python3 >/dev/null; then ok "python3: $(python3 -V 2>&1)"; else bad "python3 not found (harness needs 3.11+)"; fi
if ntp_sync=$( { command -v sntp >/dev/null && sntp -t 3 time.apple.com; } 2>/dev/null ); then
  ok "time sync reachable"
else
  warn "could not verify NTP (envelopes are refused outside a +/-5 min window)"
fi

sec "2. Engine (neuralOS / needle)"
if [ -n "$NEEDLE_ENGINE_DIR" ] && [ -d "$NEEDLE_ENGINE_DIR" ]; then
  ok "NEEDLE_ENGINE_DIR=$NEEDLE_ENGINE_DIR"
  BIN=""
  for c in needle neural needle.exe neural.exe; do
    [ -x "$NEEDLE_ENGINE_DIR/$c" ] && BIN="$NEEDLE_ENGINE_DIR/$c" && break
  done
  W=""
  for c in needle3.cact neuralOS.engine; do
    [ -f "$NEEDLE_ENGINE_DIR/$c" ] && W="$NEEDLE_ENGINE_DIR/$c" && break
  done
  [ -n "$BIN" ] && ok "engine binary: $BIN" || bad "no engine binary (needle/needle.exe or neural/neural.exe) in $NEEDLE_ENGINE_DIR"
  [ -n "$W" ]   && ok "weights: $W ($(du -h "$W" 2>/dev/null | cut -f1))" || bad "no weights (needle3.cact or neuralOS.engine) in $NEEDLE_ENGINE_DIR"
else
  bad "NEEDLE_ENGINE_DIR unset or missing (never hardcode the engine path)"
fi

sec "3. Menu + harness"
MENU_DIR="${BUTLER_MENU_DIR:-$(pwd)}"
if [ -f "${BUTLER_MENU:-$MENU_DIR/needle_menu.json}" ]; then
  M="${BUTLER_MENU:-$MENU_DIR/needle_menu.json}"
  N=$(python3 -c "import json,sys;d=json.load(open(sys.argv[1]));print(len(d if isinstance(d,list) else d.get('tools',[])))" "$M" 2>/dev/null || echo "?")
  ok "menu: $M ($N probes)"
  MISSING=$(python3 -c "
import json,sys
d=json.load(open(sys.argv[1])); t=d if isinstance(d,list) else d.get('tools',[])
print(sum(1 for p in t if not p.get('triggers')))" "$M" 2>/dev/null || echo "?")
  [ "$MISSING" = "0" ] && ok "every probe has triggers" || bad "$MISSING probe(s) missing triggers (selection will be flaky)"
else
  bad "no needle_menu.json found (set BUTLER_MENU)"
fi

sec "4. Central NATS (transport)"
if [ -z "$NATS_URL" ]; then
  bad "NATS_URL unset (ask the operator for the central endpoint)"
else
  ok "NATS_URL=$NATS_URL"
  HOSTPORT=$(echo "$NATS_URL" | sed -E 's#^[a-z]+://##; s#/.*$##')
  H=${HOSTPORT%%:*}; P=${HOSTPORT##*:}; [ "$P" = "$H" ] && P=4222
  if command -v nc >/dev/null && nc -z -w3 "$H" "$P" 2>/dev/null; then
    ok "tcp reachable $H:$P"
  else
    bad "cannot reach $H:$P (firewall/DNS?)"
  fi
  AUTH=""
  [ -n "$NATS_CREDS" ] && AUTH="--creds $NATS_CREDS"
  [ -z "$AUTH" ] && [ -n "$NATS_NKEY" ] && AUTH="--nkey $NATS_NKEY"
  if command -v nats >/dev/null; then
    if nats --server "$NATS_URL" $AUTH server check connection >/dev/null 2>&1; then
      ok "nats authenticated connection"
    else
      bad "nats connection/auth failed (check creds + account)"
    fi
  else
    warn "nats CLI not installed — skipping authenticated connect test"
  fi
  if [ -n "$NATS_MON" ]; then
    V=$(curl -s --max-time 5 "$NATS_MON/varz" | python3 -c "import json,sys;print(json.load(sys.stdin).get('version'))" 2>/dev/null)
    [ -n "$V" ] && ok "monitoring: $NATS_MON (server $V)" || warn "monitoring $NATS_MON not answering"
    E=$(curl -s --max-time 5 "$NATS_MON/jsz" | python3 -c "import json,sys;print(json.load(sys.stdin)['api']['errors'])" 2>/dev/null)
    [ "$E" = "0" ] && ok "JetStream api.errors=0" || warn "JetStream api.errors=$E (check stream/account isolation)"
  else
    warn "NATS_MON unset — cannot check JetStream/monitoring"
  fi
fi

sec "5. Gateway (trust + routing)"
if curl -s --max-time 5 "$GW/healthz" >/dev/null; then
  ok "gateway :3000 healthz"
else
  bad "gateway not answering on :3000"
fi
if [ -n "$LIVEAGENT_GATEWAY_TOKEN" ]; then
  ST=$(curl -s --max-time 5 -H "Authorization: Bearer $LIVEAGENT_GATEWAY_TOKEN" "$GW/api/mesh/status")
  if echo "$ST" | grep -q '"connected": *true'; then ok "mesh connected"; else bad "mesh not connected ($(echo "$ST" | head -c 120))"; fi
  echo "$ST" | python3 -c "import json,sys;d=json.load(sys.stdin);print('  INFO  id=',d.get('agentId'),' fp=',d.get('fingerprint'))" 2>/dev/null
else
  warn "LIVEAGENT_GATEWAY_TOKEN unset — cannot check mesh status"
fi
if [ -n "$MESH_TRUSTED_PEERS" ]; then
  ok "peer pins configured: $MESH_TRUSTED_PEERS"
else
  bad "MESH_TRUSTED_PEERS unset — invoke will be refused (3004) between edges"
fi
[ -n "$GATEWAY_MESH_ID" ] && ok "mesh id: $GATEWAY_MESH_ID" || bad "GATEWAY_MESH_ID unset"

sec "RESULT"
echo "  $PASS passed, $FAIL failed"
if [ "$FAIL" -eq 0 ]; then
  echo "  ALL GOOD — run dispatch.sh for an end-to-end proof"
  exit 0
else
  echo "  fix the FAIL lines above (see references/troubleshooting.md)"
  exit 1
fi