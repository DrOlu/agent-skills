#!/usr/bin/env python3
"""rmagent-ao drift — baseline + diff for the agent census.

First run records a baseline (~/.rmagent/agent-baselines/<id>.json, mode 600).
Later runs diff: new agents, new endpoints, new paths, gone agents.

Usage:
  python3 drift.py --inventory estate.yaml            # baseline or diff
  python3 drift.py --inventory estate.yaml --reset    # re-baseline now
"""
from __future__ import annotations
import argparse, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib

BASE_DIR = Path.home() / ".rmagent" / "agent-baselines"


def snapshot(row: dict) -> dict:
    """Pull the agentdrift digest for one witness."""
    res = lib.ask(row, "agentdrift", since_hours=1.0, limit=50)
    d = res.get("data") or {}
    return {
        "witness": row.get("id"),
        "kw_hits": d.get("kw_hits") or "",
        "ep_hits": d.get("ep_hits") or "",
        "paths": d.get("paths") or "",
        "utc": d.get("utc"),
    }


def _split(s: str) -> set[str]:
    return {x for x in (s or "").split(";") if x}


def diff(old: dict, new: dict) -> dict:
    out = {"witness": new.get("witness"), "baseline_utc": old.get("utc"),
           "now_utc": new.get("utc"), "findings": []}
    for field, label, sev in (
        ("kw_hits", "new_agents", "critical"),
        ("ep_hits", "new_endpoints", "critical"),
        ("paths", "new_paths", "warning"),
    ):
        added = sorted(_split(new.get(field) or "") - _split(old.get(field) or ""))
        if added:
            out["findings"].append({"kind": label, "severity": sev,
                                    "detail": f"{label}: {', '.join(added)}",
                                    "items": added})
    for field, label in (("kw_hits", "gone_agents"), ("ep_hits", "gone_endpoints")):
        gone = sorted(_split(old.get(field) or "") - _split(new.get(field) or ""))
        if gone:
            out["findings"].append({"kind": label, "severity": "info",
                                    "detail": f"{label}: {', '.join(gone)}",
                                    "items": gone})
    return out


def main():
    ap = argparse.ArgumentParser(description="rmagent-ao drift — agent baseline + diff")
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
        bfile = BASE_DIR / f"{wid}.json"
        new = snapshot(row)

        if args.reset or not bfile.exists():
            bfile.write_text(json.dumps(new, indent=2))
            os.chmod(bfile, 0o600)
            results.append({"witness": wid, "baseline": True,
                            "kw_hits": new["kw_hits"], "ep_hits": new["ep_hits"]})
            continue

        try:
            old = json.loads(bfile.read_text())
        except Exception:
            old = {}
        results.append(diff(old, new))
        bfile.write_text(json.dumps(new, indent=2))
        os.chmod(bfile, 0o600)

    if args.json:
        print(json.dumps(results, indent=2))
        return

    for r in results:
        if r.get("baseline"):
            print(f"[agentdrift] {r['witness']}: BASELINE recorded "
                  f"(agents={r['kw_hits']}, endpoints={r['ep_hits']})")
            continue
        fs = r.get("findings") or []
        if not fs:
            print(f"[agentdrift] {r['witness']}: no drift since {r.get('baseline_utc')}")
            continue
        print(f"[agentdrift] {r['witness']} (baseline {r.get('baseline_utc')}):")
        for f in fs:
            print(f"  [{f['severity']:8}] {f['kind']:16} {f['detail']}")


if __name__ == "__main__":
    main()