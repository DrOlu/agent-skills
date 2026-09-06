#!/usr/bin/env python3
"""RMAgent Actuate — Phase 1 response. Named, dry-run-first, journaled, reversible.

Usage:
  actuate.py <action> --inventory estate.yaml --witness ws1 --target X --reason "..." [--dry-run|--apply]
  actuate.py <action> ... --apply --plan <plan_id>        # the dry-run you showed
  actuate.py snapshot --inventory estate.yaml --witness ws1
  actuate.py journal
  actuate.py undo --journal-entry N --inventory estate.yaml

Actions are an ALLOWLIST. There is no arbitrary-command escape hatch. Every
mutating action requires --apply (dry-run is the default) and is journaled with
its undo. Credentials resolve exactly like rmagent-so (env -> creds.json -> scrt).

Rev 17 hardening (gap analysis 2026-09-03):
  C1  $Target is escaped AND validated per target_kind BEFORE it is sent.
      Targets are attacker-chosen strings (task/service/WMI names); an
      unvalidated target turned the response tool into the execution channel.
  C3  verify_action() parses the verifier's LAST LINE and requires it to be
      exactly VERIFIED. 'NOT_VERIFIED' used to satisfy "VERIFIED" in out.
  C4  mutating payloads run with $ErrorActionPreference='Stop' in try/catch
      (see the .ps1 files) - a failed mutation must never report success.
  C5  secrets never reach the journal: REDACT_KEYS are stripped from
      result_detail before journaling; the journal is chmod 600.
  H1  --apply requires --plan <id> naming a dry-run entry from this session
      (the operator must have SEEN the plan before it runs).
  H2  the engine (lib) is resolved from THIS skill tree first, falling back
      to the legacy rmagent-windows path - no more silently running an old
      engine. Transport default comes from the engine, not hardcoded.
  H3  journal entries carry prev_sha256 (a tamper-evident hash chain).
  M3  delete_task's undo is recreate_task (from the snapshotted XML);
      disable_wmi_sub captures the full filter/consumer/binding triple.
  M5  --precheck refuses to act on a blind witness; --postcheck re-asks the
      finding's question after apply and journals the delta.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys, time
from pathlib import Path

# ---------------------------------------------------------------- engine (H2)
# Resolve the Phase-0 engine from THIS skill tree first, so actuate always
# runs the same lib the observatory runs. Legacy fallback preserved for
# installs where rmagent-so is not present.
_HERE = Path(__file__).resolve().parent
_CANDIDATE_PATHS = [
    _HERE.parent.parent / "rmagent-so" / "scripts",
    _HERE.parent.parent / "rmagent-windows" / "scripts",
    Path.home() / ".agents" / "skills" / "rmagent-so" / "scripts",
    Path.home() / ".agents" / "skills" / "rmagent-windows" / "scripts",
    Path.home() / ".claude" / "skills" / "rmagent-windows" / "scripts",  # legacy
]
for _p in _CANDIDATE_PATHS:
    if (_p / "lib.py").exists():
        sys.path.insert(0, str(_p))
        break
sys.path.insert(0, str(_HERE))
import lib as rma  # noqa: E402 - reuse the Phase-0 engine (creds, inventory, ask)
import journal  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parents[1]
ADIR = SKILL_DIR / "scripts" / "actions" / "windows"

# ---------------------------------------------------------------- allowlist
# action -> (undo_action or None, target_kind, description)
ACTIONS = {
    "block_ip":          ("unblock_ip", "ip",      "Windows Firewall deny rule for a source IP"),
    "unblock_ip":        (None,         "ip",      "Remove an RMAgent block_ip rule"),
    "disable_user":      ("enable_user", "user",   "Disable a local account (never deletes)"),
    "enable_user":       ("disable_user", "user",  "Re-enable a disabled account"),
    "remove_admin":      ("add_admin",  "user",    "Remove an account from Administrators"),
    "add_admin":         ("remove_admin", "user",  "Add an account back to Administrators"),
    "delete_task":       ("recreate_task", "task", "Delete a scheduled task (XML snapshotted first)"),
    "recreate_task":     (None,         "task",    "Recreate a task from its journaled XML (undo of delete_task)"),
    "stop_service":      ("start_service", "svc",  "Stop + disable a service"),
    "start_service":     ("stop_service", "svc",   "Re-enable + start a service"),
    "kill_process":      (None,         "pid",     "Kill a process by PID (cmdline recorded first)"),
    "quarantine_file":   ("restore_file", "path",  "Deny-execute ACL on a file"),
    "restore_file":      ("quarantine_file", "path", "Remove the deny ACL"),
    "disable_wmi_sub":   (None,         "wmi",     "Delete a WMI event subscription (filter/consumer/binding recorded first)"),
    "plant_canary":      (None,         "user",    "Create a DISABLED decoy account (cannot log on; every attempt is still recorded as 4625)"),
    "snapshot":          (None,         "none",    "Read-only baseline of task/svc/user/firewall state"),
    "rotate_credential": (None,         "user",    "Force a random password on a local account (breaks the attacker's copy, keeps the account usable)"),
    "isolate_host":      ("un_isolate_host", "host", "Block inbound via profile default (WinRM kept open so undo works)"),
    "un_isolate_host":   (None,         "host",    "Remove the RMAgent isolation rules"),
}

PS_ACTIONS = {a for a in ACTIONS if a != "snapshot"}
WHOLE_HOST = {"isolate_host", "un_isolate_host"}

# C5: fields that must NEVER be written to the journal (or stdout logs).
REDACT_KEYS = {"new_password", "password", "secret"}

# ---------------------------------------------------------------- C1: target validation
_IP_RE = re.compile(r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$"
                    r"|^(?:[0-9a-fA-F]{0,4}:){2,7}[0-9a-fA-F]{0,4}$")
_PID_RE = re.compile(r"^\d{1,8}$")
_NAME_RE = re.compile(r"^[\w.\- ]{1,64}$")
_PATH_RE = re.compile(r"^[A-Za-z]:\\[^\n\r`'\"$;|&<>]{0,240}$")
_WMI_RE = re.compile(r"^[\w.\- ]{1,128}$")


def validate_target(target: str, kind: str) -> tuple[bool, str]:
    """Shape-check a target for its kind. Returns (ok, why_not)."""
    if kind == "none":
        return (True, "")
    if not target or not str(target).strip():
        return (False, "empty target")
    t = str(target)
    if kind == "ip":
        if not _IP_RE.match(t):
            return (False, f"not a valid IPv4/IPv6 address: {t!r}")
    elif kind == "pid":
        if not _PID_RE.match(t):
            return (False, f"not a plausible PID: {t!r}")
    elif kind in ("user", "svc"):
        if not _NAME_RE.match(t):
            return (False, f"not a valid account/service name: {t!r}")
    elif kind == "task":
        if not _NAME_RE.match(t):
            return (False, f"not a valid task name: {t!r}")
    elif kind == "path":
        if not _PATH_RE.match(t):
            return (False, f"not an absolute Windows path (no quotes/backticks/$ allowed): {t!r}")
    elif kind == "wmi":
        if not _WMI_RE.match(t):
            return (False, f"not a valid WMI object name: {t!r}")
    elif kind == "host":
        pass
    return (True, "")


def ps_quote(s: str) -> str:
    """Escape a value for a PowerShell single-quoted string (' -> '')."""
    return str(s).replace("'", "''")


def build_preamble(target: str) -> str:
    """The preamble every action payload gets. $Target is ESCAPED (C1)."""
    return (f"$ErrorActionPreference='Stop'\n"
            f"$Target = '{ps_quote(target)}'\n")


# ---------------------------------------------------------------- payloads
def load_action_script(action: str) -> str:
    p = ADIR / f"{action}.ps1"
    if not p.exists():
        raise SystemExit(f"no payload for action '{action}': {p} missing")
    return p.read_text()


def _session(row: dict):
    import winrm
    creds = rma.creds_for(row)
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    transport = row.get("transport") or getattr(rma, "DEFAULT_TRANSPORT", "basic")
    return winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                         transport=transport)


def _clean(out: str) -> str:
    return (out or "").replace("PowerShell is ready!", "").strip()


def run_action(row: dict, action: str, target: str) -> dict:
    """Run one allowlisted action payload over WinRM. Returns {ok, data|error}."""
    try:
        s = _session(row)
    except SystemExit as e:
        return {"ok": False, "error": str(e)}
    script = build_preamble(target) + load_action_script(action)
    r = s.run_ps(script)
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else (r.std_out or "")
    err = r.std_err.decode("utf-8", "replace") if isinstance(r.std_err, bytes) else (r.std_err or "")
    out = _clean(out)
    if r.status_code != 0:
        return {"ok": False, "error": (err or out)[-400:]}
    try:
        i = out.find("{")
        data = json.loads(out[i:] if i > 0 else out)
        if isinstance(data, dict) and data.get("ok") is False:
            return {"ok": False, "error": str(data.get("error") or data)[:400]}
        return {"ok": True, "data": data}
    except (json.JSONDecodeError, ValueError):
        return {"ok": True, "data": {"raw": out[:1500]}}


# ---------------------------------------------------------------- C3: verification
def parse_verify(out: str) -> bool:
    """A verifier emits exactly one token on its own final line.

    The old check was `"VERIFIED" in out`, which 'NOT_VERIFIED' also
    satisfies - every failure was being reported as a success. The last
    non-empty line must be EXACTLY 'VERIFIED'."""
    lines = [l.strip() for l in (out or "").splitlines() if l.strip()]
    return bool(lines) and lines[-1] == "VERIFIED"


def verify_action(row: dict, action: str, target: str) -> bool | None:
    """Post-apply verification. Returns True/False, or None when the action
    has no verifier (the journal records verified=False in that case)."""
    p = ADIR / f"{action}.verify.ps1"
    if not p.exists():
        return None
    try:
        s = _session(row)
    except SystemExit:
        return False
    r = s.run_ps(build_preamble(target) + p.read_text())
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else (r.std_out or "")
    return parse_verify(_clean(out))


# ---------------------------------------------------------------- C5: redaction
def redact(data, keys: set[str] = REDACT_KEYS):
    """Strip secret-bearing keys from a result before it is journaled."""
    if isinstance(data, dict):
        return {k: ("<redacted>" if k in keys else redact(v, keys)) for k, v in data.items()}
    if isinstance(data, list):
        return [redact(v, keys) for v in data]
    return data


# ---------------------------------------------------------------- M5: pre/postcheck
def precheck(row: dict) -> tuple[bool, str]:
    """Refuse to act on a witness that cannot see."""
    res = rma.ask(row, "attest", since_hours=1.0, limit=5)
    d = res.get("data") or {}
    if not res.get("ok"):
        return (False, f"attest failed: {res.get('error')}")
    blind = int(d.get("blind_count") or 0)
    if blind > 0:
        blind_list = [k for k, v in (d.get("blind_check") or {}).items()
                      if isinstance(v, str) and v.startswith("BLIND")]
        return (False, f"witness is audit-blind ({blind} subcats: {', '.join(blind_list[:4])}) "
                       f"- acting on a blind box is acting on a guess")
    return (True, "")


POSTCHECK_QUESTIONS = {
    "block_ip":         "edges",
    "unblock_ip":       "edges",
    "disable_user":     "sketch",
    "enable_user":      "sketch",
    "remove_admin":     "sketch",
    "add_admin":        "sketch",
    "rotate_credential": "sketch",
    "isolate_host":     "attest",
    "un_isolate_host":  "attest",
}


def postcheck(row: dict, action: str, target: str, since_h: float = 2.0) -> dict:
    """Re-ask the finding's source question after apply."""
    q = POSTCHECK_QUESTIONS.get(action)
    if not q:
        return {"checked": False, "why": f"no postcheck question mapped for {action}"}
    res = rma.ask(row, q, since_hours=since_h, limit=50)
    if not res.get("ok"):
        return {"checked": False, "why": f"{q} re-ask failed: {res.get('error')}"}
    d = res.get("data") or {}
    ev: dict = {"checked": True, "question": q}
    if q == "edges":
        fs = d.get("failed_sources") or []
        row_for_target = next((f for f in fs if (f.get("src") or "") == target), None)
        ev["failed_from_target"] = row_for_target or {"note": "no failures from this source in the window"}
    elif q == "sketch":
        ev["admin_failed"] = d.get("admin_failed")
        ev["new_local_admins"] = d.get("new_local_admins")
    elif q == "attest":
        ev["blind_count"] = d.get("blind_count")
        ev["sysmon_status"] = d.get("sysmon_status")
    return ev


# ---------------------------------------------------------------- H1: plan gate
def plan_id_for(witness: str, action: str, target: str) -> str:
    return hashlib.sha256(f"{witness}|{action}|{target}".encode()).hexdigest()[:12]


def _parse_ts(ts: str | None) -> float:
    try:
        from datetime import datetime, timezone
        return datetime.fromisoformat((ts or "").replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0


def find_plan(plan_id: str, max_age_min: float = 60.0) -> dict | None:
    """A valid plan is a DRY-RUN journal entry whose plan_id matches and is
    recent (the operator must have seen it)."""
    for e in reversed(journal.read_all()):
        if e.get("plan_id") == plan_id and e.get("result") == "dry-run":
            age = time.time() - _parse_ts(e.get("t"))
            if age <= max_age_min * 60:
                return e
    return None


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="RMAgent Actuate - Phase 1 response")
    ap.add_argument("action",
                    choices=sorted(ACTIONS) + ["journal", "undo", "verify"],
                    help="allowlisted action, or 'journal' / 'undo' / 'verify'")
    ap.add_argument("--inventory", help="estate inventory (required for host actions)")
    ap.add_argument("--witness", help="target witness id")
    ap.add_argument("--target", help="action target: ip / user / task / svc / pid / path / wmi")
    ap.add_argument("--reason", default="", help="why - recorded in the journal")
    ap.add_argument("--plan", default=None, help="plan id from a dry-run (required by --apply)")
    ap.add_argument("--precheck/--no-precheck", dest="precheck", default=True,
                    help="refuse to act on an audit-blind witness (default: on)")
    ap.add_argument("--force-blind", action="store_true",
                    help="override a failed precheck (you are asserting the finding is real)")
    ap.add_argument("--postcheck/--no-postcheck", dest="postcheck", default=True,
                    help="re-ask the finding's question after apply (default: on)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-run", action="store_true", default=True, help="show what would happen (default)")
    g.add_argument("--apply", action="store_true", help="actually do it (requires --plan <id>)")
    ap.add_argument("--journal-entry", type=int, help="for undo: the entry id to reverse")
    args = ap.parse_args()

    # ---- journal (verifies the hash chain on every read)
    if args.action == "journal":
        ok_c, problems = journal.verify_chain()
        if not ok_c:
            print("!! JOURNAL CHAIN BROKEN - the audit trail has been edited:")
            for p in problems:
                print(f"   {p}")
            print()
        else:
            chained = sum(1 for e in journal.read_all() if "entry_sha256" in e)
            if chained:
                print(f"# journal chain OK ({chained} chained entries)\n")
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
        print(f"  {'ok' if ok else 'FAIL'} - {res.get('data') or res.get('error')}")
        if ok:
            verified = verify_action(row, u["action"], u["target"])
            journal.append(e["witness"], f"undo:{u['action']}", u["target"],
                           f"undo of entry {args.journal_entry}: {e.get('reason','')}",
                           None, "undone", bool(verified))
            print(f"  undone. verified={verified}")
        return

    if args.action == "verify":
        if not args.journal_entry or not args.inventory:
            sys.exit("verify requires --journal-entry N --inventory ...")
        e = journal.get(args.journal_entry)
        if not e:
            sys.exit(f"no journal entry {args.journal_entry}")
        inv = rma.load_inventory(args.inventory)
        row = rma.find(inv, e["witness"])
        if not row:
            sys.exit(f"witness {e['witness']} not in inventory")
        v = verify_action(row, e["action"], e["target"])
        print(f"[verify] entry {e['id']} {e['action']} {e['target']}: "
              f"{'VERIFIED' if v else 'NOT VERIFIED'}")
        return

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

    if args.action not in WHOLE_HOST and not args.target:
        sys.exit(f"action '{args.action}' needs --target <{kind}>")
    target = args.target or "host"

    # ---- C1: validate the target BEFORE anything is sent anywhere
    ok_t, why_not = validate_target(target, kind)
    if not ok_t:
        sys.exit(f"REFUSED - invalid {kind} target: {why_not}\n"
                 f"(targets are attacker-chosen strings; a malformed target is "
                 f"refused, never sent to a host)")
    if not args.reason:
        sys.exit("refusing to act without --reason (the journal is the audit trail)")

    pid_ = plan_id_for(args.witness, args.action, target)

    # ---- dry-run: describe, journal it, stop.
    if not args.apply:
        print(f"[dry-run] {args.action} on {args.witness}")
        print(f"  target : {target}")
        print(f"  effect : {desc}")
        print(f"  undo   : {undo_action or '(none - journal records full state first)'}")
        print(f"  reason : {args.reason}")
        print(f"\n  plan id: {pid_}")
        print(f"  To apply: re-run with --apply --plan {pid_}")
        journal.append(args.witness, args.action, target, args.reason,
                       {"action": undo_action, "target": target} if undo_action else None,
                       "dry-run", plan_id=pid_)
        return

    # ---- H1: --apply requires the matching dry-run plan
    if not args.plan:
        sys.exit("REFUSED - --apply requires --plan <id> from a dry-run you have seen.\n"
                 "Run the dry-run first; it prints the plan id.")
    plan = find_plan(args.plan)
    if not plan or plan.get("witness") != args.witness or plan.get("target") != target:
        sys.exit(f"REFUSED - no matching dry-run plan {args.plan} for "
                 f"{args.witness} {args.action} {target} (plans expire after 60 min)")

    # ---- M5: precheck - never act on a box that cannot see
    if args.precheck:
        ok_p, why = precheck(row)
        if not ok_p:
            if args.force_blind:
                print(f"  [precheck] OVERRIDE - {why}")
            else:
                sys.exit(f"REFUSED - precheck failed: {why}\n"
                         f"(override with --force-blind only if you are certain "
                         f"the finding is real)")

    # ---- apply
    print(f"[apply] {args.action} on {args.witness} target={target}")
    res = run_action(row, args.action, target)
    ok = res.get("ok")
    print(f"  {'ok' if ok else 'FAIL'} - {res.get('data') or res.get('error')}")
    if not ok:
        journal.append(args.witness, args.action, target, args.reason,
                       {"action": undo_action, "target": target} if undo_action else None,
                       "failed")
        sys.exit(1)
    verified = verify_action(row, args.action, target)

    # C5: redact before journaling; the secret is printed ONCE, never stored
    detail = redact(res.get("data"))
    extra: dict = {"result_detail": detail, "plan_id": pid_}
    if isinstance(res.get("data"), dict):
        for k in REDACT_KEYS & set(res["data"]):
            print(f"  >>> ONE-TIME {k}: {res['data'][k]}  (not journaled; hand it to the owner now)")

    # M5: postcheck - did the action change what the observatory sees?
    post_ev: dict = {}
    if args.postcheck:
        post_ev = postcheck(row, args.action, target)
        if post_ev.get("checked"):
            print(f"  [postcheck] {post_ev.get('question')}: {json.dumps(redact(post_ev))[:300]}")
    if post_ev:
        extra["postcheck"] = redact(post_ev)

    entry = journal.append(args.witness, args.action, target, args.reason,
                           {"action": undo_action, "target": target} if undo_action else None,
                           "applied", bool(verified), extra=extra)
    print(f"  journal entry {entry['id']}  verified={verified}")
    if undo_action:
        print(f"  undo later with: actuate.py undo --journal-entry {entry['id']} --inventory {args.inventory}")


if __name__ == "__main__":
    main()
