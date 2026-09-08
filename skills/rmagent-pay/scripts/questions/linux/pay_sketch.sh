#!/bin/bash
python3 - "$ARTIFACT" "$TICKET" <<'PY'
import json, os, glob, re, sys
art, ticket = sys.argv[1], sys.argv[2] if len(sys.argv)>2 else ""
t = re.sub(r'^(RRN|STAN)-', '', ticket or '', flags=re.I)
n=0; to=0; by={}
for f in glob.glob(art)[:5] if art else []:
    try:
        with open(f,'r',errors='replace') as fh:
            for i,line in enumerate(fh):
                if i>2000: break
                if t and t not in line: continue
                n+=1
                m=re.search(r'(?i)rc[=: ]+(\w+)', line)
                rc=m.group(1) if m else '?'
                by[rc]=by.get(rc,0)+1
                if rc in ('91','68'): to+=1
    except OSError:
        pass
print(json.dumps({"skill":"pay_sketch","host":os.uname().nodename,"n":n,"timeouts":to,"by_rc":by}, separators=(',',':')))
PY
