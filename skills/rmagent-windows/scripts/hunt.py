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
import traj as trajectory  # noqa: E402 — the case trajectory (fork/merge DAG)
import thinker  # noqa: E402 — persistent reasoning between knocks
import stc as stc_mod  # noqa: E402 — Security Trace Context (rev 6)
import hop_index  # noqa: E402 — cross-case hop index (rev 6)
import otel_emit  # noqa: E402 — OTel span emission (rev 6)
import causal  # noqa: E402 — causal graph / blast radius (rev 6)
import dthinker  # noqa: E402 — distributed thinker (rev 6)


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


def _resolve_dest(dest_str, rows):
    """Resolve a 4648 dest (hostname, IP, or 'localhost') to an inventory witness."""
    if not dest_str:
        return None
    d = str(dest_str).lower().strip()
    if d in ("localhost", "127.0.0.1", "::1"):
        return None  # same-box hop — no cross-host walk needed
    for r in rows:
        rid = (r.get("id") or "").lower()
        addr = (r.get("address") or "").lower()
        host = (r.get("host") or "").lower()
        if d in (rid, addr, host) or d.endswith(rid) or rid.endswith(d):
            return r
    # try IP match
    for r in rows:
        if str(r.get("address", "")).lower() in d or d in str(r.get("address", "")).lower():
            return r
    return None


def _walk_witness(row, stc, T, case_dir, since_h, args, visited, rows=None):
    """Recursively walk a witness reached via a 4648 hop. Budget-capped by the STC."""
    wid = row.get("id")
    T.think(f"following hop to {wid} (depth {stc.depth}, fanout {stc.fanout})")
    try:
        res = lib.ask(row, "edges", since_hours=since_h, limit=args.limit)
        if res.get("ok") and res.get("data"):
            d = res["data"]
            n_logons = len(d.get("logons") or [])
            n_expl = len(d.get("explicit_creds") or [])
            T.observe(wid, "edges", f"[depth {stc.depth}] {n_logons} logons, "
                                    f"{n_expl} explicit-creds")
            print(f"  {wid:8} edges (depth {stc.depth}): {n_logons} logons, "
                  f"{n_expl} explicit-cred uses")
            # record each logon hop with its REAL kind + join keys
            for lg in (d.get("logons") or [])[:args.limit]:
                hop_index.record(
                    case=case_dir.name, entry_id=T._next_id - 1, host=wid,
                    principal=lg.get("user") or stc.principal,
                    logonid=lg.get("lid"), src_ip=lg.get("src"),
                    hop_kind="4624", t=lg.get("t"))
            for ec in (d.get("explicit_creds") or [])[:args.limit]:
                hop_index.record(
                    case=case_dir.name, entry_id=T._next_id - 1, host=wid,
                    principal=ec.get("who") or stc.principal,
                    logonid=None, src_ip=ec.get("src"),
                    hop_kind="4648", t=ec.get("t"),
                    detail=f"became={ec.get('became')} dest={ec.get('dest')}")
            # recurse further if more hops and budget remains
            for ec in (d.get("explicit_creds") or []):
                dest = _resolve_dest(ec.get("dest"), rows)
                if dest and stc.can_descend and dest.get("id") not in visited:
                    visited.add(dest.get("id"))
                    _walk_witness(dest, stc.child(), T, case_dir, since_h, args, visited, rows)
        else:
            h = res.get("hole") or lib.hole(f"{wid} edges", res.get("error") or "empty")
            T.hole(wid, h["why"])
    except Exception as e:
        T.hole(wid, f"walk failed: {e}")


def main():
    ap = argparse.ArgumentParser(description="RMAgent Hunter — tracked-principal walk")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--case-dir", default="./cases/admin-walk")
    ap.add_argument("--since", default="2h", help="window, e.g. 2h or 30m")
    ap.add_argument("--principal", default=None, help="override track (default: inventory track)")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--ticket", default=None, help="business ticket — the Flight Recorder join")
    ap.add_argument("--trigger", default="manual", choices=["manual","scheduled","alert","drill","backfill"], help="what started this hunt")
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

    # --- the case trajectory: a DAG of observations, thoughts, actions ---
    T = trajectory.Trajectory(case_dir / "trajectory.jsonl")
    T.think(f"Hunt started: tracking {track} across {len(rows)} witnesses since {args.since}")

    # --- the thinker: reason over recent census history if available ---
    census_hist_path = Path.home() / ".rmagent" / "census_history.jsonl"
    if census_hist_path.exists():
        try:
            hist = [json.loads(l) for l in census_hist_path.read_text().splitlines() if l.strip()]
            findings = thinker.think(hist[-20:])  # last 20 censuses
            for f in findings:
                T.think(f"[{f['severity']}] {f['what']}")
            if findings:
                print(f"[thinker] {len(findings)} pattern(s) detected across recent censuses:")
                print(thinker.render(findings))
                critical = [f for f in findings if f.get("severity") == "critical"]
                if critical:
                    notify.alert_smoke("thinker", [f["what"] for f in critical], case_dir.name)
        except Exception as e:
            print(f"[thinker] history unavailable: {e}")

    # --- rev 6: Security Trace Context — context propagates, data does not ---
    S = stc_mod.STC(case=case_dir.name, principal=(track[0] if track else "unknown"),
                    window_h=since_h,
                    ticket=getattr(args, "ticket", None),
                    trigger=getattr(args, "trigger", "manual"))
    T.think(f"STC: {S}")

    # --- rev 6: clock-skew detection (the silent killer of cross-host timelines) ---
    for r in rows:
        wid = r.get("id")
        att = lib.ask(r, "attest", since_hours=0.05, limit=5)
        if att.get("ok") and att.get("data"):
            host_utc = att["data"].get("utc")
            try:
                from datetime import datetime, timezone
                skew = (datetime.fromisoformat(host_utc.replace("Z", "+00:00"))
                        - datetime.now(timezone.utc)).total_seconds()
                if abs(skew) > 1.0:
                    msg = f"{wid} clock skew {skew:+.1f}s — cross-host timelines unreliable until NTP is fixed"
                    T.think(f"[high] {msg}")
                    print(f"  [thinker] {msg}")
            except (ValueError, AttributeError):
                pass

    # --- rev 6: distributed thinker — correlation ACROSS hosts via the hop index ---
    idx_entries = hop_index.read_all()
    if len(idx_entries) >= 2:
        df = dthinker.think_distributed(idx_entries[-200:])
        for f in df:
            T.think(f"[{f['severity']}] {f['what']}")
        if df:
            print(f"[dthinker] {len(df)} cross-host correlation(s):")
            print(dthinker.render(df))
            crit = [f for f in df if f.get("severity") == "critical"]
            if crit:
                notify.alert_smoke("dthinker", [f["what"] for f in crit], case_dir.name)

    seq = 0
    _visited = {r.get("id") for r in rows}  # all inventory witnesses start visited
    for r in rows:
        seq += 1
        wid = r.get("id")
        T.think(f"Asking {wid}: edges — who did they touch?")

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
            T.observe(wid, "edges", f"{n_logons} logons, {n_expl} explicit-creds, "
                                    f"{n_privs} priv-grants, {n_conns} conns")

            # --- rev 8: FOLLOW the 4648 hop — the recursive cross-host walk ---
            for ec in (d.get("explicit_creds") or []):
                dest = _resolve_dest(ec.get("dest"), rows)
                if dest and dest.get("id") != wid and S.can_descend and dest.get("id") not in _visited:
                    child_stc = S.child()
                    _visited.add(dest.get("id"))
                    T.think(f"4648 hop: {ec.get('who')} became {ec.get('became')} "
                            f"on {dest.get('id')} — following (depth {child_stc.depth})")
                    _walk_witness(dest, child_stc, T, case_dir, since_h, args, _visited, rows)
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
                    T.observe(wid, "explain", f"groups={g} svc={sv} tasks={tk} wmi={wm} "
                                              f"procs={pr} lolbins={lol} audit-cleared={ac}")
                    if ac:
                        T.think(f"{wid}: audit log was cleared (1102) — anti-forensics, immediate escalation")
                    if wm:
                        T.think(f"{wid}: WMI subscription present (5861) — fileless persistence, "
                                f"consider disable_wmi_sub via actuate")
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

        # rev 9: netedges — Sysmon ring (conns, DNS, LSASS, injection, files, registry)
        if "netedges" in (r.get("skills") or []):
            ne = lib.ask(r, "netedges", since_hours=since_h, limit=args.limit)
            lib.record_ask(case_dir, r, "netedges", ne)
            if ne.get("ok") and ne.get("data"):
                nd = ne["data"]
                n_conn = len(nd.get("conns") or [])
                n_dns = len(nd.get("dns_queries") or [])
                n_ls = len(nd.get("lsass_access") or [])
                n_inj = len(nd.get("thread_injection") or [])
                n_fc = len(nd.get("file_creates") or [])
                n_rs = len(nd.get("registry_sets") or [])
                print(f"  {wid:8} netedges: {n_conn} conns, {n_dns} DNS, "
                      f"{n_ls} LSASS, {n_inj} inject, {n_fc} files, {n_rs} reg")
                T.observe(wid, "netedges", f"{n_conn} conns, {n_dns} DNS, {n_ls} LSASS, "
                                          f"{n_inj} inject, {n_fc} files, {n_rs} reg")
                if n_ls:
                    T.think(f"{wid}: LSASS access detected (T1003 credential dumping) — "
                            f"immediate escalation")
                if n_inj:
                    T.think(f"{wid}: remote thread injection detected (T1055)")
                # DNS tunneling detection
                dns_queries = nd.get("dns_queries") or []
                if dns_queries:
                    for q in dns_queries:
                        q.setdefault("host", wid)
                    tun = thinker._dns_tunneling(dns_queries)
                    for f in tun:
                        T.think(f"[{f['severity']}] {f['what']}")
                    if tun:
                        print(f"  {wid:8} dns_tunneling: {len(tun)} indicator(s)")
                        notify.alert_smoke(wid, [f["what"] for f in tun], case_dir.name)
            else:
                h = ne.get("hole") or lib.hole(f"{wid} netedges", ne.get("error") or "empty")
                write_hole(case_dir, h)
                print(f"  {wid:8} netedges: HOLE — {h['why']}")

        # rev 9: flowstats — volume baseline for T1041 exfiltration detection
        if "flowstats" in (r.get("skills") or []):
            fs = lib.ask(r, "flowstats", since_hours=since_h, limit=args.limit)
            lib.record_ask(case_dir, r, "flowstats", fs)
            if fs.get("ok") and fs.get("data"):
                fd = fs["data"]
                n_ad = len(fd.get("adapters") or [])
                n_dst = len(fd.get("top_destinations") or [])
                print(f"  {wid:8} flowstats: {n_ad} adapters, {n_dst} top destinations")
                T.observe(wid, "flowstats", f"{n_ad} adapters, {n_dst} destinations")
            else:
                h = fs.get("hole") or lib.hole(f"{wid} flowstats", fs.get("error") or "empty")
                write_hole(case_dir, h)
                print(f"  {wid:8} flowstats: HOLE — {h['why']}")

        else:
            h = res.get("hole") or lib.hole(f"{wid} edges", res.get("error") or "empty")
            write_hole(case_dir, h)
            T.hole(wid, h["why"])
            print(f"  {wid:8} edges: HOLE — {h['why']}")

    # readable one-page summary
    hops = []
    try:
        hops = json.loads((case_dir / "path.json").read_text())
    except Exception:
        pass

    # --- rev 6: record hops to the index (cross-case memory) ---
    # hop_kind must be a REAL kind (4624/4648/conn) — dthinker's session_correlation
    # and cross_host_chain join on these, and causal builds edges from them.
    # Recording "edges"/"explain" (skill names) made those detectors dead on real data.
    principal0 = track[0] if track else "unknown"
    # adaptive sampling: full detail when the hunt found smoke, summary when clean.
    # A clean hunt still records the join keys (host/principal/kind/case) so
    # cross-case correlation works, but drops logonid/src_ip/detail — stretching
    # the 5000-entry index window from weeks to months.
    # FN FIX: [high] findings (clock skew, cross-host chains) are real findings
    # too — they must trigger full sampling, not just [critical]
    found_smoke = any(e.get("kind") == "thought" and
                      ("smoke" in str(e.get("content", "")).lower() or
                       "critical" in str(e.get("content", "")).lower() or
                       "escalation" in str(e.get("content", "")).lower() or
                       "[high]" in str(e.get("content", "")).lower())
                      for e in T.entries())
    sample_mode = "full" if found_smoke else "summary"
    for h in hops:
        hop_index.record(
            case=case_dir.name, entry_id=h.get("seq", 0), host=h.get("witness", "?"),
            principal=principal0,
            logonid=h.get("logonid"),
            src_ip=h.get("src_ip"),
            hop_kind=h.get("hop_kind") or h.get("skill", "?"),
            t=h.get("t"),
            detail=f"logons={h.get('logons', 0)} conns={h.get('conns', 0)}",
            sample=sample_mode)

    # --- rev 6: emit the whole trajectory as OTel spans (best-effort) ---
    try:
        spans = [otel_emit.span_from_entry(e, S) for e in T.entries()]
        otel_emit.emit(spans)
    except Exception:
        pass  # never block a hunt on telemetry

    # --- rev 6: build the causal graph + blast radius ---
    try:
        g = causal.build_from_hop_index(case_dir.name, hop_index.read_all())
        if g.nodes:
            (case_dir / "causal_graph.dot").write_text(g.render_dot())
            T.think(f"causal graph: {len(g.nodes)} nodes, {len(g.edges)} edges — "
                    f"written to causal_graph.dot")
            # rendered PNG for humans (best-effort; needs graphviz on the jump host)
            if causal.render_png(g.render_dot(), case_dir / "causal_graph.png"):
                T.think(f"causal graph rendered to causal_graph.png")
    except Exception:
        pass

    T.think(f"Hunt complete. Trajectory: {T.stats()['total']} entries, "
            f"{T.stats()['branches']} branch(es).")
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
