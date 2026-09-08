#!/bin/bash
# pay_attest — Linux/AIX. Uses ARTIFACT TICKET LIMIT from preamble.
python3 - "$ARTIFACT" <<'PY'
import json, os, glob, sys
art = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("ARTIFACT", "")
out = {"skill": "pay_attest", "host": os.uname().nodename, "artifact": art,
       "exists": False, "has_stan": False, "has_rrn": False, "n_rows": 0, "oldest": None, "blind": True}
files = glob.glob(art) if art else []
if not files:
    print(json.dumps(out, separators=(",", ":")))
    raise SystemExit
out["exists"] = True
n = 0
oldest = None
for f in files[:5]:
    try:
        st = os.stat(f)
        if oldest is None:
            import datetime
            oldest = datetime.datetime.utcfromtimestamp(st.st_mtime).strftime("%Y-%m-%dT%H:%M:%SZ")
        with open(f, "r", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i > 80:
                    break
                n += 1
                low = line.lower()
                if "stan" in low or "f11" in low:
                    out["has_stan"] = True
                if "rrn" in low or "f37" in low or "retrieval" in low:
                    out["has_rrn"] = True
    except OSError:
        pass
out["n_rows"] = n
out["oldest"] = oldest
out["blind"] = not (out["has_stan"] or out["has_rrn"])
print(json.dumps(out, separators=(",", ":")))
PY
