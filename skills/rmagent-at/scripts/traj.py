#!/usr/bin/env python3
"""Trajectory DAG for RMAgent cases — fork, merge, walk, render.

Stolen from Headlong's insight (github.com/laude-institute/headlong): the record
of what the agent asked, thought, and found should be a first-class DAG with
fork and merge — not just an append-only audit log. A hunt that branches
("check WS1 or WS2 first?") can fork, explore both, and merge the findings.

Each entry: {id, parent, t, kind, witness, skill, content, branch}
  kind: observation | thought | action | result | fork | merge | hole
  branch: the branch name this entry belongs to (default "main")

The trajectory is append-only. Nothing is edited in place. Forking creates a
new branch from any entry; merging records that two branches converged.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

KINDS = {"observation", "thought", "action", "result", "fork", "merge", "hole"}


class Trajectory:
    """Append-only DAG of case entries with fork and merge."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict] = []
        self._next_id = 1
        self._load()

    # ---------------------------------------------------------------- load/save
    def _load(self) -> None:
        if self.path.exists():
            for line in self.path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    self._entries.append(e)
                    if e.get("id", 0) >= self._next_id:
                        self._next_id = e["id"] + 1
                except json.JSONDecodeError:
                    continue

    def _append(self, entry: dict) -> dict:
        entry["id"] = self._next_id
        self._next_id += 1
        self._entries.append(entry)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    # ---------------------------------------------------------------- write ops
    def observe(self, witness: str, skill: str, content, branch: str = "main",
                parent: int | None = None) -> dict:
        """Record an observation: what a question returned."""
        return self._append({
            "t": _now(), "kind": "observation", "witness": witness,
            "skill": skill, "content": _safe(content), "branch": branch,
            "parent": parent or self._last_id(branch),
        })

    def think(self, content, branch: str = "main", parent: int | None = None) -> dict:
        """Record a thought: the agent's reasoning about what to do next."""
        return self._append({
            "t": _now(), "kind": "thought", "witness": None,
            "skill": None, "content": content, "branch": branch,
            "parent": parent or self._last_id(branch),
        })

    def act(self, witness: str, skill: str, content, branch: str = "main",
            parent: int | None = None) -> dict:
        """Record an action: something the agent did (ask, apply, block)."""
        return self._append({
            "t": _now(), "kind": "action", "witness": witness,
            "skill": skill, "content": _safe(content), "branch": branch,
            "parent": parent or self._last_id(branch),
        })

    def result(self, content, branch: str = "main", parent: int | None = None) -> dict:
        """Record a result: what an action produced."""
        return self._append({
            "t": _now(), "kind": "result", "witness": None,
            "skill": None, "content": _safe(content), "branch": branch,
            "parent": parent or self._last_id(branch),
        })

    def hole(self, witness: str, why: str, branch: str = "main") -> dict:
        """Record a hole: we asked, the door stayed shut."""
        return self._append({
            "t": _now(), "kind": "hole", "witness": witness,
            "skill": None, "content": why, "branch": branch,
            "parent": self._last_id(branch),
        })

    def fork(self, from_id: int, branch: str, reason: str) -> dict:
        """Fork a new branch from entry from_id. The branch explores an alternative."""
        src = self.get(from_id)
        if not src:
            raise ValueError(f"no entry {from_id} to fork from")
        return self._append({
            "t": _now(), "kind": "fork", "witness": None, "skill": None,
            "content": reason, "branch": branch, "parent": from_id,
            "forked_from": src.get("branch", "main"),
        })

    def merge(self, branches: list[str], into: str = "main", reason: str = "") -> dict:
        """Merge branches back into a parent branch. Records convergence."""
        parents = [self._last_id(b) for b in branches if self._last_id(b)]
        return self._append({
            "t": _now(), "kind": "merge", "witness": None, "skill": None,
            "content": reason, "branch": into,
            "parent": parents[-1] if parents else None,
            "merged_from": branches,
        })

    # ---------------------------------------------------------------- read ops
    def get(self, entry_id: int) -> dict | None:
        for e in self._entries:
            if e.get("id") == entry_id:
                return e
        return None

    def entries(self, branch: str | None = None) -> list[dict]:
        if branch is None:
            return list(self._entries)
        return [e for e in self._entries if e.get("branch") == branch]

    def branches(self) -> list[str]:
        return sorted({e.get("branch", "main") for e in self._entries})

    def children(self, entry_id: int) -> list[dict]:
        return [e for e in self._entries if e.get("parent") == entry_id]

    def ancestors(self, entry_id: int) -> list[dict]:
        """Walk up the DAG from an entry to the root."""
        chain = []
        seen = set()
        cur = self.get(entry_id)
        while cur and cur["id"] not in seen:
            chain.append(cur)
            seen.add(cur["id"])
            cur = self.get(cur.get("parent") or 0)
        return list(reversed(chain))

    def _last_id(self, branch: str) -> int | None:
        for e in reversed(self._entries):
            if e.get("branch") == branch:
                return e["id"]
        return None

    # ---------------------------------------------------------------- render
    def render(self, branch: str | None = None) -> str:
        """Human-readable trajectory for the CLI / case file."""
        entries = self.entries(branch)
        if not entries:
            return "(trajectory is empty)"
        lines = []
        for e in entries:
            mark = {"observation": "·", "thought": "~", "action": ">",
                    "result": "=", "fork": "├", "merge": "┴", "hole": "!"}[e["kind"]]
            w = e.get("witness") or ""
            s = e.get("skill") or ""
            head = f"{e['id']:3} {mark} [{e['kind'][:4]}]"
            if w:
                head += f" {w}"
            if s:
                head += f"/{s}"
            content = str(e.get("content", ""))[:110]
            lines.append(f"{head:32} {content}")
        return "\n".join(lines)

    def render_tree(self) -> str:
        """Render the DAG as a tree showing branches."""
        lines = []
        for b in self.branches():
            entries = self.entries(b)
            if not entries:
                continue
            lines.append(f"── branch: {b} ({len(entries)} entries) ──")
            for e in entries:
                mark = {"observation": "·", "thought": "~", "action": ">",
                        "result": "=", "fork": "├", "merge": "┴", "hole": "!"}[e["kind"]]
                lines.append(f"  {e['id']:3} {mark} {str(e.get('content',''))[:90]}")
            lines.append("")
        return "\n".join(lines)

    def stats(self) -> dict:
        by_kind = {}
        for e in self._entries:
            by_kind[e["kind"]] = by_kind.get(e["kind"], 0) + 1
        return {
            "total": len(self._entries),
            "branches": len(self.branches()),
            "by_kind": by_kind,
        }


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _safe(content) -> str:
    """Coerce content to a short string (the 32 KB cap discipline applies)."""
    if isinstance(content, (dict, list)):
        s = json.dumps(content)
        return s[:500] + ("…" if len(s) > 500 else "")
    return str(content)[:500]
