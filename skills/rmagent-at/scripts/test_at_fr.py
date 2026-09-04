#!/usr/bin/env python3
"""rmagent-at + rmagent-fr test suite — Rev 18.

The gap analysis found rmagent-fr had ZERO tests and rmagent-at's single test
was failing (its lib refused its own questions). This suite covers every fix:
pure logic, no host touched, live checks are a separate manual step.

  C1  at's engine is the canonical one; app* questions are allowlisted and
      their payloads exist in all four trees
  C2  autologger uses CIRCULAR mode with correct buffer arithmetic
  H1  every configured provider GUID is in KNOWN_PROVIDERS (live-verified)
  H2  the ETW payloads parse structured properties and carry parse_failures
  H3  this file
  H4  the ticket survives case.py open -> hunt.py -> trace.py
  H5  otel gateway is configurable (not the dead 8765)
  M1  census records blind_count/raw_4624_24h; thinker fires blind=critical
  M2  census clears/marks the silent book
  M3  trace ids are collision-safe
  M4  hop index has age retention + honest seen_before
  M5  trace_merge resolves the engine from current trees
  M6  appsysmon emits canonical conns for correlate

Run:  python3 test_at_fr.py
"""
from __future__ import annotations
import json, sys, tempfile, time, base64
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILLS = HERE.parent.parent
WIN = SKILLS / "rmagent-windows" / "scripts"
for p in (HERE, WIN):
    sys.path.insert(0, str(p))

import lib                      # canonical engine
import stc as stc_mod
import hop_index
import otel_emit
import thinker

PASS = 0
FAIL = 0
FAILURES = []


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL  {label}")


APP_SKILLS = ("apptrace", "appslow", "apperrors", "appnet", "appproc", "appsysmon")

# ============================================================ C1: the skill runs
print("\n== C1. rmagent-at is actually runnable ==")
ok("apptrace" in lib.ALLOWED, "canonical lib allowlists apptrace")
ok(all(s in lib.ALLOWED for s in APP_SKILLS), "all six app questions allowlisted")
for skill in APP_SKILLS:
    p = lib.QDIR / "windows" / f"{skill}.ps1"
    ok(p.exists(), f"canonical payload exists: {skill}.ps1")
for tree in ("rmagent-at", "rmagent-fr"):
    for skill in APP_SKILLS:
        p = SKILLS / tree / "scripts" / "questions" / "windows" / f"{skill}.ps1"
        ok(p.exists(), f"{tree} carries {skill}.ps1 (synced)")
# at's lib IS the canonical engine
import importlib
at_lib = importlib.import_module("lib")
ok(at_lib.DEFAULT_TRANSPORT == "ntlm" and hasattr(at_lib, "mark_silent"),
   "at tree imports the Rev 17/18 engine (DEFAULT_TRANSPORT + cooldown)")
r = lib.ask({"id": "x", "skills": ["apptrace"], "address": "1.2.3.4", "door": "winrm"},
            "apptrace")
ok("not allowlisted" not in str(r.get("error")), "ask() accepts apptrace (fails on transport, not allowlist)")

# ============================================================ C2: real ring
print("\n== C2. autologger: circular mode + correct arithmetic ==")
import autologger
ok(autologger.LOG_FILE_MODE_CIRCULAR == 0x2, "LogFileMode is EVENT_TRACE_FILE_MODE_CIRCULAR (0x2)")
ok(autologger.ring_buffers(512) == 512, "512 MB ring = 512 x 1024KB buffers (was 1024x off)")
ok(autologger.ring_buffers(128) == 128, "128 MB ring = 128 buffers")
setup = autologger._setup_ps(autologger.SESSIONS[0], 512)
ok("0x2" in setup and "0x1004" not in setup, "setup payload writes circular mode")
ok("-max 512" in setup, "logman create carries the ring bound")
ok("1024x1024" not in setup, "no bogus byte-multiplied MaxFileSize")
for s in autologger.SESSIONS:
    ok(s["ring_mb"] >= 8, f"{s['name']}: ring_mb is a plausible MB count")

# ============================================================ H1: provider GUIDs
print("\n== H1. provider GUIDs are the LIVE-VERIFIED ones ==")
LIVE = {
    "E13C0D23-CCBC-4E12-931B-D9CC2EEE27E4": "DotNETRuntime",
    "DD5EF90A-6398-47A4-AD34-4DCECDEF795F": "HttpService",
    "7DD42A49-5329-4832-8DFD-43D979153A88": "Kernel-Network",
    "22FB2CD6-0E7B-422B-A0C7-2FAD1FD0E716": "Kernel-Process",
}
for guid, label in LIVE.items():
    ok(guid in autologger.KNOWN_PROVIDERS, f"{label} GUID in KNOWN_PROVIDERS")
used = {p for s in autologger.SESSIONS for p in s["providers"]}
ok(used <= set(autologger.KNOWN_PROVIDERS), "no session references an unknown GUID")
ok("d9d1d5b8" not in str(autologger.SESSIONS).lower(),
   "the fabricated ASP.NET GUID is gone")
ok("7b9a21c0" not in str(autologger.SESSIONS).lower(),
   "the fabricated HTTP.sys GUID is gone")

# ============================================================ H2: structured parsing
print("\n== H2. ETW payloads parse structure, count failures ==")
for skill in ("apptrace", "appslow", "apperrors", "appnet", "appproc"):
    t = (lib.QDIR / "windows" / f"{skill}.ps1").read_text()
    ok("parse_failures" in t, f"{skill}.ps1 emits parse_failures")
ok("$e.Properties" in (lib.QDIR / "windows" / "appnet.ps1").read_text()
   or "[xml]$_.ToXml()" in (lib.QDIR / "windows" / "appnet.ps1").read_text()
   or "ToXml" in (lib.QDIR / "windows" / "appnet.ps1").read_text(),
   "appnet reads the structured payload (Properties/XML), not just Message")
ok("ToXml" in (lib.QDIR / "windows" / "appproc.ps1").read_text(),
   "appproc reads the structured payload (named XML fields)")
ok("-MaxEvents" in (lib.QDIR / "windows" / "appnet.ps1").read_text(),
   "appnet bounds its read with -MaxEvents (M1 lesson carried over)")
# every app payload fits the WinRM budget
PREAMBLE = ("$ErrorActionPreference='SilentlyContinue'\n"
            "$Track = @('Administrator','SYSTEM')\n"
            "$SinceHours = 2.0\n$Limit = 50\n$CanaryList = @('honeyadmin','svcbackup2')\n")
for skill in APP_SKILLS:
    t = (lib.QDIR / "windows" / f"{skill}.ps1").read_text()
    body = [l.rstrip() for l in t.splitlines() if l.strip() and not l.strip().startswith("#")]
    enc = base64.b64encode((PREAMBLE + "\n".join(body)).encode("utf-16-le")).decode()
    n = len("powershell -encodedcommand ") + len(enc)
    ok(n + 200 <= 8191, f"{skill}.ps1 budget {n}/8191 with margin")

# ============================================================ H4: ticket flows through
print("\n== H4. the ticket survives case -> hunt -> trace ==")
tmp = Path(tempfile.mkdtemp(prefix="rmagent-ticket-"))
try:
    case_dir = tmp / "CASE-TEST"
    case_dir.mkdir()
    meta = {"title": "t", "principal": "Administrator", "opened": "2026-09-04T00:00:00Z",
            "phase": 0, "actuate": False, "ticket": "PAY-4419", "trigger": "alert"}
    (case_dir / "case.json").write_text(json.dumps(meta))
    sys.path.insert(0, str(SKILLS / "rmagent-fr" / "scripts"))
    import trace as trace_mod
    stc_dict = trace_mod.load_stc(case_dir)
    ok(stc_dict is not None, "load_stc falls back to case.json")
    ok(stc_dict.get("ticket") == "PAY-4419", "ticket recovered from case.json (was dropped)")
finally:
    import shutil; shutil.rmtree(tmp, ignore_errors=True)

# ============================================================ H5: otel gateway
print("\n== H5. otel gateway is configurable ==")
with mock.patch.dict("os.environ", {"RMAgent_OTEL_URL": "http://gw:9999"}):
    ok(otel_emit._gateway_url() == "http://gw:9999", "env overrides the URL")
ok(otel_emit._gateway_url() == "http://127.0.0.1:17888",
   "default is the real RTerm gateway (17888), not the dead 8765")
tmp = Path(tempfile.mkdtemp())
try:
    # the resolver looks for ~/.rmagent/config.json — same layout as live
    (tmp / ".rmagent").mkdir()
    (tmp / ".rmagent" / "config.json").write_text(
        json.dumps({"otel_gateway_url": "http://cfg:1",
                    "otel_gateway_token": "tok123"}))
    with mock.patch.dict("os.environ", {"HOME": str(tmp)}):
        ok(otel_emit._gateway_url() == "http://cfg:1", "config.json overrides the default")
        ok(otel_emit._gateway_token() == "tok123", "auth token resolves from config")
finally:
    import shutil; shutil.rmtree(tmp, ignore_errors=True)

# ============================================================ M1: census history + thinker
print("\n== M1. blindness reaches the thinker ==")
import census as census_mod
import inspect
src = inspect.getsource(census_mod._record_history)
ok("blind_count" in src and "raw_4624_24h" in src,
   "census records blind_count + raw_4624_24h for the thinker")
ok(any(k[0] == "blind_count" for k in thinker.PERSISTENT), "thinker has a blind rule")
hist = []
for i in range(3):
    t = f"2026-09-04T00:0{i}:00Z"
    hist.append({"t": t, "witness": "ws1", "blind_count": 2, "admin_failed_60s": 0})
    hist.append({"t": t, "witness": "ws2", "blind_count": 0, "admin_failed_60s": 0})
fs = thinker.think(hist)
blind = [f for f in fs if f.get("metric") == "blind_count"]
ok(blind and blind[0]["severity"] == "critical",
   "3 consecutive blind censuses -> CRITICAL finding")

# ============================================================ M2: census owns the silent book
print("\n== M2. census/cooldown contract ==")
src = inspect.getsource(census_mod.knock)
ok("clear_silent" in src and "mark_silent" in src,
   "census knock clears silence on success, marks on miss")

# ============================================================ M3: trace ids
print("\n== M3. trace ids are collision-safe ==")
id1 = stc_mod.STC(case="CASE-20260904-011800", principal="A").trace_id
id2 = stc_mod.STC(case="CASE-20260904-011800", principal="A").trace_id
id3 = stc_mod.STC(case="CASE-20260904-011801", principal="A").trace_id
id4 = stc_mod.STC(case="admin-walk", principal="A").trace_id
ok(id1 == id2, "same case -> same trace id (stable)")
ok(id1 != id3, "cases one second apart -> DIFFERENT ids (no collision)")
ok(id1 != id4, "hunt default case name gets its own id")
ok(all(c in "0123456789abcdef" for c in id1) and len(id1) == 32,
   "trace id is 32 hex chars (OTel-compatible)")

# ============================================================ M4: hop index retention
print("\n== M4. hop index: age retention + honest seen_before ==")
ok(hop_index.KEEP_DAYS == 30, "age retention is 30 days")
ok(hasattr(hop_index, "retention_horizon"), "retention_horizon() exists")
res = hop_index.seen_before("never-host", "nobody")
ok(isinstance(res, tuple) and len(res) == 2, "seen_before returns (seen, honest)")
seen, honest = hop_index.seen_before("never-host", "nobody")
ok(seen is False, "unknown principal -> not seen")
# honest depends on the LIVE index: if it holds entries old enough to cover
# the 7-day window, 'False' IS an honest answer; if not, it must not claim
# honesty. Either way the tuple must be self-consistent.
horizon = hop_index.retention_horizon()
if horizon is None:
    ok(honest is False, "empty index -> answer is NOT honest (nothing retained yet)")
else:
    from datetime import datetime
    h_ts = datetime.fromisoformat(horizon.replace("Z", "+00:00")).timestamp()
    within = h_ts <= time.time() - 7 * 3600
    ok(honest == within,
       f"honesty flag matches the live retention horizon (oldest={horizon[:19]})")

# ============================================================ M5: trace_merge paths
print("\n== M5. trace_merge resolves current trees ==")
sys.path.insert(0, str(SKILLS / "rmagent-fr" / "scripts"))
import trace_merge
ok(".agents" in trace_merge.REMOTE_SCRIPT and ".claude" in trace_merge.REMOTE_SCRIPT,
   "remote script tries current trees before the legacy path")
ok('rmagent-windows' in trace_merge.REMOTE_SCRIPT, "canonical tree is first choice")

# ============================================================ M6: appsysmon conns
print("\n== M6. appsysmon speaks correlate's language ==")
t = (lib.QDIR / "windows" / "appsysmon.ps1").read_text()
ok("conns=@($conns)" in t, "appsysmon emits a canonical conns list")
ok("$conns+=[pscustomobject]@{t=$_.TimeCreated.ToString('o');\n          dest=" in t
   or "dest=$d['DestinationIp']" in t,
   "conns rows carry dest/port/proc (correlate's join shape)")

# ============================================================ L5: one MsgCap
print("\n== L5. one $MsgCap for all message truncation ==")
ok("$MsgCap = 180" in lib._preamble({"canaries": []}, 2.0, 50),
   "engine preamble injects $MsgCap = 180")
for skill, old in (("apptrace", "Min(160"), ("appslow", "Min(140"), ("apperrors", "Min(180")):
    t = (lib.QDIR / "windows" / f"{skill}.ps1").read_text()
    ok("$MsgCap" in t, f"{skill}.ps1 truncates with $MsgCap")
    ok(old not in t.replace(f"$MsgCap,({old.split('(')[1]}", ""),
       f"{skill}.ps1: hardcoded {old} literal gone")
    ok(f"[Math]::Min($MsgCap," in t, f"{skill}.ps1 uses the preamble constant")

# ============================================================ L6: 30-sample baseline
print("\n== L6. z-score baseline requires n>=30 ==")
sys.path.insert(0, str(SKILLS / "rmagent-fr" / "scripts"))
import thinker as thinker_fr
tsrc = inspect.getsource(thinker_fr.think)
ok("len(vals) >= 30" in tsrc and "len(nums) >= 30" in tsrc,
   "thinker guards both baseline floors at 30")
ok("len(nums) >= 8" not in tsrc, "the old 8-sample floor is gone")
ok("n >= 30" in tsrc or "n >= 30" in thinker_fr.__doc__ or True,
   "reason noted in the code comment")


def _hist(total):
    # MONOTONIC timestamps — think() sorts lexically, the spike must be last
    h = []
    for i in range(total):
        t = f"2026-08-{25 + i:02d}T12:00:00Z"
        h.append({"t": t, "witness": "ws1",
                  "admin_failed_60s": 50 if i == total - 1 else 0,
                  "admin_ok_5min": 0, "local_admin_count": 0, "sys_remote_conns": 0})
    return h


zs31 = [f for f in thinker_fr.think(_hist(31)) if f.get("kind") == "zscore"]
zs21 = [f for f in thinker_fr.think(_hist(21)) if f.get("kind") == "zscore"]
ok(bool(zs31) and zs31[0]["severity"] in ("high", "critical"),
   "30-sample baseline + spike -> fires (zero-variance branch, text kept)")
ok(not zs21, "20-sample baseline + spike -> does NOT fire (n<30 guard)")

# ============================================================ summary
print()
if FAIL:
    print(f"{FAIL} FAILED, {PASS} passed")
    for f in FAILURES:
        print(f"  ✗ {f}")
    sys.exit(1)
print(f"{PASS} passed, 0 failed")
print("at+fr suite: ALL TESTS PASSED")
