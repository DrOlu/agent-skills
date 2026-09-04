#!/usr/bin/env python3
"""RMAgent correlate — join per-box answers across witnesses.

The drill's whole thesis is LATERAL MOVEMENT, but every question runs per-box.
This script joins edges/netedges/attest answers across witnesses for the same
account + time window, surfacing the pair patterns a per-box view structurally
misses:

  - account seen on BOTH boxes in the window (cross-host access)
  - WS1 connecting TO WS2's address (or vice versa) — the lateral hop itself
  - explicit-credential use on one box targeting a peer
  - same LogonId on two boxes (pass-the-hash / stolen session)

Usage:
  python3 correlate.py --inventory estate.yaml --since 2h
  python3 correlate.py --inventory estate.yaml --since 24h --case-dir ./cases/x

Writes correlation.json into the case dir and prints a readable digest.
Pure post-processing: re-uses answers already pulled by hunt.py when a case-dir
with answers/ is given; otherwise pulls edges/netedges itself.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def _to_hours(s: str) -> float:
    s = s.strip()
    if s.endswith("h"):
        return float(s[:-1])
    if s.endswith("m"):
        return float(s[:-1]) / 60
    if s.endswith("d"):
        return float(s[:-1]) * 24
    return float(s)


def _load_answers(case_dir: Path) -> dict:
    """Re-use answers hunt.py already pulled (answers/*.json)."""
    out = {}
    adir = case_dir / "answers"
    if not adir.exists():
        return out
    for f in sorted(adir.glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text())
        except Exception:
            continue
    return out


def _pull_edges(rows: list, since_h: float, limit: int) -> dict:
    """Pull edges (and netedges where advertised) fresh for each witness."""
    answers = {}
    for r in rows:
        wid = r.get("id")
        for skill in ("edges", "netedges"):
            if skill not in (r.get("skills") or []):
                continue
            res = lib.ask(r, skill, since_hours=since_h, limit=limit)
            answers[f"{wid}__{skill}"] = res.get("data") or {}
    return answers


def correlate(answers: dict, rows: list) -> dict:
    """Join per-box answers into cross-host findings. Pure — no I/O.

    Field names match the LIVE edges.ps1/netedges.ps1 payload shapes:
      logons:      {t, user, type, src, lid, auth}
      explicit:    {t, who, became, dest, src}
      conns:       {dest, port, pid, proc}   (netedges adds {user, ...})
    Legacy/verbose names (TargetUserName, LogonId, remote_ip...) are accepted
    as fallbacks so older captures still join.
    """
    by_id = {r.get("id"): r for r in rows}
    findings = []

    def _logon_user(lg):
        return (lg.get("user") or lg.get("TargetUserName") or "").strip()

    def _logon_lid(lg):
        return (lg.get("lid") or lg.get("logon_id") or lg.get("LogonId") or "").strip()

    def _conn_dest(c):
        return (c.get("dest") or c.get("remote_ip") or c.get("dest_ip")
                or c.get("DestinationIp") or "").strip()

    def _conn_port(c):
        return (c.get("port") or c.get("dest_port") or c.get("DestinationPort")
                or c.get("RemotePort") or "?")

    def _conn_owner(c):
        return (c.get("user") or c.get("owner") or c.get("proc") or "?")

    # --- 1. account seen on multiple boxes in the window ---
    acct_hosts = {}
    for key, data in answers.items():
        if "__edges" not in key:
            continue
        wid = key.split("__")[0]
        for lg in data.get("logons") or []:
            user = _logon_user(lg)
            if user:
                acct_hosts.setdefault(user, set()).add(wid)
    for user, hosts in sorted(acct_hosts.items()):
        if len(hosts) > 1:
            findings.append({
                "kind": "cross-host-account",
                "severity": "warning",
                "detail": "account '%s' logged on to %d witnesses (%s) in the window"
                          % (user, len(hosts), ", ".join(sorted(hosts))),
                "account": user,
                "hosts": sorted(hosts),
            })

    # --- 2. network edge from one witness to another's address ---
    addr_to_id = {r.get("address"): r.get("id") for r in rows if r.get("address")}
    for key, data in answers.items():
        if "__edges" not in key and "__netedges" not in key:
            continue
        src = key.split("__")[0]
        conns = (data.get("conns") or []) + (data.get("connections") or [])
        for c in conns:
            dst_ip = _conn_dest(c)
            dst_id = addr_to_id.get(dst_ip)
            if dst_id and dst_id != src:
                findings.append({
                    "kind": "lateral-hop",
                    "severity": "critical",
                    "detail": "%s -> %s (%s) port %s by %s"
                              % (src, dst_ip, dst_id, _conn_port(c), _conn_owner(c)),
                    "src": src, "dst": dst_id, "dst_ip": dst_ip,
                })

    # --- 3. explicit-credential use targeting a peer box ---
    for key, data in answers.items():
        if "__edges" not in key:
            continue
        src = key.split("__")[0]
        for ec in data.get("explicit_creds") or []:
            target = (ec.get("dest") or ec.get("target")
                      or ec.get("TargetServerName") or "").strip()
            if not target:
                continue
            for other_id, r in by_id.items():
                if other_id == src:
                    continue
                other_addr = (r.get("address") or "").strip()
                if other_addr and other_addr in target:
                    findings.append({
                        "kind": "explicit-cred-to-peer",
                        "severity": "warning",
                        "detail": "%s: %s used explicit creds targeting %s (peer %s)"
                                  % (src, ec.get("who") or ec.get("user") or "?", target, other_id),
                        "src": src, "dst": other_id,
                    })

    # --- 4. same LogonId on two boxes (stolen session / PTH) ---
    logonid_hosts = {}
    for key, data in answers.items():
        if "__edges" not in key:
            continue
        wid = key.split("__")[0]
        for lg in data.get("logons") or []:
            lid = _logon_lid(lg)
            if lid and lid not in ("0x0", "0x3e7"):
                logonid_hosts.setdefault(lid, set()).add(wid)
    for lid, hosts in logonid_hosts.items():
        if len(hosts) > 1:
            findings.append({
                "kind": "shared-logonid",
                "severity": "critical",
                "detail": "LogonId %s appears on %d witnesses (%s) — same session on two boxes"
                          % (lid, len(hosts), ", ".join(sorted(hosts))),
                "logon_id": lid, "hosts": sorted(hosts),
            })

    sev_order = {"critical": 0, "warning": 1, "info": 2}
    findings.sort(key=lambda f: sev_order.get(f.get("severity", "info"), 3))
    return {
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "witnesses": [r.get("id") for r in rows],
        "findings": findings,
        "summary": {
            "critical": sum(1 for f in findings if f["severity"] == "critical"),
            "warning": sum(1 for f in findings if f["severity"] == "warning"),
            "total": len(findings),
        },
    }


def main():
    ap = argparse.ArgumentParser(description="RMAgent correlate — cross-witness join")
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--since", default="2h")
    ap.add_argument("--case-dir", default=None,
                    help="reuse answers from this case dir if present")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--json", action="store_true", help="print raw JSON only")
    args = ap.parse_args()

    since_h = _to_hours(args.since)
    inv = lib.load_inventory(args.inventory)
    rows = lib.witnesses(inv)

    answers = {}
    if args.case_dir:
        answers = _load_answers(Path(args.case_dir))
    if not any("__edges" in k for k in answers):
        answers = _pull_edges(rows, since_h, args.limit)

    result = correlate(answers, rows)

    if args.case_dir:
        cdir = Path(args.case_dir)
        cdir.mkdir(parents=True, exist_ok=True)
        (cdir / "correlation.json").write_text(json.dumps(result, indent=2))

    if args.json:
        print(json.dumps(result, indent=2))
        return

    s = result["summary"]
    print("[correlate] %d witnesses, window %s" % (len(rows), args.since))
    print("  critical: %d   warning: %d   total: %d" % (s["critical"], s["warning"], s["total"]))
    if not result["findings"]:
        print("  (no cross-host patterns — per-box views agree)")
        return
    for f in result["findings"]:
        print("  [%-8s] %-22s %s" % (f["severity"], f["kind"], f["detail"]))


if __name__ == "__main__":
    main()
