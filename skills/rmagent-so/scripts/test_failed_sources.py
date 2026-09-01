#!/usr/bin/env python3
"""test_failed_sources — Rev 16: tracked 4625 failures with a POINTER.

The hole this closes: the 95.142.115.135 brute-force hit Administrator, not
the canary, so the observatory counted failures but could not NAME the
client — block_ip had nothing to block. Now edges carries failed_sources
(distinct (src,user) collapse: count + last-seen + substatus) and correlate
turns them into ranked bruteforce_source findings with the IP attached.

Covers: the collapse itself, the cap interaction, correlate severity
scaling, triage rank, and the budget. Pure logic + payload text checks."""
import sys, base64, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib, correlate

PASS = FAIL = 0
def ok(c, l):
    global PASS, FAIL
    if c: PASS += 1; print(f"  PASS  {l}")
    else: FAIL += 1; print(f"  FAIL  {l}")

# ---- 1. the payload carries the 4625 block, collapsed ----
print("\n== 1. edges.ps1 payload ==")
src = (Path(__file__).resolve().parent / "questions/windows/edges.ps1").read_text()
ok("Id=4625" in src, "reads 4625")
ok("failed_sources" in src, "emits failed_sources")
ok("SubStatus" in src, "captures substatus (wrong-pw vs disabled vs locked)")
ok("Sort-Object n -Descending" in src, "sorted by count, worst source first")
ok("Select-Object -First $Limit" in src.split("4625")[1].split("4648")[0],
   "distinct sources capped at $Limit")
# the collapse: one entry per (src,user) key, not per event
ok("$g.ContainsKey($k)" in src, "collapses to distinct (src,user) — one row per source")
ok("TT $_" in src.split("Id=4625")[1].split("4648")[0], "failures are TRACK-filtered (not a lake)")

# ---- 2. budget ----
print("\n== 2. WinRM budget ==")
PREAMBLE = ("$ErrorActionPreference='SilentlyContinue'\n"
            "$Track = @('Administrator','SYSTEM')\n"
            "$SinceHours = 2.0\n$Limit = 50\n"
            "$CanaryList = @('honeyadmin','svcbackup2')\n")
body = []
for line in src.splitlines():
    s = line.strip()
    if not s or s.startswith("#"): continue
    body.append(line.rstrip())
enc = base64.b64encode((PREAMBLE + "\n".join(body)).encode("utf-16-le")).decode()
ok(len(enc) <= 8191, f"fits the budget ({len(enc)}/8191, {100*len(enc)//8191}%)")

# ---- 3. cap interaction: failed_sources is a critical field ----
print("\n== 3. signal-aware cap ==")
ok("failed_sources" in lib._CRITICAL_FIELDS.get("edges", []),
   "failed_sources in _CRITICAL_FIELDS — not shed as low-signal")
# an over-budget edges answer keeps the brute-force row
noisy = [{"user": f"u{i}", "src": "1.2.3.4", "t": "2026-01-01T00:00:00Z",
          "lid": f"0x{i}", "auth": "x", "type": "3"} for i in range(400)]
bf = [{"user": "Administrator", "src": "95.142.115.135", "n": 86,
       "last": "2026-01-01T01:00:00Z", "sub": "0xc000006a", "type": "3", "auth": "NTLM"}]
res = lib._cap_signal({"ok": True, "data": {"logons": noisy, "failed_sources": bf}},
                      {"id": "w"}, "edges")
kept_bf = (res.get("data") or {}).get("failed_sources") or []
ok(any(r.get("src") == "95.142.115.135" for r in kept_bf),
   f"the brute-force source row survives a heavy trim ({len(kept_bf)} kept)")

# ---- 4. correlate: bruteforce_source findings with the IP ----
print("\n== 4. correlate ==")
ROWS = [{"id": "ws1", "address": "10.0.0.1"}, {"id": "ws2", "address": "10.0.0.2"}]
answers = {
    "ws1__edges": {
        "logons": [], "explicit_creds": [], "special_privs": [], "conns": [],
        "failed_sources": [
            {"user": "Administrator", "src": "95.142.115.135", "n": 86,
             "type": "3", "auth": "NTLM", "sub": "0xc000006a", "last": "2026-01-01T01:00:00Z"},
            {"user": "Administrator", "src": "10.0.0.9", "n": 1,
             "type": "3", "auth": "NTLM", "sub": "0xc000006a", "last": "2026-01-01T02:00:00Z"},
        ],
    },
}
r = correlate.correlate(answers, ROWS)
bfs = [f for f in r["findings"] if f["kind"] == "bruteforce_source"]
ok(len(bfs) == 2, f"both distinct sources become findings ({len(bfs)})")
heavy = next((f for f in bfs if f.get("source_ip") == "95.142.115.135"), None)
light = next((f for f in bfs if f.get("source_ip") == "10.0.0.9"), None)
ok(heavy and heavy["severity"] == "critical", "86 attempts -> critical")
ok(light and light["severity"] == "info", "1 attempt (a mistyped password) -> info, not an alarm")
ok(heavy and heavy.get("hit_count") == 86, "the count is carried")
ok(heavy and "95.142.115.135" in heavy["detail"], "the IP is IN the detail — the pointer")
ok(heavy and heavy.get("triage_rank") == 1, "triaged at rank 1 (behind canary, ahead of shared-logonid)")
ok(heavy and "block_ip" in heavy.get("recommended_actions", []),
   "recommends block_ip — the actuate path now has its target")

# ---- 5. severity thresholds ----
print("\n== 5. severity scaling ==")
for n, want in [(1, "info"), (4, "info"), (5, "warning"), (19, "warning"), (20, "critical"), (86, "critical")]:
    a = {"ws1__edges": {"logons": [], "explicit_creds": [], "special_privs": [], "conns": [],
                        "failed_sources": [{"user": "Administrator", "src": "9.9.9.9", "n": n,
                                            "type": "3", "auth": "NTLM", "sub": "x", "last": "t"}]}}
    rr = correlate.correlate(a, ROWS)
    f = next((x for x in rr["findings"] if x["kind"] == "bruteforce_source"), None)
    ok(f and f["severity"] == want, f"n={n} -> {want}")

# ---- 6. no failed_sources key (old answer shape) -> no crash, no finding ----
print("\n== 6. back-compat ==")
r = correlate.correlate({"ws1__edges": {"logons": [], "explicit_creds": [], "conns": []}}, ROWS)
ok(not any(f["kind"] == "bruteforce_source" for f in r["findings"]),
   "old-shape edges answer (no failed_sources) -> no findings, no crash")
# empty list
r = correlate.correlate({"ws1__edges": {"failed_sources": []}}, ROWS)
ok(not any(f["kind"] == "bruteforce_source" for f in r["findings"]),
   "empty failed_sources -> no findings")
# n=0 rows skipped
r = correlate.correlate({"ws1__edges": {"failed_sources": [{"user": "a", "src": "1.1.1.1", "n": 0}]}}, ROWS)
ok(not any(f["kind"] == "bruteforce_source" for f in r["findings"]),
   "n=0 row skipped")

# ---- 7. triage ordering: canary still outranks bruteforce ----
print("\n== 7. triage order ==")
both = {
    "ws1__edges": {"logons": [], "explicit_creds": [], "special_privs": [], "conns": [],
                   "failed_sources": [{"user": "Administrator", "src": "9.9.9.9", "n": 50,
                                       "type": "3", "auth": "NTLM", "sub": "x", "last": "t"}]},
    "ws1__canary": {"tripped": True, "sources": ["8.8.8.8"], "hit_count": 1},
}
r = correlate.correlate(both, ROWS)
ok(r["findings"][0]["kind"] == "canary_tripped", "canary (rank 0) still outranks bruteforce (rank 1)")
ok(r["findings"][1]["kind"] == "bruteforce_source", "bruteforce second")

print(f"\n{PASS} passed, {FAIL} failed")
if FAIL:
    print("FAILURES:")
    sys.exit(1)
print("failed_sources: ALL TESTS PASSED")
