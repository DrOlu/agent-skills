#!/usr/bin/env python3
"""One live pypsrp test on WS1 with a TEMPORARY row override (door: psrp).
Confirms edges parity with pywinrm. estate.yaml is NOT modified."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

INV = lib.load_inventory(str(Path.home() / "estate.yaml"))
ws1 = dict([r for r in lib.witnesses(INV) if r["id"] == "ws1"][0])
ws1["skills"] = list(set(ws1.get("skills") or []) | {"edges"})

results = {}
for door in ("winrm", "psrp"):
    row = dict(ws1)
    row["door"] = door
    row["transport"] = "ntlm" if door == "winrm" else "psrp"
    r = lib.ask(row, "edges", since_hours=2.0, limit=20)
    d = r.get("data") or {}
    results[door] = d
    print(f"[{door}] edges ok={r.get('ok')} logons={len(d.get('logons') or [])} "
          f"failed={len(d.get('failed_sources') or [])} "
          f"explicit={len(d.get('explicit_creds') or [])} conns={len(d.get('conns') or [])}")

w, p = results.get("winrm", {}), results.get("psrp", {})
keys = ("logons", "failed_sources", "explicit_creds", "conns")
parity = all(len(w.get(k) or []) == len(p.get(k) or []) for k in keys)
print(f"\nEDGES PARITY (winrm vs psrp): {'YES' if parity else 'NO'}")
print(f"transport used: inventory untouched -> {Path.home() / 'estate.yaml'} still ntlm")
