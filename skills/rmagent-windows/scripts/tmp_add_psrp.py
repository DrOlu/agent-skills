#!/usr/bin/env python3
"""Add the `psrp` door to lib.ask() (Rev 19).

Design (agreed after the live comparison on WS1, 2026-09-04):
  - pywinrm stays the DEFAULT. pypsrp is opt-in per witness via the
    inventory row: `door: psrp` (or door: winrm + transport: psrp).
  - The script travels INSIDE the PSRP message body, not on a command line
    -> the 8191-char WinRM command-line budget disappears for psrp doors
    (test_budget.py stays enforced for winrm doors, informational for psrp).
  - pypsrp returns a flat list of output objects; the payload's final
    ConvertTo-Json emits ONE JSON string, so output[0] is the answer —
    same _parse/_cap_signal path as pywinrm. Verified live (edges parity).
  - Same credentials (NTLM over 5985), no witness change. Jump-host-only
    dependency (pypsrp already installed).

Edit plan:
  1. try-import pypsrp lazily at the top (optional dependency).
  2. add _ask_psrp(row, skill, script, timeout) helper.
  3. in ask(): door 'psrp' (or transport 'psrp') routes to _ask_psrp;
     everything else unchanged.
"""
import re
from pathlib import Path

LIB = Path.home() / ".agents/skills/rmagent-windows/scripts/lib.py"
t = LIB.read_text()
n0 = len(t)

# ---------- 1. lazy pypsrp import next to the winrm import ----------
old_imp = """try:
    import winrm  # pywinrm
except ImportError:
    winrm = None  # surfaced with a clear message at ask() time"""
new_imp = """try:
    import winrm  # pywinrm
except ImportError:
    winrm = None  # surfaced with a clear message at ask() time

# Rev 19: optional PSRP transport (pypsrp). Same WinRM port/creds, but the
# script travels in the SOAP body -> no 8191-char command-line budget.
try:
    from pypsrp.client import Client as _psrp_client
    from pypsrp.powershell import PowerShell as _psrp_ps, RunspacePool as _psrp_pool
    pypsrp = True
except ImportError:
    pypsrp = None  # surfaced with a clear message at ask() time"""
assert old_imp in t, "import anchor not found"
t = t.replace(old_imp, new_imp)

# ---------- 2. the psrp helper, inserted before `def ask( ----------
helper = '''
# ---------------------------------------------------------------- PSRP door (Rev 19)
def _ask_psrp(row: dict, skill: str, script: str, timeout: int) -> dict:
    """One question over PowerShell Remoting Protocol (pypsrp).

    The script goes INSIDE the message body — no command-line length limit.
    Returns the same shape as the winrm path: {ok, data?, error?, hole?}.
    pypsrp.invoke() returns a flat list of output objects; our payloads end
    with ConvertTo-Json, so output[0] is the JSON string (verified live:
    edges.ps1 parity, 2026-09-04)."""
    creds = creds_for(row)
    client = _psrp_client(row["address"], username=creds["user"],
                          password=creds["password"], ssl=False,
                          connection_timeout=timeout)
    with _psrp_pool(client.wsman) as pool:
        ps = _psrp_ps(pool)
        ps.add_script(script)
        res = ps.invoke()
    # invoke() returns output objects; errors arrive via ps.had_errors +
    # ps.stream_error — surface them like a non-zero winrm exit
    if ps.had_errors:
        err = "; ".join(str(e) for e in ps.stream_error)[:500]
        return {"ok": False, "error": err}
    out = str(res[0]) if res else ""
    return _parse(out)


'''
anchor = "# ---------------------------------------------------------------- preamble + ask"
assert anchor in t, "ask-section anchor not found"
t = t.replace(anchor, helper + anchor)

# ---------- 3. door dispatch in ask() ----------
old_door = """    door = (row.get("door") or "winrm").lower()
    if door != "winrm":
        return {"ok": False, "error": f"this skill is Windows-only; door={door}",
                "hole": hole(f"{row.get('id')} {skill}", f"door {door} not supported")}"""
new_door = """    door = (row.get("door") or "winrm").lower()
    # Rev 19: psrp is a first-class door (or an opt-in transport on winrm)
    use_psrp = door == "psrp" or (row.get("transport") or "").lower() == "psrp"
    if door not in ("winrm", "psrp") and not use_psrp:
        return {"ok": False, "error": f"this skill is Windows-only; door={door}",
                "hole": hole(f"{row.get('id')} {skill}", f"door {door} not supported")}"""
assert old_door in t, "door anchor not found"
t = t.replace(old_door, new_door)

# ---------- 4. the transport branch: run psrp instead of pywinrm ----------
old_run = """    try:
        session = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                                transport=transport)
        r = session.run_ps(script)
        out = r.std_out
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        err = r.std_err
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        if r.status_code != 0:
            mark_silent(row.get("id") or "", f"exit {r.status_code}: {(err or out)[-200:]}")
            return _cap_signal({"ok": False, "error": (err or out or "")[-500:] or f"exit {r.status_code}"}, row, skill)
        parsed = _parse(out)
        if skill == "attackmap" and parsed.get("ok") and isinstance(parsed.get("data"), dict):
            parsed["data"] = _filter_attackmap_fps(parsed["data"])
        clear_silent(row.get("id") or "")   # the witness answered — L2
        return _cap_signal(parsed, row, skill)"""
new_run = """    if use_psrp:
        if not pypsrp:
            return {"ok": False, "error": "pypsrp not installed (`pip install pypsrp`)",
                    "hole": hole(f"{row.get('id')} {skill}", "pypsrp not installed")}
        try:
            parsed = _ask_psrp(row, skill, script, timeout)
            if not parsed.get("ok"):
                mark_silent(row.get("id") or "", f"psrp: {str(parsed.get('error'))[:200]}")
                return _cap_signal(parsed, row, skill) | {
                    "hole": hole(f"{row.get('id')} {skill}", f"psrp: {str(parsed.get('error'))[:200]}")}
            if skill == "attackmap" and isinstance(parsed.get("data"), dict):
                parsed["data"] = _filter_attackmap_fps(parsed["data"])
            clear_silent(row.get("id") or "")
            return _cap_signal(parsed, row, skill)
        except Exception as e:  # noqa: BLE001 - transport failure is a hole
            msg = str(e).split("\\n")[0][:300]
            kind = "timeout" if "timed out" in msg.lower() else "unreachable"
            mark_silent(row.get("id") or "", f"psrp {kind}: {msg}")
            return _cap_signal({"ok": False, "error": msg}, row, skill) | {
                "hole": hole(f"{row.get('id')} {skill}", f"psrp {kind}: {msg}")}

    try:
        session = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                                transport=transport)
        r = session.run_ps(script)
        out = r.std_out
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        err = r.std_err
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        if r.status_code != 0:
            mark_silent(row.get("id") or "", f"exit {r.status_code}: {(err or out)[-200:]}")
            return _cap_signal({"ok": False, "error": (err or out or "")[-500:] or f"exit {r.status_code}"}, row, skill)
        parsed = _parse(out)
        if skill == "attackmap" and parsed.get("ok") and isinstance(parsed.get("data"), dict):
            parsed["data"] = _filter_attackmap_fps(parsed["data"])
        clear_silent(row.get("id") or "")   # the witness answered — L2
        return _cap_signal(parsed, row, skill)"""
assert old_run in t, "run anchor not found (check the em-dash/comment text)"
t = t.replace(old_run, new_run)

LIB.write_text(t)
print(f"patched {LIB} ({n0} -> {len(t)} chars, +{len(t)-n0})")

# syntax check
import ast
ast.parse(t)
print("AST parses OK")
