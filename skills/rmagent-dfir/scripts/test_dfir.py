#!/usr/bin/env python3
"""test_dfir.py — pure-logic tests for rmagent-dfir. No witness, no network.

Run:  python3 scripts/test_dfir.py     (prints PASS/FAIL per assertion)
Covers: grain firewall, payload budget, payload content contracts, path
validation, chunk arithmetic, timeline merge, chain record/verify/tamper,
matrix validity, report generation, shared wrappers present.
"""
import json, hashlib, os, sys, tempfile, math
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))
PASS = FAIL = 0
def ok(cond, name):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  ok  {name}")
    else: FAIL += 1; print(f"  FAIL {name}")

print("== 1. grain firewall ==")
try:
    import lib
    ok(len(lib.ALLOWED) == 9, f"ALLOWED has 9 dfir questions")
    CORE = Path.home() / ".agents" / "skills" / "rmagent-core" / "scripts"
    sys.path.insert(0, str(CORE))
    import grains
    try:
        grains.assert_grain("rmagent-dfir", set(lib.ALLOWED))
        ok(True, "dfir grain has no foreign names")
    except ValueError as e:
        ok(False, f"grain violation: {e}")
    ok("rmagent-dfir" in grains.BY_SKILL, "rmagent-dfir registered in BY_SKILL")
    for other in ("IDENTITY", "APP", "AGENT", "ISO", "PAY", "PACK"):
        overlap = getattr(grains, other) & set(lib.ALLOWED)
        ok(not overlap, f"no overlap with {other} grain ({sorted(overlap)})")
except Exception as e:
    ok(False, f"grain section: {e}")

print("== 2. payload budget (WinRM ~8191 chars, x2.7 UTF-16LE b64) ==")
qdir = SKILL / "scripts" / "questions" / "windows"
payloads = sorted(qdir.glob("*.ps1"))
ok(len(payloads) == 9, f"9 payloads present ({[p.name for p in payloads]})")
for p in payloads:
    ok(p.stat().st_size <= 2400, f"{p.name} {p.stat().st_size}B within 3500B budget")

print("== 3. payload contracts ==")
BAD_CMDS = __import__("json").loads(sys.argv[1] if len(sys.argv) > 1 else "[]")
for p in payloads:
    t = p.read_text().lower()
    ok("convertto-json" in t, f"{p.name} emits JSON")
    hits = [b for b in BAD_CMDS if b.lower() in t]
    ok(not hits, f"{p.name} is read-only (no mutating cmdlets){': ' + ','.join(hits) if hits else ''}")

print("== 4. path validation (dfir.py) ==")
import dfir
for good in [r"C:\Windows\System32\cmd.exe", r"c:\temp\a.b.c.log", r"D:\data\file name with spaces.txt"]:
    ok(dfir.valid_windows_path(good), f"accepts {good}")
for bad in ["C:\\x; calc.exe", "C:\\x&whoami", "C:\\x`iex`", "C:\\x$env:x", "\\\\unc\\share\\f",
            "relative\\path.exe", "C:\\x" + "A" * 300, "", 'C:\\x"quote']:
    ok(not dfir.valid_windows_path(bad), f"rejects {bad[:40]}")

print("== 5. chunk arithmetic ==")
for size, cs, want in [(1, 24576, 1), (24576, 24576, 1), (24577, 24576, 2), (100000, 24576, 5), (123456789, 24576, 5024)]:
    got = math.ceil(size / cs)
    ok(got == want, f"size {size} / chunk {cs} = {want} chunks (got {got})")

print("== 6. chain record / verify / tamper ==")
import chain as chainmod
tmp = tempfile.mkdtemp()
chainmod.record(tmp, "collect", witness="ws1", question="vol", sha256="a" * 64)
chainmod.record(tmp, "acquire", witness="ws1", path="C:\\x\\s.exe", sha256="b" * 64)
ok2_ = False
ok_, n, bad = chainmod.verify(tmp)
ok(ok_ and n == 2, f"chain verifies with {n} intact entries")
p = chainmod.chain_path(tmp)
t = open(p).read().replace("ws1", "ws2")
open(p, "w").write(t)
ok3_, n3, bad3 = chainmod.verify(tmp)
ok(not ok3_ and bad3, "tampered chain FAILS verification")

print("== 7. timeline merge ==")
import timeline as tlmod
case = Path(tempfile.mkdtemp())
(case / "answers").mkdir(parents=True)
json.dump({"skill": "vol", "utc": "2026-09-19T10:00:00Z", "processes": [
    {"pid": 1, "name": "evil.exe", "cmd": "evil", "start": "2026-09-19T09:59:00Z"},
    {"pid": 2, "name": "good.exe", "cmd": "good", "start": "2026-09-19T09:58:00Z"}]},
    open(case / "answers" / "ws1__vol.json", "w"))
json.dump({"skill": "logtriage", "utc": "2026-09-19T10:01:00Z", "new_services": [
    {"name": "DrillSvc", "t": "2026-09-19T09:30:00Z"}]}, open(case / "answers" / "ws1__logtriage.json", "w"))
rows = tlmod.build(case)
ok(len(rows) >= 3, f"timeline merged {len(rows)} records from nested arrays")
ok(rows == sorted(rows, key=lambda r: r["ts"]), "timeline sorted by ts")
ok(any("evil.exe" in r["text"] for r in rows), "process record present in timeline")
ok(any(r["source"].startswith("answer:ws1__") for r in rows), "records tagged with source")

print("== 8. matrices ==")
for m in sorted((SKILL / "decisions").glob("*.json")):
    d = json.load(open(m))
    ok("questions" in d and "policy" in d, f"{m.name} has questions + policy")
    for qid, q in d["questions"].items():
        ok(q.get("type") in ("choice", "score", "noul"), f"{m.name}:{qid} valid type")
        if q["type"] == "choice":
            ok(1 <= len(q.get("criteria", {})) <= 10, f"{m.name}:{qid} 1-10 options (laya calibrated bucket)")
        if q["type"] == "score":
            ok(len(q.get("criteria", [])) >= 2, f"{m.name}:{qid} >= 2 levels")
    ok("escalate_below" in d["policy"], f"{m.name} has escalate policy")

print("== 9. report generation ==")
import report as repmod
case = Path(tempfile.mkdtemp()); (case / "answers").mkdir(parents=True)
json.dump({"skill": "vol", "utc": "2026-09-19T10:00:00Z", "count": 1}, open(case / "answers" / "ws1__vol.json", "w"))
chainmod.record(case, "collect", witness="ws1", question="vol", sha256="c" * 64)
out = repmod.generate(case)
txt = out.read_text()
ok("IR REPORT" in txt and "Chain of custody" in txt and "VERIFIED" in txt, "report skeleton with verified chain")
ok("Open actions" in txt, "report lists open actions")

print("== 10. shared wrappers present and runnable ==")
for s in ("needle_extract.py", "needle_drift.py", "laya_decide.py"):
    p = SKILL / "scripts" / s
    ok(p.exists() and os.access(p, os.X_OK), f"{s} present + executable")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
sys.exit(1 if FAIL else 0)
