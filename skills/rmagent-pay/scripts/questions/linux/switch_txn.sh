#!/bin/bash
python3 - "$ARTIFACT" "$TICKET" "$LIMIT" <<'PY'
import json, os, glob, re, sys
art, ticket, limit = sys.argv[1], sys.argv[2] if len(sys.argv)>2 else "", int(sys.argv[3] if len(sys.argv)>3 else 20)
t = re.sub(r'^(RRN|STAN)-', '', ticket or '', flags=re.I)
rows = []
def mask(pan):
    d = re.sub(r'\D', '', pan or '')
    if len(d) < 10: return None
    return d[:6] + '*'*(len(d)-10) + d[-4:]
for f in glob.glob(art)[:8] if art else []:
    try:
        with open(f, 'r', errors='replace') as fh:
            for i, line in enumerate(fh):
                if i > 4000: break
                if t and t not in line: continue
                def g(p):
                    m = re.search(p, line)
                    return m.group(1) if m else None
                stan = g(r'(?i)stan[=: ]+(\w+)')
                rrn = g(r'(?i)rrn[=: ]+(\w+)')
                rc = g(r'(?i)rc[=: ]+(\w+)')
                ts = re.search(r'(\d{4}-\d{2}-\d{2}T[\d:.]+Z?)', line)
                panm = re.search(r'\b(5\d{15,18})\b', line)
                if stan or rrn:
                    rows.append({"stan": stan, "rrn": rrn, "in_ts": ts.group(1) if ts else None,
                                 "out_ts": None, "rc": rc, "pan": mask(panm.group(1) if panm else None)})
                if len(rows) >= limit: break
    except OSError:
        pass
    if len(rows) >= limit: break
print(json.dumps({"skill": "switch_txn", "host": os.uname().nodename, "rows": rows[:limit]}, separators=(',', ':')))
PY
