#!/usr/bin/env python3
"""apply_psrp_msgcap — re-apply the two post-commit lib.py deltas:
Rev 18.1 PSRP door (pypsrp runspace pools, cached, one rebuild retry)
Rev 18 (L5) $MsgCap in the preamble."""
import ast
from pathlib import Path

p = Path("/Users/olu/.agents/skills/rmagent-windows/scripts/lib.py")
t = p.read_text()

# ---------- 1. PSRP import block + pool helper (insert before SKILL_DIR) ----------
if "_psrp_pool" not in t:
    anchor = "SKILL_DIR = Path(__file__).resolve().parents[1]"
    psrp_block = '''# ---------------------------------------------------------------- PSRP door (Rev 18.1)
# pypsrp is OPTIONAL: import lazily, degrade to the winrm door when absent.
# The inventory opts in per witness with `door: psrp`.
try:
    from pypsrp.client import Client as _PsrpClient
    from pypsrp.powershell import PowerShell as _PsrpPowerShell, RunspacePool as _PsrpPool
    PSRP = True
except ImportError:
    PSRP = False

# one RunspacePool per (host, user) - reused across asks in a process so a
# hunt/census amortizes pool setup instead of paying it per question
_PSRP_POOLS: dict[tuple, tuple] = {}


def _psrp_available() -> bool:
    return bool(PSRP)


def _psrp_pool(ws1_address: str | None, creds: dict):
    """Return (pool, run_script) for a cached PSRP runspace pool.

    run_script(script) -> list of output objects. The pool is created on
    first use and reused; a dead pool (host rebooted, WinRM restarted) is
    detected on invoke and rebuilt once."""
    key = (ws1_address or "", creds["user"])
    entry = _PSRP_POOLS.get(key)

    def _make():
        client = _PsrpClient(ws1_address, username=creds["user"],
                             password=creds["password"], ssl=False)
        pool = _PsrpPool(client.wsman)
        pool.open()
        return pool

    if entry is None:
        pool = _make()
        _PSRP_POOLS[key] = (pool, 0)
    else:
        pool, _uses = entry

    def run_script(script: str):
        nonlocal pool
        ps = _PsrpPowerShell(pool)
        ps.add_script(script)
        try:
            return ps.invoke()
        except Exception:
            # the pool may have gone stale (reboot / WinRM restart) - rebuild ONCE
            try:
                pool.close()
            except Exception:
                pass
            pool = _make()
            _PSRP_POOLS[key] = (pool, 0)
            ps2 = _PsrpPowerShell(pool)
            ps2.add_script(script)
            return ps2.invoke()

    _PSRP_POOLS[key] = (pool, 0)
    return pool, run_script


''' + anchor
    t = t.replace(anchor, psrp_block, 1)
    print("PSRP block inserted")

# ---------- 2. door routing: accept psrp ----------
old_door = '''    door = (row.get("door") or "winrm").lower()
    if door not in ("winrm",):'''
new_door = '''    door = (row.get("door") or "winrm").lower()
    if door not in ("winrm", "psrp"):'''
if new_door not in t:
    assert old_door in t, "door anchor missing"
    t = t.replace(old_door, new_door, 1)
    print("door routing accepts psrp")
elif "psrp" in t.split('door not in')[1][:40]:
    print("door routing already accepts psrp")

# ---------- 3. the psrp branch in ask() ----------
if "PSRP door" not in t or "_psrp_pool(ws1_address" not in t:
    anchor2 = '''    script = _preamble(row, since_hours, limit, skill) + _strip_payload(payload.read_text())
    timeout = _clamp_timeout(skill, timeout)
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    transport = row.get("transport") or "basic"
'''
    psrp_branch = anchor2 + '''
    # ---------------------------------------------------------------- PSRP door
    # Rev 18.1: door=psrp routes through pypsrp's RunspacePool. The script
    # travels INSIDE the WS-Management SOAP body, so the 8191-char command-line
    # budget (pywinrm's encodedcommand wrapper) does not apply - measured live
    # on WS1: a 40,799-char payload that pywinrm refuses with
    # ERROR_FILENAME_EXCED_RANGE returns all 1200 lines in 4.33s, and the real
    # edges.ps1 question returns identical JSON through both doors. Pools are
    # cached per (witness,user) so one pool amortizes across a hunt's
    # questions. Everything downstream (parse, cap, holes, cooldown) is
    # door-agnostic.
    if door == "psrp":
        try:
            _pool, run_script = _psrp_pool(ws1_address=row.get("address"), creds=creds)
            result = run_script(script)   # flat list of output objects
            out = "\\n".join(str(o) for o in result) if result else ""
            parsed = _parse(out)
            if skill == "attackmap" and parsed.get("ok") and isinstance(parsed.get("data"), dict):
                parsed["data"] = _filter_attackmap_fps(parsed["data"])
            clear_silent(row.get("id") or "")
            return _cap_signal(parsed, row, skill)
        except Exception as e:  # noqa: BLE001 - transport failure is a hole, not a crash
            msg = str(e).split("\\n")[0][:300]
            kind = "timeout" if "timed out" in msg.lower() else "unreachable"
            mark_silent(row.get("id") or "", f"psrp {kind}: {msg}")
            return _cap_signal({"ok": False, "error": msg}, row, skill) | {
                "hole": hole(f"{row.get('id')} {skill}", f"psrp {kind}: {msg}")
            }
'''
    assert anchor2 in t, "ask() anchor missing"
    t = t.replace(anchor2, psrp_branch, 1)
    print("psrp branch inserted into ask()")

# ---------- 4. MsgCap in the preamble ----------
if "$MsgCap" not in t:
    old_c = '''    c_items = "','".join(str(c).replace("'", "''") for c in canaries if c)
    out += f"$CanaryList = @('{c_items}')\\n"
    return out'''
    new_c = '''    c_items = "','".join(str(c).replace("'", "''") for c in canaries if c)
    out += f"$CanaryList = @('{c_items}')\\n"
    # Rev 18 (L5): ONE truncation cap for every message field across all
    # payloads (the app questions used 160/140/180 for the same field).
    out += "$MsgCap = 180\\n"
    return out'''
    assert old_c in t, "canary preamble anchor missing"
    t = t.replace(old_c, new_c, 1)
    print("$MsgCap added to the preamble")

ast.parse(t)
p.write_text(t)
print("lib.py: PSRP door + MsgCap applied, AST OK")
