#!/usr/bin/env python3
"""CLI for the six ISO questions.

    python3 hunt.py attest  --rings examples/rings
    python3 hunt.py trace   --rings examples/rings --stan 123456 --rrn 123456789012
    python3 hunt.py hops    --rings examples/rings --stan 123456 --rrn 123456789012
    python3 hunt.py slow    --rings examples/rings --threshold-ms 800
    python3 hunt.py fail    --rings examples/rings
    python3 hunt.py baseline --rings examples/rings
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib import ask

SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_RINGS = SKILL_DIR / "examples" / "rings"

MAP = {
    "attest": "txnattest",
    "trace": "txntrace",
    "hops": "txnhops",
    "slow": "txnslow",
    "fail": "txnfail",
    "baseline": "txnbaseline",
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="rmagent-iso hunt")
    ap.add_argument("question", choices=list(MAP))
    ap.add_argument("--rings", default=str(DEFAULT_RINGS))
    ap.add_argument("--inventory", default=str(SKILL_DIR / "estate-iso.yaml"))
    ap.add_argument("--stan")
    ap.add_argument("--rrn")
    ap.add_argument("--since", type=float, default=None, help="hours")
    ap.add_argument("--threshold-ms", type=float, default=800)
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args(argv)
    ans = ask(
        MAP[args.question],
        rings=args.rings,
        stan=args.stan,
        rrn=args.rrn,
        since_hours=args.since,
        threshold_ms=args.threshold_ms,
        limit=args.limit,
    )
    print(json.dumps(ans, indent=2, default=str))
    if ans.get("hole") and ans.get("reason") in ("not-allowlisted", "need-stan-or-rrn"):
        return 2
    if ans.get("blind_check") == "BLIND":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
