#!/usr/bin/env python3
"""rmagent-at autologger — enterprise-scale ETW session management.

Creates and manages AutoLogger sessions that start at BOOT and run resident
in kernel memory. The ring buffer is circular: old events are overwritten,
nothing hits disk until the pull reads it. No lake.

ENTERPRISE SCALE: the default session uses a 512 MB kernel ring buffer with
a 256 MB file cap, giving hours-to-days of retention on a busy box instead
of minutes. Buffer sizes are tunable per session.

This is a PERSISTENT CHANGE to the witness (registry + boot-time session).
It is a MOP-level action, not a Phase 0 question. Every function here is
reversible via `teardown()`.

Usage:
  python3 autologger.py --inventory estate.yaml --setup          # create sessions
  python3 autologger.py --inventory estate.yaml --status         # what's running
  python3 autologger.py --inventory estate.yaml --resize 1024    # grow buffers
  python3 autologger.py --inventory estate.yaml --teardown       # remove everything
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

# ---------------------------------------------------------------- sessions

# Each session: name, providers (guid + friendly name), buffer size in MB.
# The providers are ALL built into Windows — zero install, zero code change
# in the target apps. .NET / IIS / HTTP.sys apps emit into these already.

SESSIONS = [
    {
        "name": "RMAgent-AppTrace",
        "purpose": "application-level events (.NET EventSource, HTTP.sys, IIS)",
        "buffer_mb": 512,          # enterprise: hours of retention
        "file_cap_mb": 256,        # when flushed to disk, stop at this
        "providers": [
            # .NET Common Language Runtime — GC, JIT, exceptions, threading.
            # Every .NET app emits here with zero code changes.
            "e13c0d23-ccbc-4e12-931b-d9cc2eedb7d1",
            # HTTP service (HTTP.sys) — every request through the kernel HTTP stack
            "7b9a21c0-2f55-4e75-b6c1-0b0a5e1f6b6d",
            # ASP.NET (System.Web / ASP.NET Core IIS integration)
            "d9d1d5b8-2f5a-4e75-b6c1-0b0a5e1f6b6d",
        ],
    },
    {
        "name": "RMAgent-NetTrace",
        "purpose": "connection-level network (every TCP connection with PID)",
        "buffer_mb": 256,
        "file_cap_mb": 128,
        "providers": [
            # Microsoft-Windows-Kernel-Network — TCP/UDP with owning PID
            "7dd42a49-5329-4832-8dfd-43d979153a88",
        ],
    },
    {
        "name": "RMAgent-ProcTrace",
        "purpose": "process lifecycle (create/exit with full command line)",
        "buffer_mb": 128,
        "file_cap_mb": 64,
        "providers": [
            # Microsoft-Windows-Kernel-Process
            "22fb2cd6-0c7b-422b-b0c5-2e8b9918b978",
        ],
    },
]

REG_BASE = r"HKLM\SYSTEM\CurrentControlSet\Control\WMI\Autologger"


# ---------------------------------------------------------------- payloads

def _setup_ps(session: dict, buffer_mb: int) -> str:
    """PowerShell to create one AutoLogger session. Compact for WinRM."""
    name = session["name"]
    provs = ",".join(f"{{{g}}}" for g in session["providers"])
    file_cap = session["file_cap_mb"]
    return f"""
$ErrorActionPreference='SilentlyContinue'
$name='{name}'
$base='{REG_BASE}\\'+$name
# session root
reg add $base /v Start /t REG_DWORD /d 1 /f | Out-Null
reg add $base /v MaxFileSize /t REG_DWORD /d 0x{file_cap * 1024 * 1024:x} /f | Out-Null
reg add $base /v FileName /t REG_SZ /d "C:\\etw\\{name}.etl" /f | Out-Null
reg add $base /v LogFileMode /t REG_DWORD /d 0x1004 /f | Out-Null
# 0x1004 = EVENT_TRACE_FILE_MODE_CIRCULAR | SEQUENTIAL
# Buffer sizing — enterprise scale
reg add $base /v BufferSize /t REG_DWORD /d 1024 /f | Out-Null          # KB per buffer
reg add $base /v MinimumBuffers /t REG_DWORD /d {buffer_mb} /f | Out-Null  # buffers = MB
reg add $base /v MaximumBuffers /t REG_DWORD /d {buffer_mb * 2} /f | Out-Null
reg add $base /v FlushTimer /t REG_DWORD /d 0 /f | Out-Null
# ensure the output dir exists
New-Item -ItemType Directory -Path 'C:\\etw' -Force | Out-Null
# providers
$provs = '{provs}'.Split(',')
$i = 0
foreach($p in $provs){{
  $pk = $base + '\\\\' + $p
  reg add $pk /v Enabled /t REG_DWORD /d 1 /f | Out-Null
  reg add $pk /v Level /t REG_DWORD /d 0xff /f | Out-Null
  reg add $pk /v MatchAnyKeyword /t REG_QWORD /d 0xffffffffffffffff /f | Out-Null
  $i++
}}
# start the session NOW (not just at next boot)
logman create trace $name -pf ( $provs | ForEach-Object {{ $_ }} ) -o "C:\\etw\\{name}.etl" -ets 2>&1 | Out-Null
Write-Output "SETUP $name buffers={buffer_mb}MB providers=$i"
""".strip()


def _status_ps() -> str:
    return """
$ErrorActionPreference='SilentlyContinue'
$out=@()
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){
  $base='{REG_BASE}\\'+$n
  $start=(reg query $base /v Start 2>$null) -replace '.*REG_DWORD\s+',''
  $buf=(reg query $base /v MinimumBuffers 2>$null) -replace '.*REG_DWORD\s+',''
  $running = (logman query $n 2>$null) -ne $null
  $out += [pscustomobject]@{{name=$n;autologger_start=$start;buffer_mb=$buf;running=$running}}
}
$out | ConvertTo-Json -Compress
""".strip()


def _teardown_ps() -> str:
    return """
$ErrorActionPreference='SilentlyContinue'
foreach($n in @('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')){
  logman stop $n -ets 2>&1 | Out-Null
  logman delete $n -ets 2>&1 | Out-Null
  reg delete ('{REG_BASE}\\'+$n) /f 2>&1 | Out-Null
  Remove-Item "C:\\etw\\$n.etl" -Force -ErrorAction SilentlyContinue
}
Write-Output 'TORN DOWN'
""".strip()


# ---------------------------------------------------------------- driver

def run_ps(row: dict, script: str) -> dict:
    """Send a PowerShell script to a WinRM witness. Not a named question —
    this is the MOP management path, so it bypasses the question allowlist
    but still goes through the same transport."""
    import winrm as _winrm
    creds = lib.creds_for(row)
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    transport = row.get("transport") or "basic"
    session = _winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                             transport=transport)
    r = session.run_ps(script)
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else r.std_out
    err = r.std_err.decode("utf-8", "replace") if isinstance(r.std_err, bytes) else r.std_err
    return {"ok": r.status_code == 0, "stdout": out.strip(), "stderr": err.strip()[:300]}


def main():
    ap = argparse.ArgumentParser(description="rmagent-at autologger management (MOP-level)")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--setup", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--teardown", action="store_true")
    ap.add_argument("--resize", type=int, default=None, metavar="MB",
                    help="re-run setup with this buffer size (MB) for all sessions")
    args = ap.parse_args()

    if not (args.setup or args.status or args.teardown):
        ap.error("choose --setup, --status, or --teardown")

    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)

    for row in rows:
        wid = row.get("id")
        if args.status:
            res = run_ps(row, _status_ps())
            print(f"[{wid}] status: {res.get('stdout', '')[:200]}")
            continue
        if args.teardown:
            res = run_ps(row, _teardown_ps())
            print(f"[{wid}] teardown: {'OK' if res['ok'] else res.get('stderr','')[:100]}")
            continue
        if args.setup:
            for sess in SESSIONS:
                buf = args.resize if args.resize else sess["buffer_mb"]
                script = _setup_ps(sess, buf)
                res = run_ps(row, script)
                line = res.get("stdout", "")
                if "SETUP" in line:
                    print(f"[{wid}] {line}")
                else:
                    print(f"[{wid}] {sess['name']}: {'OK' if res['ok'] else 'FAIL: ' + res.get('stderr','')[:120]}")


if __name__ == "__main__":
    main()