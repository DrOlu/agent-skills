"""Re-apply the Rev 18 M1/M2 census edits to BOTH trees (windows canonical
+ fr), file-based (heredocs keep getting mangled)."""
from pathlib import Path

for root in (Path.home() / ".agents/skills/rmagent-windows/scripts",
             Path.home() / ".agents/skills/rmagent-fr/scripts"):
    c = root / "census.py"
    t = c.read_text()
    changed = False
    if "REV 18 (M1)" not in t:
        old1 = '''            for k in ("admin_failed_60s", "admin_ok_5min", "local_admin_count",
                      "sys_remote_conns", "sysmon_status"):'''
        new1 = '''            for k in ("admin_failed_60s", "admin_ok_5min", "local_admin_count",
                      "sys_remote_conns", "sysmon_status",
                      "blind_count", "raw_4624_24h"):   # REV 18 (M1)'''
        if old1 in t:
            t = t.replace(old1, new1)
            changed = True
    if "REV 18 (M2)" not in t:
        old2 = '''    res = lib.ask(row, "attest", since_hours=0.05, limit=10, timeout=lib.ASK_TIMEOUT_SEC)
    lib.record_ask(case_dir, row, "attest", res)
    return row.get("id"), res'''
        new2 = '''    res = lib.ask(row, "attest", since_hours=0.05, limit=10, timeout=lib.ASK_TIMEOUT_SEC)
    lib.record_ask(case_dir, row, "attest", res)
    wid = row.get("id")
    # REV 18 (M2): the census/cooldown contract. Census is the CHEAPEST knock
    # (one attest, 1/min) and runs before any hunt, so it owns the silent-host
    # book: a successful knock CLEARS the witness's L2 cooldown and a miss
    # MARKS it. One missed knock does not blind the next hunt.
    if res.get("ok"):
        lib.clear_silent(wid)
    else:
        lib.mark_silent(wid, (res.get("hole") or {}).get("why") or res.get("error") or "census miss")
    return wid, res'''
        if old2 in t:
            t = t.replace(old2, new2)
            changed = True
    if changed:
        c.write_text(t)
    print(f"{root.parent.name}: M1={'REV 18 (M1)' in t} M2={'REV 18 (M2)' in t} changed={changed}")
