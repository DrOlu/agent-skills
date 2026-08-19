#!/usr/bin/env python3
"""RMAgent Actuate journal — append-only record of every applied action.

Each entry: id, timestamp, witness, action, target, reason, undo spec, result,
verification. Undoing an action writes a NEW entry (never edits an old one) so
the journal reads as a complete, ordered response story.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

JOURNAL = Path.home() / ".rmagent" / "actuate-journal.jsonl"


def _ensure() -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)


def next_id() -> int:
    entries = read_all()
    return (entries[-1]["id"] + 1) if entries else 1


def append(witness: str, action: str, target: str, reason: str,
           undo: dict | None, result: str, verified: bool = False,
           extra: dict | None = None) -> dict:
    """Append one journal entry and return it."""
    _ensure()
    entry = {
        "id": next_id(),
        "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "witness": witness,
        "action": action,
        "target": target,
        "reason": reason,
        "undo": undo,
        "result": result,          # "applied" | "dry-run" | "undone" | "failed"
        "verified": verified,
    }
    if extra:
        entry.update(extra)
    with JOURNAL.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def read_all() -> list[dict]:
    if not JOURNAL.exists():
        return []
    out = []
    for line in JOURNAL.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def get(entry_id: int) -> dict | None:
    for e in read_all():
        if e.get("id") == entry_id:
            return e
    return None


def applied_entries() -> list[dict]:
    """Entries that changed a host and have an undo spec."""
    return [e for e in read_all()
            if e.get("result") == "applied" and e.get("undo")]


def render(entries: list[dict] | None = None) -> str:
    """Human-readable journal for the CLI."""
    entries = entries if entries is not None else read_all()
    if not entries:
        return "(journal is empty — no actions applied yet)"
    lines = []
    for e in entries:
        undo = e.get("undo")
        undo_s = f"{undo['action']} {undo['target']}" if undo else "(none)"
        mark = "✓" if e.get("verified") else ("·" if e.get("result") == "dry-run" else "!")
        lines.append(
            f"{e['id']:3} {mark} {e['t']}  {e['witness']:5} {e['action']:16} "
            f"{str(e['target'])[:34]:34}  undo={undo_s}"
        )
        if e.get("reason"):
            lines.append(f"      reason: {e['reason']}")
    return "\n".join(lines)
