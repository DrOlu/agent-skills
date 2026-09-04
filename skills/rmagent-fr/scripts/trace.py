#!/usr/bin/env python3
"""Trace query API — merge trajectory + hop index + causal graph into one view.

The data existed in three places (trajectory.jsonl, hop_index.jsonl, OTel spans)
but there was no get_trace(case_id) that merged them. A SOC analyst clicking
"show me this incident" got nothing. Now:

    python3 trace.py CASE-20260825-143022          # full merged trace
    python3 trace.py CASE-... --json               # machine-readable
    python3 trace.py --ticket PAY-4419             # find traces by business ticket
    python3 trace.py --principal Administrator     # find traces by principal
    python3 trace.py --list                        # list all cases in the index

Also exposes get_trace(case_id) for the RTerm gateway to call.
"""
from __future__ import annotations
import json
import sys
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hop_index
import causal
import stc as stc_mod

CASES_DIR = Path.home() / "cases"


# ---------------------------------------------------------------- core
def find_case_dir(case_id: str) -> Path | None:
    """Locate a case directory by id (exact or suffix match)."""
    if not CASES_DIR.exists():
        return None
    # exact
    d = CASES_DIR / case_id
    if d.exists():
        return d
    # suffix match (case ids are timestamps like 20260825-143022)
    for c in CASES_DIR.iterdir():
        if c.is_dir() and case_id in c.name:
            return c
    return None


def load_trajectory(case_dir: Path) -> list[dict]:
    """Read the case's trajectory.jsonl."""
    tj = case_dir / "trajectory.jsonl"
    if not tj.exists():
        return []
    out = []
    for line in tj.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def load_stc(case_dir: Path) -> dict | None:
    """Reconstruct the STC from the trajectory's first STC thought entry.

    REV 18 (H4): falls back to case.json when the trajectory carries no STC
    line (e.g. census-only cases, or a hunt that died before the STC thought
    was written). The ticket must survive whichever way the case was made."""
    for e in load_trajectory(case_dir):
        content = str(e.get("content", ""))
        if content.startswith("STC:"):
            try:
                return stc_mod.STC.decode(content[4:].strip()).__dict__
            except ValueError:
                return None
    # fallback: case.json (written by case.py open --ticket ...)
    meta_path = case_dir / "case.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text())
            if meta.get("ticket") or meta.get("title"):
                return {
                    "case": case_dir.name,
                    "principal": meta.get("principal") or "",
                    "window_h": 2.0,
                    "origin": "jh1",
                    "depth": 0,
                    "ticket": meta.get("ticket"),
                    "trigger": meta.get("trigger") or "manual",
                    "app_trace_id": meta.get("app_trace_id"),
                }
        except Exception:
            return None
    return None


def get_trace(case_id: str) -> dict:
    """The merged view: trajectory + hops + causal graph + STC + summary."""
    case_dir = find_case_dir(case_id)
    if not case_dir:
        return {"ok": False, "error": f"case {case_id} not found"}

    traj = load_trajectory(case_dir)
    hops = hop_index.by_case(case_dir.name)
    stc = load_stc(case_dir)

    # causal graph from the hop index entries for this case
    graph = causal.build_from_hop_index(case_dir.name, hop_index.read_all())

    # summary
    kinds = {}
    for e in traj:
        kinds[e.get("kind", "?")] = kinds.get(e.get("kind", "?"), 0) + 1
    hosts = sorted({h.get("host") for h in hops if h.get("host")})
    holes = [e for e in traj if e.get("kind") == "hole"]
    thoughts = [e for e in traj if e.get("kind") == "thought"]

    return {
        "ok": True,
        "case": case_dir.name,
        "case_dir": str(case_dir),
        "stc": stc,
        "ticket": (stc or {}).get("ticket"),
        "summary": {
            "entries": len(traj),
            "by_kind": kinds,
            "hops": len(hops),
            "hosts_touched": hosts,
            "holes": len(holes),
            "thoughts": len(thoughts),
            "branches": len({e.get("branch", "main") for e in traj}),
            "graph_nodes": len(graph.nodes),
            "graph_edges": len(graph.edges),
        },
        "trajectory": traj,
        "hops": hops,
        "holes": [{"id": e["id"], "why": e.get("content", "")} for e in holes],
        "key_thoughts": [{"id": e["id"], "t": e.get("t"), "what": e.get("content")}
                         for e in thoughts],
        "causal_graph": {
            "nodes": list(graph.nodes.keys()),
            "edges": [{"src": e.src, "dst": e.dst, "kind": e.kind, "detail": e.detail}
                      for e in graph.edges],
            "dot": graph.render_dot(),
        },
    }


def find_by_ticket(ticket: str) -> list[dict]:
    """Every trace whose STC carries this business ticket."""
    out = []
    if not CASES_DIR.exists():
        return out
    for c in sorted(CASES_DIR.iterdir()):
        if not c.is_dir():
            continue
        stc = load_stc(c)
        if stc and stc.get("ticket") == ticket:
            out.append({"case": c.name, "stc": stc})
    return out


def find_by_principal(principal: str) -> list[dict]:
    """Every case whose hop index mentions this principal."""
    entries = hop_index.by_principal(principal)
    cases = sorted({e.get("case") for e in entries if e.get("case")})
    return [{"case": c, "hops": len([e for e in entries if e.get("case") == c])}
            for c in cases]


def list_cases() -> list[dict]:
    """All cases: hop-index entries PLUS case directories with no hops.

    BUG FIX: this used to read only the hop index, so a case where every
    witness was silent (0 hops) was invisible. Now the cases dir is scanned
    too and merged in with hops=0.
    """
    all_e = hop_index.read_all()
    by_case = {}
    for e in all_e:
        c = e.get("case")
        if c:
            by_case.setdefault(c, {"hops": 0, "hosts": set()})
            by_case[c]["hops"] += 1
            if e.get("host"):
                by_case[c]["hosts"].add(e["host"])
    # also include case directories the index doesn't know about
    if CASES_DIR.exists():
        for d in CASES_DIR.iterdir():
            if d.is_dir() and d.name not in by_case:
                by_case[d.name] = {"hops": 0, "hosts": set()}
    return [{"case": c, "hops": v["hops"], "hosts": sorted(v["hosts"])}
            for c, v in sorted(by_case.items())]


# ---------------------------------------------------------------- render
def render_trace(t: dict) -> str:
    """Human-readable merged trace."""
    if not t.get("ok"):
        return t.get("error", "unknown error")
    s = t["summary"]
    lines = []
    lines.append(f"TRACE {t['case']}")
    if t.get("ticket"):
        lines.append(f"  ticket: {t['ticket']}")
    if t.get("stc"):
        st = t["stc"]
        lines.append(f"  stc: principal={st.get('principal')} window={st.get('window_h')}h "
                     f"origin={st.get('origin')} depth={st.get('depth')}")
    lines.append(f"  {s['entries']} trajectory entries ({s['branches']} branch(es)) · "
                 f"{s['hops']} hops · {len(s['hosts_touched'])} host(s): "
                 f"{', '.join(s['hosts_touched'])}")
    lines.append(f"  {s['holes']} hole(s) · {s['thoughts']} thought(s) · "
                 f"causal graph: {s['graph_nodes']} nodes / {s['graph_edges']} edges")
    lines.append("")

    if t["key_thoughts"]:
        lines.append("REASONING CHAIN:")
        for th in t["key_thoughts"][:20]:
            lines.append(f"  {th['id']:3} ~ {str(th['what'])[:100]}")
        lines.append("")

    if t["hops"]:
        lines.append("HOPS:")
        for h in t["hops"][:30]:
            lid = h.get("logonid") or "-"
            src = h.get("src_ip") or "-"
            lines.append(f"  {h.get('t', '?')[:19]}  {h.get('host', '?'):8} "
                         f"{h.get('kind', '?'):8} {str(h.get('principal', '?'))[:16]:16} "
                         f"src={src:15} lid={lid}")
        lines.append("")

    if t["holes"]:
        lines.append("HOLES:")
        for h in t["holes"]:
            lines.append(f"  {h['id']:3} ! {h['why'][:90]}")
        lines.append("")

    if t["causal_graph"]["edges"]:
        lines.append("CAUSAL GRAPH:")
        for e in t["causal_graph"]["edges"][:15]:
            lines.append(f"  {e['src']}  --{e['kind']}-->  {e['dst']}")
        lines.append("")
        lines.append("BLAST RADIUS (from first node, 4 hops):")
        g = causal.build_from_hop_index(t["case"], hop_index.read_all())
        if g.nodes:
            first = list(g.nodes.keys())[0]
            reach = g.blast_radius(first, 4)
            lines.append(f"  {len(reach)} node(s) reachable from {first}")
    return "\n".join(lines)


# ---------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description="RMAgent trace query")
    ap.add_argument("case", nargs="?", help="case id (full or suffix)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--ticket", help="find traces by business ticket")
    ap.add_argument("--principal", help="find traces by principal")
    ap.add_argument("--list", action="store_true", help="list all cases")
    args = ap.parse_args()

    if args.list:
        cases = list_cases()
        if args.json:
            print(json.dumps(cases, indent=2))
        else:
            for c in cases:
                print(f"{c['case']:24} {c['hops']:3} hops  hosts={','.join(c['hosts'])}")
        return

    if args.ticket:
        r = find_by_ticket(args.ticket)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            if not r:
                print(f"(no traces for ticket {args.ticket})")
            for x in r:
                print(f"{x['case']}  stc={x['stc']}")
        return

    if args.principal:
        r = find_by_principal(args.principal)
        if args.json:
            print(json.dumps(r, indent=2))
        else:
            if not r:
                print(f"(no traces for principal {args.principal})")
            for x in r:
                print(f"{x['case']:24} {x['hops']:3} hops")
        return

    if not args.case:
        ap.print_help()
        return

    t = get_trace(args.case)
    if args.json:
        print(json.dumps(t, indent=2, default=str))
    else:
        print(render_trace(t))


if __name__ == "__main__":
    main()
