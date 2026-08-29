"""Unit test for correlate.correlate() and drift.diff() — pure logic, no I/O."""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import correlate
import drift

rows = [
    {"id": "ws1", "address": "10.0.0.1"},
    {"id": "ws2", "address": "10.0.0.2"},
]

# --- correlate: same account on both boxes (LIVE payload shape: lid, not logon_id) ---
answers = {
    "ws1__edges": {"logons": [{"user": "Administrator", "lid": "0xabc123", "type": "3", "src": "10.0.0.9"}]},
    "ws2__edges": {"logons": [{"user": "Administrator", "lid": "0xabc123", "type": "3", "src": "10.0.0.1"}]},
}
r = correlate.correlate(answers, rows)
kinds = [f["kind"] for f in r["findings"]]
assert "cross-host-account" in kinds, kinds
assert "shared-logonid" in kinds, kinds
assert r["summary"]["critical"] >= 1, r["summary"]

# --- correlate: legacy verbose shape still joins (TargetUserName/LogonId) ---
answers = {
    "ws1__edges": {"logons": [{"TargetUserName": "Administrator", "LogonId": "0xdead"}]},
    "ws2__edges": {"logons": [{"TargetUserName": "Administrator", "LogonId": "0xdead"}]},
}
r = correlate.correlate(answers, rows)
kinds = [f["kind"] for f in r["findings"]]
assert "shared-logonid" in kinds, kinds

# --- correlate: lateral hop ws1 -> ws2 (live shape: dest/port, netedges user) ---
answers = {
    "ws1__edges": {"logons": [], "conns": [{"dest": "10.0.0.2", "port": 5985, "pid": 4, "proc": "svchost"}]},
    "ws1__netedges": {"conns": [{"dest": "10.0.0.2", "port": 445, "user": "Administrator"}]},
    "ws2__edges": {"logons": []},
}
r = correlate.correlate(answers, rows)
hop = [f for f in r["findings"] if f["kind"] == "lateral-hop"]
assert len(hop) == 2, r["findings"]
assert {h["dst"] for h in hop} == {"ws2"}
assert all(h["severity"] == "critical" for h in hop)
assert any(h["dst_ip"] == "10.0.0.2" and str(h.get("detail", "")).find("445") >= 0 for h in hop), hop

# --- correlate: explicit cred targeting peer (live shape: who/became/dest) ---
answers = {
    "ws1__edges": {"logons": [], "explicit_creds": [{"who": "Admin", "became": "Administrator", "dest": "10.0.0.2"}]},
    "ws2__edges": {"logons": []},
}
r = correlate.correlate(answers, rows)
ec = [f for f in r["findings"] if f["kind"] == "explicit-cred-to-peer"]
assert ec and "Admin" in ec[0]["detail"], r["findings"]

# --- correlate: clean estate -> no findings ---
r = correlate.correlate({"ws1__edges": {"logons": []}, "ws2__edges": {"logons": []}}, rows)
assert r["summary"]["total"] == 0, r["summary"]

# --- correlate: system logon ids ignored (0x3e7) ---
answers = {
    "ws1__edges": {"logons": [{"user": "SYSTEM", "logon_id": "0x3e7"}]},
    "ws2__edges": {"logons": [{"user": "SYSTEM", "logon_id": "0x3e7"}]},
}
r = correlate.correlate(answers, rows)
assert not any(f["kind"] == "shared-logonid" for f in r["findings"]), r["findings"]

# --- drift: new admin is critical ---
old = {"taken_utc": "2026-08-28T00:00:00Z", "admins": ["Administrator"], "sysmon_status": "running", "attackmap": {"T1547.001": 1}}
new = {"witness": "ws1", "taken_utc": "2026-08-29T00:00:00Z", "admins": ["Administrator", "Backdoor"], "sysmon_status": "running", "attackmap": {"T1547.001": 1}}
d = drift.diff(old, new)
kinds = [f["kind"] for f in d["findings"]]
assert "new_admins" in kinds and "Backdoor" in str(d["findings"]), d["findings"]
assert not any(f["kind"] == "sysmon_change" for f in d["findings"])

# --- drift: sysmon change is critical ---
new2 = dict(new, sysmon_status="stopped")
d = drift.diff(old, new2)
assert any(f["kind"] == "sysmon_change" and f["severity"] == "critical" for f in d["findings"]), d["findings"]

# --- drift: persistence growth is warning ---
new3 = dict(new, attackmap={"T1547.001": 3})
d = drift.diff(old, new3)
assert any(f["kind"] == "new_persistence" and f["technique"] == "T1547.001" for f in d["findings"]), d["findings"]

# --- drift: no change -> no findings ---
d = drift.diff(old, dict(new, admins=["Administrator"]))
assert d["findings"] == [], d["findings"]

# --- attackmap allowlist: default netsh helpers suppressed, real one fires ---
import subprocess, tempfile, os
payload = Path.home() / ".agents/skills/rmagent-windows/scripts/questions/windows/attackmap.ps1"
assert payload.exists()
text = payload.read_text()
# Rev 8 filters engine-side (payload must stay under the ~8191-char WinRM budget)
assert "T1546.007" in text, "netsh technique missing from attackmap.ps1"
import lib
assert "T1546.007" in lib.FP_ALLOWLIST, "netsh allowlist missing from lib.py"
assert "dotnet" in lib.FP_ALLOWLIST["T1546.007"], "netsh helper allowlist entries missing"
assert "T1547.005" in lib.FP_ALLOWLIST, "SSP allowlist missing"
assert "kerberos" in lib.FP_ALLOWLIST["T1547.005"], "SSP defaults missing"

# allowlist actually suppresses a default, keeps a real one
sample = {"findings": [
    {"t": "T1546.007", "n": "netsh", "c": 3, "v": ["dotnet=ok", "wfpdiag=ok", "evil.dll=bad"]},
    {"t": "T1547.001", "n": "run_keys", "c": 1, "v": ["Malware=cmd"]},
], "found": 2}
filtered = lib._filter_attackmap_fps(sample)
netsh = [f for f in filtered["findings"] if f["t"] == "T1546.007"][0]
assert netsh["v"] == ["evil.dll=bad"], netsh
assert netsh["c"] == 1, netsh
assert filtered["found"] == 2, filtered  # run_keys kept
rk = [f for f in filtered["findings"] if f["t"] == "T1547.001"][0]
assert rk["v"] == ["Malware=cmd"], rk

# fully-default finding drops entirely
sample2 = {"findings": [{"t": "T1546.007", "n": "netsh", "c": 2, "v": ["dotnet=ok", "wfpdiag=ok"]}], "found": 1}
filtered2 = lib._filter_attackmap_fps(sample2)
assert filtered2["findings"] == [], filtered2
assert filtered2["found"] == 0, filtered2

print("ALL UNIT TESTS PASSED")
