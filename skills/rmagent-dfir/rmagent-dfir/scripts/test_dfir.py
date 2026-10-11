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
    ok(len(lib.ALLOWED) == 15, f"ALLOWED has 15 dfir questions")
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
ok(len(payloads) == 15, f"15 payloads present ({[p.name for p in payloads]})")
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
for s in ("needle_extract.py", "needle_drift.py", "laya_decide.py", "browser_parse.py", "amcache_parse.py"):
    p = SKILL / "scripts" / s
    ok(p.exists() and os.access(p, os.X_OK), f"{s} present + executable")

print("== 11. browser_parse on a synthetic chromium DB ==")
import sqlite3, browser_parse as bp
bcase = Path(tempfile.mkdtemp())
hpath = bcase / "ws1__History"
con = sqlite3.connect(hpath)
con.execute("CREATE TABLE urls (id INTEGER PRIMARY KEY, url TEXT, title TEXT, visit_count INTEGER, last_visit_time INTEGER, hidden INTEGER)")
con.execute("CREATE TABLE downloads (id INTEGER PRIMARY KEY, target_path TEXT, start_time INTEGER, received_bytes INTEGER, total_bytes INTEGER, tab_url TEXT)")
ts = int((1765430400 + 11644473600) * 1_000_000)
con.execute("INSERT INTO urls VALUES (1, 'http://evil.example/payload', 'Evil Page', 3, ?, 0)", (ts,))
con.execute("INSERT INTO downloads VALUES (1, 'C:\\\\Users\\\\a\\\\Downloads\\\\evil.exe', ?, 999, 999, 'http://evil.example/payload')", (ts,))
con.commit(); con.close()
r = bp.parse_chromium(hpath)
ok(len(r["rows"]) == 2, f"chromium parser read {len(r['rows'])} rows (urls+downloads)")
ok(any("evil.example" in str(x.get("url", "")) for x in r["rows"]), "url row parsed")
ok(any("evil.exe" in str(x.get("download", "")) for x in r["rows"]), "download row parsed")
ok(not r["holes"], "no holes on clean DB")
ok(bp.parse_places(hpath)["holes"], "firefox parser holes gracefully on chromium DB")

print("== 12. amcache_parse on a synthetic regf hive ==")
import struct as st, amcache_parse as ap
def build_regf():
    nxt = [0x1020]
    blob = bytearray()
    def cell(b):
        total, pad = 4 + len(b), 0
        pad = (-total) % 8
        o = nxt[0]
        blob.extend(st.pack("<i", -(total + pad))); blob.extend(b); blob.extend(b"\x00" * pad)
        nxt[0] += total + pad
        return o + 4
    def nk(name, subkeys_off=0, nvalues=0, values_off=0, ts=0x01D2A1B2C3D4E5F0):
        raw = bytearray(0x4C)
        raw[0:2] = b"nk"
        st.pack_into("<H", raw, 2, 0x0020)
        st.pack_into("<Q", raw, 4, ts)
        st.pack_into("<I", raw, 0x1C, subkeys_off)
        st.pack_into("<I", raw, 0x24, nvalues)
        st.pack_into("<I", raw, 0x28, values_off)
        nm = name.encode("utf-16-le")
        st.pack_into("<H", raw, 0x48, len(nm))
        return cell(bytes(raw) + nm)
    def vk(name, dtype, data):
        raw = bytearray(0x14)
        raw[0:2] = b"vk"
        st.pack_into("<H", raw, 2, 2 * len(name))       # utf16 name
        st.pack_into("<I", raw, 8, dtype)
        st.pack_into("<H", raw, 0xC, 0)
        st.pack_into("<I", raw, 0x10, len(data))
        nm = name.encode("utf-16-le")
        return bytes(raw) + nm                           # data_off patched by caller
    BASE = 0x1020
    def patch(off, val):
        st.pack_into("<I", blob, off - BASE + 0x1C, val)  # subkeys_off @0x1C (off = record start)
    def patch_vo(off, val):
        st.pack_into("<I", blob, off - BASE + 0x28, val)  # values_off @0x28
    def patch_nv(off, val):
        st.pack_into("<I", blob, off - BASE + 0x24, val)  # nvalues @0x24
    def patch_vk_doff(vk_data_start, val):
        st.pack_into("<I", blob, vk_data_start - BASE + 4, val)  # vk data_offset @4
    # build order: parents first (offsets known), children, then patch
    root = nk("Root"); inner = nk("Root")
    fk = nk("FileOrKey"); fke = nk("0001\\abcdef")
    fblob = st.pack("<I", 0x0E) + "c:\\windows\\evil.dll".encode("utf-16-le") + b"\x00\x00"
    vk_f = cell(vk("f", 3, fblob))      # dlen must equal the true data length
    data_f = cell(fblob)
    patch_vk_doff(vk_f, data_f)
    lf_fk = cell(b"lf" + st.pack("<H", 1) + st.pack("<I", fke) + b"0001")
    patch(fk, lf_fk)
    lst_fk = cell(st.pack("<I", vk_f))
    patch_vo(fke, lst_fk); patch_nv(fke, 1)
    inv = nk("InventoryApplicationFile"); inve = nk("evilapp|c:\\x\\evil.exe|A1B2C3")
    pdata = "c:\\x\\evil.exe".encode("utf-16-le") + b"\x00\x00"
    vk_p = cell(vk("lowercaselongpath", 1, pdata))
    data_p = cell(pdata)
    patch_vk_doff(vk_p, data_p)
    lst_inv = cell(st.pack("<I", vk_p))
    patch_vo(inve, lst_inv); patch_nv(inve, 1)
    lf_inv = cell(b"lf" + st.pack("<H", 1) + st.pack("<I", inve) + b"EVIL")
    patch(inv, lf_inv)
    lf_inner = cell(b"lf" + st.pack("<H", 2) + st.pack("<I", fk) + b"FILE" + st.pack("<I", inv) + b"INVE")
    patch(inner, lf_inner)
    lf_root = cell(b"lf" + st.pack("<H", 1) + st.pack("<I", inner) + b"ROOT")
    patch(root, lf_root)
    span = 0x20 + len(blob)
    hb = bytearray(0x20); hb[0:4] = b"hbin"; st.pack_into("<I", hb, 8, span)
    hd = bytearray(0x1000); hd[0:4] = b"regf"
    st.pack_into("<I", hd, 0x24, (0x1020 + 4) - 0x1000)  # root cell data offset, bin-relative
    st.pack_into("<I", hd, 0x28, span)
    return bytes(hd + hb + blob)

rr = ap.parse(build_regf())
ok(len(rr["entries_fileorkey"]) == 1, f"FileOrKey entry found ({rr['entries_fileorkey']})")
ok(rr["entries_fileorkey"][0].get("f_version") == "0xe", "f-version decoded")
ok(any("evil.dll" in s for s in rr["entries_fileorkey"][0].get("f_strings", [])), "utf16 strings extracted from f blob")
ok(len(rr["entries_app"]) == 1, "InventoryApplicationFile entry found")
ok(rr["entries_app"][0].get("lowercaselongpath") == "c:\\x\\evil.exe", "string value read")
ok(rr["entries_fileorkey"][0].get("key_write"), "key last-write time decoded")
ok(ap.parse(b"not a hive")["holes"], "non-hive is a hole, not a crash")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
sys.exit(1 if FAIL else 0)
