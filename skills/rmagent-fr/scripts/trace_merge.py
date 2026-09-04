#!/usr/bin/env python3
"""Item 3: pull-merge multi-jump-host tracing.

Each jump host keeps its own ~/.rmagent/ + ~/cases/. For a two-site estate,
this module pulls from remote jump hosts over SSH and merges into one view.
No shared state, no new infrastructure — query-time fan-out and merge.

Usage (in trace.py):
    trace.py CASE-X --remote user@host2[,user@host3]   # merge remote indexes

The remote needs only: ssh access + the rmagent scripts in the same location.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

REMOTE_SCRIPT = '''
import json, sys
# REV 18 (M5): resolve the engine from CURRENT trees, not the legacy
# ~/.claude path (which holds a stale pre-Rev-17 lib). Same candidate order
# as rmagent-actuate's import fix. A remote set up from ~/.agents/skills
# used to return [] silently.
from pathlib import Path as _P
_home = _P.home()
for _c in (_home / ".agents" / "skills" / "rmagent-windows" / "scripts",
           _home / ".agents" / "skills" / "rmagent-so" / "scripts",
           _home / ".claude" / "skills" / "rmagent-windows" / "scripts"):
    if (_c / "hop_index.py").exists():
        sys.path.insert(0, str(_c))
        break
import hop_index
case = sys.argv[1] if len(sys.argv) > 1 else None
entries = hop_index.read_all()
if case:
    entries = [e for e in entries if e.get("case") == case]
print(json.dumps(entries))
'''


def pull_remote_hops(remote: str, case: str | None = None, timeout: int = 15) -> list[dict]:
    """Pull hop-index entries from a remote jump host over SSH. Never raises."""
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             remote, "python3", "-c", REMOTE_SCRIPT, case or ""],
            capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            return []
        out = r.stdout.strip()
        # find the JSON array (skip any SSH banners)
        i = out.find("[")
        if i < 0:
            return []
        return json.loads(out[i:])
    except Exception:
        return []


def merge_traces(local_hops: list[dict], remote_hops: list[dict]) -> list[dict]:
    """Merge local + remote hop entries, deduplicating by (case, entry, host, kind, t)."""
    seen = set()
    merged = []
    for e in local_hops + remote_hops:
        key = (e.get("case"), e.get("entry"), e.get("host"),
               e.get("kind"), e.get("t"))
        if key not in seen:
            seen.add(key)
            merged.append(e)
    return sorted(merged, key=lambda x: str(x.get("t", "")))


def pull_and_merge(remotes: list[str], case: str | None = None) -> tuple[list[dict], dict]:
    """Pull from all remotes, merge with local. Returns (merged, per-remote status)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hop_index
    local = hop_index.read_all()
    if case:
        local = [e for e in local if e.get("case") == case]

    status = {"local": len(local)}
    all_remote = []
    for r in remotes:
        hops = pull_remote_hops(r, case)
        status[r] = len(hops)
        all_remote.extend(hops)

    return merge_traces(local, all_remote), status
