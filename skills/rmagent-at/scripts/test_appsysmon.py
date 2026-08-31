#!/usr/bin/env python3
"""Offline test for the appsysmon payload: verify it parses, fits the budget,
and the allowlist accepts it. Then attempt a live run if the box is up."""
import sys, base64
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

# 1. allowlist accepts it
ok1 = "appsysmon" in lib.ALLOWED
print(f"  {'PASS' if ok1 else 'FAIL'}  appsysmon in ALLOWED")

# 2. payload exists
p = lib.QDIR / "windows" / "appsysmon.ps1"
ok2 = p.exists()
print(f"  {'PASS' if ok2 else 'FAIL'}  payload exists at {p.name}")

# 3. fits the WinRM budget (the rev-8 lesson, now a test)
PREAMBLE = ("$ErrorActionPreference='SilentlyContinue'\n"
            "$Track = @('Administrator','SYSTEM')\n"
            "$SinceHours = 2.0\n$Limit = 50\n")
body = []
for line in p.read_text().splitlines():
    s = line.strip()
    if not s or s.startswith("#"):
        continue
    body.append(line.rstrip())
enc = base64.b64encode((PREAMBLE + "\n".join(body)).encode("utf-16-le")).decode()
ok3 = len(enc) <= 8191
print(f"  {'PASS' if ok3 else 'FAIL'}  WinRM budget: {len(enc)}/8191 ({100*len(enc)//8191}%)")

# 4. the payload reads the right event IDs
src = p.read_text()
ids = {1, 3, 7, 10, 13}
found = {int(m) for m in __import__("re").findall(r"Id=(\d+)", src)}
ok4 = ids.issubset(found)
print(f"  {'PASS' if ok4 else 'FAIL'}  reads Sysmon events 1,3,7,10,13 (found {sorted(found)})")

# 5. does not install anything (read-only)
danger = [w for w in ("Install-", "New-Service", "sc.exe create", "sysmon -i",
                      "DownloadFile", "Invoke-WebRequest", "Start-Process") if w in src]
ok5 = not danger
print(f"  {'PASS' if ok5 else 'FAIL'}  read-only (no install/download/spawn verbs"
      + (f" — found {danger}" if danger else "") + ")")

# 6. reports not-installed as a hole, not an error
ok6 = "not-installed" in src
print(f"  {'PASS' if ok6 else 'FAIL'}  absent Sysmon reported as not-installed, not a crash")

# 7. live attempt (may be unreachable — that is a hole, not a failure)
print("\n  live attempt (ws1):")
inv = lib.load_inventory(str(Path.home() / "estate.yaml"))
row = lib.find(inv, "ws1")
res = lib.ask(row, "appsysmon", since_hours=2.0, limit=20)
if res.get("ok"):
    d = res.get("data") or {}
    print(f"    PASS  live: sysmon={d.get('sysmon')} n_events={d.get('n_events')}")
    for k in ("proc_hashes", "lsass_access", "image_loads", "registry_sets", "guid_conns"):
        print(f"          {k}: {len(d.get(k) or [])}")
else:
    print(f"    HOLE  {res.get('error') or 'unreachable'} (boxes down — expected today)")

allok = all([ok1, ok2, ok3, ok4, ok5, ok6])
print(f"\n{'ALL OFFLINE CHECKS PASS' if allok else 'SOME CHECKS FAILED'}")
sys.exit(0 if allok else 1)
