#!/usr/bin/env python3
"""chain.py — append-only chain-of-custody for a DFIR case.

Every collection, hash, and acquisition is one JSONL entry with its own
SHA256. verify() recomputes every hash: a single edited byte in any entry
fails the chain, which by policy invalidates the case as court-ready
evidence. Entries carry who (operator), when, what (witness/question/path)
and the artifact digest — never credentials.
"""
import hashlib, json, os, sys, time
from pathlib import Path

def chain_path(case): return Path(case) / "chain.jsonl"

def record(case, kind, **kw):
    # callers may pass sha256=<artifact digest> — rename it BEFORE the
    # integrity hash is computed, or verify() can never reproduce the line.
    if "sha256" in kw:
        kw["digest_sha256"] = kw.pop("sha256")
    e = {"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "operator":
         os.environ.get("USERNAME") or os.environ.get("USER") or "jump-host",
         "kind": kind, **kw}
    line = json.dumps(e, sort_keys=True)
    e["sha256"] = hashlib.sha256(line.encode()).hexdigest()
    with open(chain_path(case), "a") as f:
        f.write(json.dumps(e, sort_keys=True) + "\n")
    return e

def entries(case):
    p = chain_path(case)
    if not p.exists(): return []
    return [json.loads(l) for l in open(p)]

def verify(case):
    bad, n = [], 0
    for e in entries(case):
        h = e.pop("sha256", None); n += 1
        if hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest() != h:
            bad.append(f"entry {n}")
    return (not bad), n, bad

if __name__ == "__main__":
    case = sys.argv[1] if len(sys.argv) > 1 else "cases/ir"
    ok, n, bad = verify(case)
    print(f"chain: {n} entries — {'VERIFIED' if ok else 'CORRUPT: ' + ', '.join(bad)}")
    sys.exit(0 if ok else 1)
