#!/usr/bin/env python3
"""Delegate a refused question to a Synapse peer agent.

Usage:
  python3 delegate_refusal.py --instance-dir ./inst \
      --question "how many work orders are blocked" \
      --gateway http://127.0.0.1:8090

Flow:
  1. ask the local instance (refusal expected)
  2. discover mesh peers whose skills match the question's domain nouns
  3. delegate to the best match
  4. print the peer's response, tagged as peer-sourced
"""
import argparse
import json
import sys

from neuralosd._cmd._common import load_instance
from neuralosd.router import NoResults
from neuralosd.synapse import (SynapseError, SynapseHTTP, delegate_to_peer,
                               discover_peers)


def main():
    ap = argparse.ArgumentParser(
        description="Delegate a refused question to a Synapse peer")
    ap.add_argument("--instance-dir", required=True)
    ap.add_argument("--question", required=True)
    ap.add_argument("--gateway", default="http://127.0.0.1:8090")
    ap.add_argument("--timeout", type=float, default=30)
    args = ap.parse_args()

    inst = load_instance(args.instance_dir)
    transport = SynapseHTTP(gateway=args.gateway, timeout=args.timeout)

    # 1. ask locally
    try:
        env = inst.ask(args.question)
        print(f"ANSWERED locally by {env.get('probe')}")
        print(json.dumps(env["results"], indent=2, ensure_ascii=False))
        return 0
    except NoResults as e:
        env = getattr(e, "envelope", {}) or {}
        print(f"REFUSED locally: {env.get('error', 'no results')}")
    except Exception as e:
        print(f"ERROR: {e}")
        return 1

    # 2. discover peers
    print("\ndiscovering peers ...")
    try:
        peers = discover_peers(transport, args.question, inst.name)
    except SynapseError as e:
        print(f"discovery failed: {e}")
        return 1

    if not peers:
        print("no peers on the mesh have the capability for this question")
        print("\nthe question is logged as a gap — add a probe or a derived "
              "metric to handle it")
        return 2

    print(f"  {len(peers)} peer(s) matched:")
    for p in peers:
        print(f"    {p['agent_id']}  matched: {', '.join(p['matched'])}")

    # 3. delegate to the best match
    best = peers[0]
    print(f"\ndelegating to {best['agent_id']} ...")
    result = delegate_to_peer(transport, best, args.question)
    if result is None:
        print("peer did not respond")
        return 1

    print(f"\npeer response (source: {result['source']}):")
    print(json.dumps(result["response"], indent=2, ensure_ascii=False,
                     default=str))
    print("\n⚠ this response came from a PEER AGENT, not from a locally "
          "verified probe. Verify before using.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
