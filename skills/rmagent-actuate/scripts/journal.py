#!/usr/bin/env python3
"""RMAgent Actuate journal — append-only record of every applied action.

Each entry: id, timestamp, witness, action, target, reason, undo spec, result,
verification, prev_sha256. Undoing an action writes a NEW entry (never edits
an old one) so the journal reads as a complete, ordered response story.

Rev 17 (H3): entries are chained — each carries the sha256 of the previous
entry's canonical line, so silent edits or deletions anywhere in the file
break the chain and are caught by `journal.py verify` (also exposed as
`actuate.py journal`, which verifies on every read). The chain is computed
over the entry WITHOUT its own prev_sha256/entry_sha256 fields, so the check
is stable across schema additions. The file is chmod 600: an audit trail
that any local user can edit is not an audit trail.
"""
from __future__ import annotations
import hashlib
import json
import time
from pathlib import Path

JOURNAL = Path.home() / ".rmagent" / "actuate-journal.jsonl"
MODE = 0o600


def _ensure() -> None:
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)


def _line_digest(entry: dict) -> str:
    """sha256 of the canonical entry minus its own chain fields."""
    core = {k: v for k, v in entry.items() if k not in ("prev_sha256", "entry_sha256")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def _chmod() -> None:
    try:
        JOURNAL.chmod(MODE)
    except OSError:
        pass  # best-effort; some filesystems (network shares) reject chmod


def next_id() -> int:
    entries = read_all()
    return (entries[-1]["id"] + 1) if entries else 1


def append(witness: str, action: str, target: str, reason: str,
           undo: dict | None, result: str, verified: bool = False,
           extra: dict | None = None, plan_id: str | None = None) -> dict:
    """Append one journal entry and return it."""
    _ensure()
    prev = read_all()
    prev_sha = prev[-1].get("entry_sha256") if prev else None
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
    if plan_id:
        entry["plan_id"] = plan_id
    if extra:
        entry.update(extra)
    entry["prev_sha256"] = prev_sha  # None for the first entry — genesis
    entry["entry_sha256"] = _line_digest(entry)
    with JOURNAL.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    _chmod()
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


def verify_chain() -> tuple[bool, list[str]]:
    """Check the tamper-evident hash chain. Returns (ok, problems).

    Every entry's entry_sha256 must match its own content, and its
    prev_sha256 must equal the previous entry's entry_sha256. Pre-chain
    (Rev 16) entries have no hashes — they are reported as 'legacy' rather
    than failing the check, and the chain resumes at the first entry that
    carries one."""
    problems: list[str] = []
    entries = read_all()
    last_sha: str | None = None
    chained_seen = False
    for e in entries:
        if "entry_sha256" not in e:
            if chained_seen:
                problems.append(f"entry {e.get('id')}: unchained entry after the chain began")
            continue
        chained_seen = True
        if _line_digest(e) != e.get("entry_sha256"):
            problems.append(f"entry {e.get('id')}: content does not match its hash (edited?)")
        if last_sha is not None and e.get("prev_sha256") != last_sha:
            problems.append(f"entry {e.get('id')}: prev_sha256 mismatch "
                            f"(entry removed or reordered?)")
        last_sha = e.get("entry_sha256")
    return (not problems), problems


def render(entries: list[dict] | None = None) -> str:
    """Human-readable journal for the CLI."""
    entries = entries if entries is not None else read_all()
    if not entries:
        return "(journal is empty — no actions applied yet)"
    lines = []
    for e in entries:
        undo = e.get("undo")
        undo_s = f"{undo['action']} {undo['target']}" if undo else "(none)"
        mark = "\u2713" if e.get("verified") else ("\u00b7" if e.get("result") == "dry-run" else "!")
        lines.append(
            f"{e['id']:3} {mark} {e['t']}  {e['witness']:5} {e['action']:16} "
            f"{str(e['target'])[:34]:34}  undo={undo_s}"
        )
        if e.get("reason"):
            lines.append(f"      reason: {e['reason']}")
        if e.get("plan_id"):
            lines.append(f"      plan  : {e['plan_id']}")
    return "\n".join(lines)
