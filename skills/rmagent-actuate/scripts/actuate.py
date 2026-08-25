#!/usr/bin/env python3
"""RMAgent Actuate — Phase 1 response. Named, dry-run-first, journaled, reversible.

Usage:
  actuate.py <action> --inventory estate.yaml --witness ws1 --target X --reason "..." [--dry-run|--apply]
  actuate.py snapshot --inventory estate.yaml --witness ws1
  actuate.py journal
  actuate.py undo --journal-entry N --inventory estate.yaml

Actions are an ALLOWLIST. There is no arbitrary-command escape hatch. Every
mutating action requires --apply (dry-run is the default) and is journaled with
its undo. Credentials resolve exactly like rmagent-windows (env → creds.json → scrt).
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

RMA = Path.home() / ".claude" / "skills" / "rmagent-windows" / "scripts"
sys.path.insert(0, str(RMA))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib as rma  # reuse the Phase-0 engine (creds, inventory, ask)
import journal

SKILL_DIR = Path(__file__).resolve().parents[1]
ADIR = SKILL_DIR / "scripts" / "actions" / "windows"

# ---------------------------------------------------------------- allowlist
# action -> (undo_action or None, target_kind, description)
ACTIONS = {
    "block_ip":        ("unblock_ip", "ip",      "Windows Firewall deny rule for a source IP"),
    "unblock_ip":      (None,         "ip",      "Remove an RMAgent block_ip rule"),
    "disable_user":    ("enable_user", "user",   "Disable a local account (never deletes)"),
    "enable_user":     ("disable_user", "user",  "Re-enable a disabled account"),
    "remove_admin":    ("add_admin",  "user",    "Remove an account from Administrators"),
    "add_admin":       ("remove_admin", "user",  "Add an account back to Administrators"),
    "delete_task":     (None,         "task",    "Delete a scheduled task (XML snapshotted first)"),
    "stop_service":    ("start_service", "svc",  "Stop + disable a service"),
    "start_service":   ("stop_service", "svc",   "Re-enable + start a service"),
    "kill_process":    (None,         "pid",     "Kill a process by PID (cmdline recorded first)"),
    "quarantine_file": ("restore_file", "path",  "Deny-execute ACL on a file"),
    "restore_file":    ("quarantine_file", "path", "Remove the deny ACL"),
    "disable_wmi_sub": (None,         "wmi",     "Delete a WMI event subscription (query recorded first)"),
    "snapshot":        (None,         "none",    "Read-only baseline of task/svc/user/firewall state"),
}

# actions whose payload is a pure PowerShell script taking $Target
PS_ACTIONS = {a for a in ACTIONS if a != "snapshot"}


def load_action_script(action: str) -> str:
    p = ADIR / f"{action}.ps1"
    if not p.exists():
        raise SystemExit(f"no payload for action '{action}': {p} missing")
    return p.read_text()


def run_action(row: dict, action: str, target: str) -> dict:
    """Run one allowlisted action payload over WinRM. Returns {ok, data|error}."""
    import winrm
    creds = rma.creds_for(row)
    script = load_action_script(action)
    # every action payload reads $Target
    # A1 fix: escape single quotes — a target like "x'; rm C:\ -Recurse; '" was RCE
    safe_target = str(target).replace("'", "''")
    preamble = f"$ErrorActionPreference='SilentlyContinue'\n$Target = '{safe_target}'\n"
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    s = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                      transport=row.get("transport") or "ntlm")
    r = s.run_ps(preamble + script)
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else (r.std_out or "")
    err = r.std_err.decode("utf-8", "replace") if isinstance(r.std_err, bytes) else (r.std_err or "")
    out = out.replace("PowerShell is ready!", "").strip()
    if r.status_code != 0:
        return {"ok": False, "error": (err or out)[-400:]}
    try:
        i = out.find("{")
        return {"ok": True, "data": json.loads(out[i:] if i > 0 else out)}
    except (json.JSONDecodeError, ValueError):
        return {"ok": True, "data": {"raw": out[:1500]}}


def verify_action(row: dict, action: str, target: str) -> bool:
    """Post-apply verification: run the action's verify payload if present."""
    p = ADIR / f"{action}.verify.ps1"
    if not p.exists():
        return True  # no verifier = assume ok (journal marks verified=False)
    import winrm
    creds = rma.creds_for(row)
    # A1 fix: same escaping in the verifier
    safe_target = str(target).replace("'", "''")
    preamble = f"$ErrorActionPreference='SilentlyContinue'\n$Target = '{safe_target}'\n"
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    s = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                      transport=row.get("transport") or "ntlm")
    r = s.run_ps(preamble + p.read_text())
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else (r.std_out or "")
    out = out.replace("PowerShell is ready!", "").strip()
    return "VERIFIED" in out


def main():
    ap = argparse.ArgumentParser(description="RMAgent Actuate — Phase 1 response")
    ap.add_argument("action",
                    choices=sorted(ACTIONS) + ["journal", "undo"],
                    help="allowlisted action, or 'journal' / 'undo'")
    ap.add_argument("--inventory", help="estate inventory (required for host actions)")
    ap.add_argument("--witness", help="target witness id")
    ap.add_argument("--target", help="action target: ip / user / task / svc / pid / path / wmi")
    ap.add_argument("--reason", default="", help="why — recorded in the journal")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True, help="show what would happen (default)")
    g.add_argument("--apply", action="store_true", help="actually do it (requires a seen dry-run)")
    ap.add_argument("--journal-entry", type=int, help="for undo: the entry id to reverse")
    args = ap.parse_args()

    # ---- journal / undo need no inventory
    if args.action == "journal":
        print(journal.render())
        return

    if args.action == "undo":
        if not args.journal_entry:
            sys.exit("undo requires --journal-entry N")
        e = journal.get(args.journal_entry)
        if not e:
            sys.exit(f"no journal entry {args.journal_entry}")
        if e.get("result") != "applied" or not e.get("undo"):
            sys.exit(f"entry {args.journal_entry} has no undo (result={e.get('result')})")
        if not args.inventory:
            sys.exit("undo requires --inventory")
        inv = rma.load_inventory(args.inventory)
        row = rma.find(inv, e["witness"])
        if not row:
            sys.exit(f"witness {e['witness']} not in inventory")
        u = e["undo"]
        print(f"[undo] reversing entry {args.journal_entry}: "
              f"{u['action']} {u['target']} on {e['witness']}")
        res = run_action(row, u["action"], u["target"])
        ok = res.get("ok")
        print(f"  {'ok' if ok else 'FAIL'} — {res.get('data') or res.get('error')}")
        if ok:
            verified = verify_action(row, u["action"], u["target"])
            journal.append(e["witness"], f"undo:{u['action']}", u["target"],
                           f"undo of entry {args.journal_entry}: {e.get('reason','')}",
                           None, "undone", verified)
            print(f"  undone. verified={verified}")
        return

    # ---- everything else needs inventory + witness (+ target unless snapshot)
    if not args.inventory:
        sys.exit("this action requires --inventory")
    inv = rma.load_inventory(args.inventory)
    if not args.witness:
        rows = rma.witnesses(inv)
        print("witnesses:", ", ".join(r.get("id") for r in rows))
        sys.exit("specify --witness <id>")
    row = rma.find(inv, args.witness)
    if not row:
        sys.exit(f"witness {args.witness} not in inventory")

    undo_action, kind, desc = ACTIONS[args.action]

    if args.action == "snapshot":
        res = run_action(row, "snapshot", "")
        print(f"[snapshot] {args.witness}:")
        d = res.get("data") or {}
        print(f"  tasks={len(d.get('tasks') or [])} services={len(d.get('services') or [])} "
              f"users={len(d.get('users') or [])} fw_rules={len(d.get('fw_rules') or [])}")
        journal.append(args.witness, "snapshot", "", args.reason or "baseline",
                       None, "dry-run", True,
                       extra={"snapshot": {k: len(v or []) for k, v in d.items()
                                           if isinstance(v, list)}})
        return

    if not args.target:
        sys.exit(f"action '{args.action}' needs --target <{kind}>")
    if not args.reason:
        sys.exit("refusing to act without --reason (the journal is the audit trail)")

    # ---- dry-run: describe, journal it, stop.
    if not args.apply:
        print(f"[dry-run] {args.action} on {args.witness}")
        print(f"  target : {args.target}")
        print(f"  effect : {desc}")
        print(f"  undo   : {undo_action or '(none — journal records full state first)'}")
        print(f"  reason : {args.reason}")
        print(f"\n  To apply: re-run with --apply")
        journal.append(args.witness, args.action, args.target, args.reason,
                       {"action": undo_action, "target": args.target} if undo_action else None,
                       "dry-run")
        return

    # ---- apply
    print(f"[apply] {args.action} on {args.witness} target={args.target}")
    res = run_action(row, args.action, args.target)
    ok = res.get("ok")
    print(f"  {'ok' if ok else 'FAIL'} — {res.get('data') or res.get('error')}")
    if not ok:
        journal.append(args.witness, args.action, args.target, args.reason,
                       {"action": undo_action, "target": args.target} if undo_action else None,
                       "failed")
        sys.exit(1)
    verified = verify_action(row, args.action, args.target)
    entry = journal.append(args.witness, args.action, args.target, args.reason,
                           {"action": undo_action, "target": args.target} if undo_action else None,
                           "applied", verified,
                           extra={"result_detail": res.get("data")})
    print(f"  journal entry {entry['id']}  verified={verified}")
    if undo_action:
        print(f"  undo later with: actuate.py undo --journal-entry {entry['id']} --inventory {args.inventory}")


if __name__ == "__main__":
    main()
