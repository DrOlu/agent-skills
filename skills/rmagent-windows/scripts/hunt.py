#!/usr/bin/env python3
"""Hunter — walk Administrator (and SYSTEM) across the estate, one hop at a time.

Serial. Depth-capped. Never pooled. Writes hops + holes to a one-page case.
This is the "who walked in Ada's shoes" walk, scoped to tracked principals.

Usage:
  python3 hunt.py --inventory estate.yaml --since 2h --case-dir ./cases/ada
  python3 hunt.py --inventory estate.yaml --principal Administrator --since 1h
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402
import notify  # noqa: E402 — Telegram smoke alerts


def write_hop(case_dir: Path, hop: dict):
    p = case_dir / "path.json"
    hops = []
    if p.exists():
        try:
            hops = json.loads(p.read_text())
        except Exception:
            hops = []
    hops.append(hop)
    p.write_text(json.dumps(hops, indent=2))


def write_hole(case_dir: Path, h: dict):
    with (case_dir / "holes.jsonl").open("a") as f:
        f.write(json.dumps({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), **h}) + "\n")


def main():
    ap = argparse.ArgumentParser(description="RMAgent Hunter — tracked-principal walk")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--case-dir", default="./cases/admin-walk")
    ap.add_argument("--since", default="2h", help="window, e.g. 2h or 30m")
    ap.add_argument("--principal", default=None, help="override track (default: inventory track)")
    ap.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    def to_hours(s):
        s = s.strip()
        if s.endswith("h"):
            return float(s[:-1])
        if s.endswith("m"):
            return float(s[:-1]) / 60
        return float(s)

    since_h = to_hours(args.since)
    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)
    case_dir = Path(args.case_dir)
    case_dir.mkdir(parents=True, exist_ok=True)

    principal = args.principal
    if principal:
        for r in rows:
            r["track"] = [principal]
    track = (rows[0].get("track") if rows else None) or ["Administrator", "SYSTEM"]

    print(f"[hunt] tracking {track} across {len(rows)} witnesses, since {args.since}")
    seq = 0
    for r in rows:
        seq += 1
        wid = r.get("id")

        # edges — who did this witness touch?
        res = lib.ask(r, "edges", since_hours=since_h, limit=args.limit)
        lib.record_ask(case_dir, r, "edges", res)
        if res.get("ok") and res.get("data"):
            d = res["data"]
            n_logons = len(d.get("logons") or [])
            n_conns = len(d.get("conns") or [])
            n_expl = len(d.get("explicit_creds") or [])
            n_privs = len(d.get("special_privs") or [])
            print(f"  {wid:8} edges: {n_logons} tracked logons, {n_expl} explicit-cred uses, "
                  f"{n_privs} special-priv grants, {n_conns} outbound conns")
            write_hop(case_dir, {"seq": seq, "plane": r.get("plane"),
                                 "witness": wid, "skill": "edges",
                                 "logons": n_logons, "explicit_creds": n_expl,
                                 "special_privs": n_privs, "conns": n_conns,
                                 "t": d.get("utc")})
            # explain only where there is smoke (budget: depth-capped)
            # NOTE: explain payloads are far denser than edges (lolbin entries
            # carry full command lines), so use a tighter limit to stay under
            # the 32 KB anti-lake cap. 4688 auditing ON makes proc/lolbin
            # lists grow fast on busy boxes.
            if n_logons > 0 or n_conns > 0 or n_expl > 0:
                ex = lib.ask(r, "explain", since_hours=since_h,
                             limit=max(3, args.limit // 4))
                lib.record_ask(case_dir, r, "explain", ex)
                if ex.get("ok") and ex.get("data"):
                    ed = ex["data"]
                    g = len(ed.get("group_changes") or ed.get("identity_changes") or [])
                    sv = len(ed.get("service_events") or [])
                    tk = len(ed.get("task_events") or [])
                    pr = len(ed.get("proc_spawns") or [])
                    wm = len(ed.get("wmi_subscriptions") or [])
                    ac = len(ed.get("audit_cleared") or [])
                    lol = len(ed.get("lolbin_spawns") or [])
                    print(f"  {wid:8} explain: groups={g} svc={sv} tasks={tk} wmi={wm} "
                          f"procs={pr} lolbins={lol} audit-cleared={ac}")
                    write_hop(case_dir, {"seq": seq, "plane": r.get("plane"),
                                         "witness": wid, "skill": "explain",
                                         "group_changes": g, "service_events": sv,
                                         "task_events": tk, "wmi_subscriptions": wm,
                                         "audit_cleared": ac, "proc_spawns": pr,
                                         "lolbin_spawns": lol,
                                         "t": ed.get("utc")})
                    # Telegram: fire a smoke alert when explain finds changes
                    findings = []
                    if g:  findings.append(f"{g} identity/group/explicit-cred change(s) (4720/4732/4648/4672)")
                    if sv: findings.append(f"{sv} service event(s) (7045/7036)")
                    if tk: findings.append(f"{tk} scheduled task change(s) (4698/4702/4699)")
                    if wm: findings.append(f"{wm} WMI event subscription(s) (5861 — fileless persistence!)")
                    if ac: findings.append(f"{ac} AUDIT LOG CLEARED (1102 — anti-forensics!)")
                    if lol: findings.append(f"{lol} LOLBin spawn(s) with command line (4688)")
                    if pr: findings.append(f"{pr} Administrator/SYSTEM process spawn(s) (4688)")
                    if findings:
                        notify.alert_smoke(wid, findings, case_dir.name)
                else:
                    h = ex.get("hole") or lib.hole(f"{wid} explain", ex.get("error") or "empty")
                    write_hole(case_dir, h)
                    print(f"  {wid:8} explain: HOLE — {h['why']}")

            # pslogs — PowerShell script blocks (the actual code) where advertised
            if "pslogs" in (r.get("skills") or []):
                pl = lib.ask(r, "pslogs", since_hours=since_h, limit=args.limit)
                lib.record_ask(case_dir, r, "pslogs", pl)
                if pl.get("ok") and pl.get("data"):
                    nb = len(pl["data"].get("blocks") or [])
                    print(f"  {wid:8} pslogs: {nb} script block(s) (4104)")
                    write_hop(case_dir, {"seq": seq, "plane": r.get("plane"),
                                         "witness": wid, "skill": "pslogs",
                                         "blocks": nb, "t": pl["data"].get("utc")})
                else:
                    h = pl.get("hole") or lib.hole(f"{wid} pslogs", pl.get("error") or "empty")
                    write_hole(case_dir, h)
                    print(f"  {wid:8} pslogs: HOLE — {h['why']}")

        # kernring — kernel ETW burst capture (10s window, not a ring)
        if "kernring" in (r.get("skills") or []):
            kr = lib.ask(r, "kernring", since_hours=since_h, limit=args.limit)
            lib.record_ask(case_dir, r, "kernring", kr)
            if kr.get("ok") and kr.get("data"):
                d = kr["data"]
                np_ = len(d.get("procs") or [])
                ss = d.get("sysmon_status") or "unknown"
                bs = d.get("burst_seconds") or 10
                print(f"  {wid:8} kernring: {np_} proc events in {bs}s burst "
                      f"(sysmon={ss})")
                write_hop(case_dir, {"seq": seq, "plane": r.get("plane"),
                                     "witness": wid, "skill": "kernring",
                                     "procs": np_, "burst_seconds": bs,
                                     "sysmon_status": ss,
                                     "t": d.get("utc")})
                # Tripwire: Sysmon not running is a finding
                if ss in ("not-installed", "stopped", "unknown"):
                    notify.alert_smoke(wid, [f"Sysmon is {ss} — "
                                            f"the primary ring is down; kernring burst is the fallback"],
                                       case_dir.name)
            else:
                h = kr.get("hole") or lib.hole(f"{wid} kernring", kr.get("error") or "empty")
                write_hole(case_dir, h)
                print(f"  {wid:8} kernring: HOLE — {h['why']}")

        # attackmap — ATT&CK-mapped persistence state (registry locations)
        if "attackmap" in (r.get("skills") or []):
            am = lib.ask(r, "attackmap", since_hours=since_h, limit=args.limit)
            lib.record_ask(case_dir, r, "attackmap", am)
            if am.get("ok") and am.get("data"):
                d = am["data"]
                nf = d.get("found") or 0
                nc = d.get("checked") or 0
                print(f"  {wid:8} attackmap: {nf}/{nc} ATT&CK techniques with findings")
                write_hop(case_dir, {"seq": seq, "plane": r.get("plane"),
                                     "witness": wid, "skill": "attackmap",
                                     "checked": nc, "found": nf,
                                     "t": d.get("utc")})
                # Report the techniques found
                for f_ in (d.get("findings") or []):
                    print(f"    {f_.get('t')}: {f_.get('n')} ({f_.get('c')} values)")
                # High-severity techniques warrant a smoke alert
                high = [f_ for f_ in (d.get("findings") or [])
                        if f_.get("t") in ("T1546.010", "T1547.005", "T1547.004",
                                           "T1546.009", "T1562.004")]
                if high:
                    findings = [f"{f_.get('t')} {f_.get('n')} — {f_.get('c')} value(s)"
                                for f_ in high]
                    notify.alert_smoke(wid, findings, case_dir.name)
            else:
                h = am.get("hole") or lib.hole(f"{wid} attackmap", am.get("error") or "empty")
                write_hole(case_dir, h)
                print(f"  {wid:8} attackmap: HOLE — {h['why']}")

        else:
            h = res.get("hole") or lib.hole(f"{wid} edges", res.get("error") or "empty")
            write_hole(case_dir, h)
            print(f"  {wid:8} edges: HOLE — {h['why']}")

    # readable one-page summary
    hops = []
    try:
        hops = json.loads((case_dir / "path.json").read_text())
    except Exception:
        pass
    summary = case_dir / "CASE.md"
    lines = [f"# Case {case_dir.name}", "", f"Track: {track}",
             f"Window: {args.since}", "", "## Hops", ""]
    for h in hops:
        lines.append(f"- {h.get('seq'):02} {h.get('witness')} · {h.get('skill')} → "
                     f"{ {k:v for k,v in h.items() if k not in ('seq',)} }")
    lines += ["", "## Holes", ""]
    hf = case_dir / "holes.jsonl"
    if hf.exists():
        for line in hf.read_text().splitlines():
            if line.strip():
                lines.append(f"- {line}")
    else:
        lines.append("(none — every door answered)")
    summary.write_text("\n".join(lines))
    print(f"\n[case] {case_dir}/CASE.md  ({len(hops)} hops)")


if __name__ == "__main__":
    main()
