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

# --- Rev 9: witness going audit-blind is CRITICAL ---
old9 = {"taken_utc": "2026-08-28T00:00:00Z", "admins": ["Administrator"],
        "sysmon_status": "running", "blind_count": 0, "raw_4624_24h": 120}
new9 = {"witness": "ws2", "taken_utc": "2026-08-29T00:00:00Z", "admins": ["Administrator"],
        "sysmon_status": "running", "blind_count": 3, "raw_4624_24h": 0,
        "blind_check": {"Logon": "BLIND: Failure", "Logoff": "BLIND: No Auditing",
                        "Special Logon": "BLIND: No Auditing", "Account Lockout": "ok"}}
d = drift.diff(old9, new9)
blind = [f for f in d["findings"] if f["kind"] == "witness_blind"]
assert blind and blind[0]["severity"] == "critical", d["findings"]
assert "Logon" in blind[0]["detail"] and "Logoff" in blind[0]["detail"], blind[0]["detail"]
lost = [f for f in d["findings"] if f["kind"] == "logon_visibility_lost"]
assert lost and lost[0]["severity"] == "warning", d["findings"]

# --- Rev 9: blindness improving (or unchanged) is NOT a finding ---
d = drift.diff(new9, dict(new9, blind_count=0, blind_check={"Logon": "ok"},
                          raw_4624_24h=140))
assert not any(f["kind"] in ("witness_blind", "logon_visibility_lost") for f in d["findings"]), d["findings"]

# --- Rev 9: attest payload carries blind_check fields ---
apayload = Path.home() / ".agents/skills/rmagent-windows/scripts/questions/windows/attest.ps1"
text = apayload.read_text()
for needle in ("raw_4624_24h", "blind_check", "blind_count", "auditpol"):
    assert needle in text, "attest.ps1 missing %s" % needle
# blind_check must be computed from UNFILTERED 4624 (no track filter) —
# the WS2 bug was that a track-filtered count looked fine while raw was 0.
# NOTE: the payload is compact-style ("$raw4624=@(...)" — no spaces around =),
# so the regex must tolerate both spacing forms.
import re as _re
m = _re.search(r"raw4624\s*=\s*@\(\s*Get-WinEvent.*?\)\s*\.Count", text, _re.S)
assert m and "Where-Object" not in m.group(0), "raw4624 must not be track-filtered"

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

# --- Rev 14: profile payload exists, is allowlisted, and fits the WinRM budget ---
prof = Path.home() / ".agents/skills/rmagent-windows/scripts/questions/windows/profile.ps1"
assert prof.exists(), "profile.ps1 missing"
ptext = prof.read_text()
for needle in ("cpu_pct", "mem", "disks", "proc_count", "top_cpu", "top_mem", "tracked_procs"):
    assert needle in ptext, "profile.ps1 missing %s" % needle
assert "profile" in lib.ALLOWED, "profile not allowlisted"
# budget: preamble + stripped payload must encode under ~8191 (2.67x inflation)
_p = lib._strip_payload(ptext)
_pre = lib._preamble({"id": "x", "track": ["Administrator", "SYSTEM"]}, 1.0, 10, "profile")
assert (len(_pre) + len(_p)) * 2.67 < 8191, "profile.ps1 over WinRM budget"
# read-only: must not contain any state-changing cmdlet
for bad in ("Stop-Service", "Remove-Item", "Set-Item", "Restart-Computer", "netsh ", "auditpol /set"):
    assert bad not in ptext, "profile.ps1 contains mutating command: %s" % bad

# --- Rev 14: drift — new tracked-principal process is CRITICAL ---
old14 = {"taken_utc": "2026-08-28T00:00:00Z", "admins": ["Administrator"], "sysmon_status": "running",
         "profile": {"cpu_pct": 12, "mem_used_pct": 45, "disk_used_pct_max": 60,
                     "tracked_proc_names": ["svchost", "Sysmon64"]}}
new14 = {"witness": "ws1", "taken_utc": "2026-08-29T00:00:00Z", "admins": ["Administrator"],
         "sysmon_status": "running",
         "profile": {"cpu_pct": 12, "mem_used_pct": 45, "disk_used_pct_max": 60,
                     "tracked_proc_names": ["svchost", "Sysmon64", "evilsvc"]}}
d = drift.diff(old14, new14)
ntp = [f for f in d["findings"] if f["kind"] == "new_tracked_proc"]
assert ntp and ntp[0]["severity"] == "critical", d["findings"]
assert "evilsvc" in ntp[0]["detail"], ntp[0]["detail"]

# --- Rev 14: drift — resource spike crossing 90% is a warning ---
new14b = dict(new14)
new14b["profile"] = dict(new14["profile"], cpu_pct=97, mem_used_pct=45, disk_used_pct_max=60)
d = drift.diff(old14, new14b)
spikes = [f for f in d["findings"] if f["kind"] == "resource_spike"]
assert spikes and any("CPU" in f["detail"] for f in spikes), d["findings"]
assert all(f["severity"] == "warning" for f in spikes), spikes

# --- Rev 14: drift — same profile, no findings ---
d = drift.diff(old14, dict(new14, profile=old14["profile"]))
assert not any(f["kind"] in ("new_tracked_proc", "resource_spike") for f in d["findings"]), d["findings"]

# --- Rev 14: drift — no profile in baseline (first run) is not a finding ---
d = drift.diff({"taken_utc": "x", "admins": ["Administrator"]}, new14)
assert not any(f["kind"] in ("new_tracked_proc", "resource_spike") for f in d["findings"]), d["findings"]

# --- Rev 14: drift — spike that stays UNDER 90 is not a finding ---
new14c = dict(new14)
new14c["profile"] = dict(new14["profile"], cpu_pct=75)
d = drift.diff(old14, new14c)
assert not any(f["kind"] == "resource_spike" for f in d["findings"]), d["findings"]

print("ALL UNIT TESTS PASSED")
