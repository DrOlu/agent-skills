#!/usr/bin/env python3
"""RMAgent drift — baseline + diff for attest/attackmap answers.

`attest` is point-in-time: "who is admin NOW". The sharper question is
"who BECAME admin since last week" — that needs a stored baseline and a diff.

Baselines live in ~/.rmagent/baselines/<witness>.json (mode 600). First run
records the baseline; later runs diff against it and report:

  new_admins        accounts added to Administrators since baseline
  removed_admins    accounts removed (also interesting — de-provisioning?)
  new_persistence   attackmap techniques with MORE values than baseline
  gone_persistence  techniques with fewer values
  sysmon_change     Sysmon Running -> anything else (the Rev 4 tripwire)

Usage:
  python3 drift.py --inventory estate.yaml                 # baseline or diff
  python3 drift.py --inventory estate.yaml --reset         # re-baseline now
  python3 drift.py --inventory estate.yaml --json
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

BASE_DIR = Path.home() / ".rmagent" / "baselines"


def _snap_attest(row: dict) -> dict:
    res = lib.ask(row, "attest", since_hours=1.0, limit=20)
    d = res.get("data") or {}
    return {
        "admins": sorted(d.get("local_admins") or d.get("admins") or []),
        "admin_count": d.get("local_admin_count") or d.get("admin_count"),
        "sysmon_status": d.get("sysmon_status"),
        "blind_count": d.get("blind_count"),
        "blind_check": d.get("blind_check"),
        "raw_4624_24h": d.get("raw_4624_24h"),
        "utc": d.get("utc"),
    }


def _snap_profile(row: dict) -> dict:
    """Rev 14: on-device resource baseline — CPU/mem/disk + tracked-proc count.
    Joins 'host got weird' with 'identity got weird' in the same drift run."""
    if "profile" not in (row.get("skills") or []):
        return {}
    res = lib.ask(row, "profile", since_hours=1.0, limit=10)
    d = res.get("data") or {}
    if not d:
        return {}
    out = {"cpu_pct": d.get("cpu_pct"), "proc_count": d.get("proc_count")}
    mem = d.get("mem") or {}
    if mem:
        out["mem_used_pct"] = mem.get("used_pct")
    disks = d.get("disks") or []
    if disks:
        # worst (highest-used) local volume
        worst = max(disks, key=lambda x: x.get("used_pct") or 0)
        out["disk_used_pct_max"] = worst.get("used_pct")
    tracked = d.get("tracked_procs") or []
    out["tracked_proc_count"] = len(tracked)
    # names of tracked-principal processes — a NEW one appearing is a finding
    out["tracked_proc_names"] = sorted({t.get("n") for t in tracked if t.get("n")})
    return {"profile": out}


def _snap_attackmap(row: dict) -> dict:
    if "attackmap" not in (row.get("skills") or []):
        return {}
    res = lib.ask(row, "attackmap", since_hours=1.0, limit=200)
    d = res.get("data") or {}
    techs = {}
    for f in d.get("findings") or []:
        techs[f.get("t")] = int(f.get("n") or 0)
    return {"attackmap": techs}


def snapshot(row: dict) -> dict:
    """Pull the current state for one witness. Pure-ish (one ask per skill)."""
    snap = {"witness": row.get("id")}
    snap.update(_snap_attest(row))
    snap.update(_snap_profile(row))
    snap.update(_snap_attackmap(row))
    snap["taken_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return snap


def diff(old: dict, new: dict) -> dict:
    """Diff two snapshots into drift findings. Pure — no I/O."""
    out = {"witness": new.get("witness"), "baseline_utc": old.get("taken_utc"),
           "now_utc": new.get("taken_utc"), "findings": []}

    old_admins = set(old.get("admins") or [])
    new_admins = set(new.get("admins") or [])
    added = sorted(new_admins - old_admins)
    removed = sorted(old_admins - new_admins)
    if added:
        out["findings"].append({"kind": "new_admins", "severity": "critical",
                                "detail": "new local admin(s): %s" % ", ".join(added),
                                "accounts": added})
    if removed:
        out["findings"].append({"kind": "removed_admins", "severity": "info",
                                "detail": "admin(s) removed: %s" % ", ".join(removed),
                                "accounts": removed})

    old_sysmon = old.get("sysmon_status")
    new_sysmon = new.get("sysmon_status")
    if old_sysmon and new_sysmon and old_sysmon != new_sysmon:
        out["findings"].append({"kind": "sysmon_change", "severity": "critical",
                                "detail": "Sysmon %s -> %s" % (old_sysmon, new_sysmon)})

    # Rev 9: a witness going audit-blind is the worst regression — every other
    # question silently returns empty. Found live on WS2 (Logon was Failure-only).
    old_blind = int(old.get("blind_count") or 0)
    new_blind = int(new.get("blind_count") or 0)
    if new_blind > old_blind:
        blind_map = new.get("blind_check") or {}
        blind_list = [k for k, v in blind_map.items()
                      if isinstance(v, str) and v.startswith("BLIND")]
        out["findings"].append({"kind": "witness_blind", "severity": "critical",
                                "detail": "audit-blind subcategories grew %d -> %d (%s)"
                                          % (old_blind, new_blind, ", ".join(blind_list))})
    # raw_4624_24h dropping to 0 on a live box is also blindness (log rolled
    # or policy changed) — flag as warning, not critical (a quiet box is legal).
    if old.get("raw_4624_24h") and not new.get("raw_4624_24h"):
        out["findings"].append({"kind": "logon_visibility_lost", "severity": "warning",
                                "detail": "raw 4624 in 24h went %s -> 0" % old.get("raw_4624_24h")})

    # --- Rev 14: resource drift (profile) ---
    old_p = old.get("profile") or {}
    new_p = new.get("profile") or {}
    if old_p and new_p:
        # a NEW tracked-principal process is the identity x resource join —
        # a service that appeared running as Administrator/SYSTEM since baseline
        old_names = set(old_p.get("tracked_proc_names") or [])
        new_names = set(new_p.get("tracked_proc_names") or [])
        appeared = sorted(new_names - old_names)
        if appeared:
            out["findings"].append({"kind": "new_tracked_proc", "severity": "critical",
                                    "detail": "new process(s) running as a tracked principal: %s"
                                              % ", ".join(appeared),
                                    "processes": appeared})
        # resource spikes (warning — could be legitimate load)
        for field, label, threshold in (("cpu_pct", "CPU", 90), ("mem_used_pct", "memory", 90),
                                        ("disk_used_pct_max", "disk", 90)):
            ov, nv = old_p.get(field), new_p.get(field)
            if isinstance(ov, (int, float)) and isinstance(nv, (int, float)) and nv >= threshold > ov:
                out["findings"].append({"kind": "resource_spike", "severity": "warning",
                                        "detail": "%s %s%% -> %s%% (crossed %s%%)"
                                                  % (label, ov, nv, threshold),
                                        "field": field})

    old_t = old.get("attackmap") or {}
    new_t = new.get("attackmap") or {}
    for tech, n in sorted(new_t.items()):
        prev = old_t.get(tech, 0)
        if n > prev:
            out["findings"].append({"kind": "new_persistence", "severity": "warning",
                                    "detail": "%s grew %d -> %d" % (tech, prev, n),
                                    "technique": tech})
    for tech, n in sorted(old_t.items()):
        now_n = new_t.get(tech, 0)
        if n > now_n:
            out["findings"].append({"kind": "gone_persistence", "severity": "info",
                                    "detail": "%s shrank %d -> %d" % (tech, n, now_n),
                                    "technique": tech})
    return out


def main():
    ap = argparse.ArgumentParser(description="RMAgent drift — baseline + diff")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--reset", action="store_true", help="re-baseline now")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    BASE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(BASE_DIR, 0o700)

    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)
    results = []

    for row in rows:
        wid = row.get("id")
        bfile = BASE_DIR / ("%s.json" % wid)
        new = snapshot(row)

        if args.reset or not bfile.exists():
            bfile.write_text(json.dumps(new, indent=2))
            os.chmod(bfile, 0o600)
            results.append({"witness": wid, "baseline": True, "snapshot": new})
            continue

        try:
            old = json.loads(bfile.read_text())
        except Exception:
            old = {}
        d = diff(old, new)
        results.append(d)
        # refresh baseline to current state after a successful diff
        bfile.write_text(json.dumps(new, indent=2))
        os.chmod(bfile, 0o600)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for r in results:
        if r.get("baseline"):
            s = r.get("snapshot") or {}
            print("[drift] %s: BASELINE recorded (%s admins, sysmon=%s)"
                  % (r["witness"], s.get("admin_count") or len(s.get("admins") or []),
                     s.get("sysmon_status")))
            continue
        fs = r.get("findings") or []
        if not fs:
            print("[drift] %s: no drift since %s" % (r["witness"], r.get("baseline_utc")))
            continue
        print("[drift] %s (baseline %s):" % (r["witness"], r.get("baseline_utc")))
        for f in fs:
            print("  [%-8s] %-20s %s" % (f["severity"], f["kind"], f["detail"]))


if __name__ == "__main__":
    main()
