#!/usr/bin/env python3
"""RMAgent red-team drill — stage living-off-the-land artifacts on WS1/WS2,
then run rmagent to see what it detects. Reports to Telegram + stdout.

A DRILL, not a real attack. Benign payloads, RMAgentDrill_* prefixed, reversible.

Modes:
  stage    stage the drill artifacts on the estate
  clean    remove every RMAgentDrill_* artifact (idempotent)
  run      the full loop: stage -> rmagent census+hunt -> score -> telegram -> clean

Usage:
  python3 redteam.py run   --inventory estate.yaml --confirm
  python3 redteam.py stage --inventory estate.yaml --confirm
  python3 redteam.py clean --inventory estate.yaml

Credentials come from env (RMAgent_<ID>_USER/PASS) or the scrt secrets store
(windows-server1-password / windows-server2-password), same as rmagent.
Telegram token/chat come from scrt (telegram-bot-token / telegram-chat-id) or env.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, time
from pathlib import Path

RMA = Path.home() / ".claude" / "skills" / "rmagent-windows" / "scripts"
sys.path.insert(0, str(RMA))
import lib as rma  # noqa: E402 — reuse the rmagent engine

SKILL_DIR = Path(__file__).resolve().parents[1]
QDIR = SKILL_DIR / "scripts" / "questions" / "windows"

# --- scrt secrets (token/chat/windows passwords) -------------------------------
# Cross-platform: the scrt master password is resolved from SCRT_PASS env var,
# then macOS Keychain (macOS only), then ~/.scrt_pass file (Linux/Windows fallback).
SCRT_STORE = os.environ.get(
    "SCRT_STORE", str(Path.home() / ".claude" / "skills" / "secrets" / "connectors.scrt")
)
import sys as _sys

def _resolve_store() -> str:
    """Return the first existing scrt store among known locations (env + defaults)."""
    cands = [SCRT_STORE,
             str(Path.home() / ".claude" / "skills" / "secrets" / "connectors.scrt"),
             str(Path.home() / ".pi" / "agent" / "skills" / "secrets" / "connectors.scrt"),
             str(Path.home() / ".pi" / "agent" / "skills-2" / "secrets" / "connectors.scrt")]
    for c in cands:
        if c and Path(c).exists():
            return c
    return SCRT_STORE  # last resort; scrt will report the error

def _scrt_master_password() -> str | None:
    """Resolve the scrt master password cross-platform (env → macOS Keychain → file)."""
    pw = os.environ.get("SCRT_PASS")
    if pw:
        return pw.strip()
    if _sys.platform == "darwin":
        try:
            r = subprocess.run(
                ["security", "find-generic-password", "-s", "scrt-connectors-store", "-w"],
                capture_output=True, text=True, timeout=10)
            v = r.stdout.strip()
            if v and r.returncode == 0:
                return v
        except Exception:
            pass
    passfile = Path(os.environ.get("SCRT_PASS_FILE", str(Path.home() / ".scrt_pass")))
    try:
        if passfile.exists():
            return passfile.read_text().splitlines()[0].strip()
    except Exception:
        pass
    return None

def _scrt(key: str) -> str | None:
    """Read a secret from scrt; master password from env / Keychain / ~/.scrt_pass."""
    pw = _scrt_master_password()
    if not pw:
        return None
    try:
        r = subprocess.run(
            ["scrt", "get", "--password", pw, "--storage", "local",
             "--local-path", _resolve_store(), key],
            capture_output=True, text=True, timeout=15)
        v = r.stdout.strip()
        return v if v and "Error" not in v else None
    except Exception:
        return None

def ensure_creds(rows: list[dict]) -> None:
    """If env creds are missing, load Windows passwords from scrt into env."""
    rid_map = {"ws1": "windows-server1-password", "ws2": "windows-server2-password"}
    for r in rows:
        rid = (r.get("id") or "").upper()
        if not os.environ.get(f"RMAgent_{rid}_PASS"):
            sec = _scrt(rid_map.get(r.get("id"), ""))
            if sec:
                os.environ[f"RMAgent_{rid}_USER"] = os.environ.get(
                    f"RMAgent_{rid}_USER", "Administrator")
                os.environ[f"RMAgent_{rid}_PASS"] = sec

# --- WinRM run a payload on one row --------------------------------------------
def run_payload(row: dict, name: str, timeout: int = 60) -> dict:
    path = QDIR / f"{name}.ps1"
    if not path.exists():
        return {"ok": False, "error": f"no payload {path.name}"}
    creds = rma.creds_for(row)
    # the drill payloads are self-contained (no $Track preamble needed)
    try:
        import winrm
        endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
        s = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                          transport=row.get("transport") or "ntlm")
        r = s.run_ps(path.read_text())
        out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else (r.std_out or "")
        if r.status_code != 0:
            err = r.std_err.decode("utf-8", "replace") if isinstance(r.std_err, bytes) else (r.std_err or "")
            return {"ok": False, "error": (err or out)[-400:]}
        # parse, tolerating a banner
        out = out.strip()
        try:
            return {"ok": True, "data": json.loads(out)}
        except json.JSONDecodeError:
            i = out.find("{")
            if i > 0:
                try:
                    return {"ok": True, "data": json.loads(out[i:])}
                except json.JSONDecodeError:
                    pass
            return {"ok": True, "data": {"raw": out[:1000]}}
    except Exception as e:
        return {"ok": False, "error": str(e).split("\n")[0][:300]}

# --- Telegram ------------------------------------------------------------------
def telegram_send(text: str) -> bool:
    token = os.environ.get("RMAgent_TELEGRAM_TOKEN") or _scrt("telegram-bot-token")
    chat = os.environ.get("RMAgent_TELEGRAM_CHAT") or _scrt("telegram-chat-id")
    if not token or not chat:
        return False
    try:
        import urllib.request, urllib.parse
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text,
             "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False

# --- scoring: did rmagent see the staged artifacts? -----------------------------
# BUG FIX (2026-08-19): the scorer used to count ANY 4625 / ANY new service / ANY new
# task as "detected" — including real attack traffic (ws1 is brute-forced every ~2min
# from 95.142.115.12) and drill leftovers from earlier runs. It now (a) only scores
# signals the drill VERIFIED it staged on that box, and (b) for new_local_admin only
# counts names containing RMAgentDrill (not leftover SIDs of already-deleted users).
EXPECTED = {
    "failed_admin_logons":   "attest/sketch  (4625 admin failed)",
    "new_local_admin":       "explain.identity_changes / sketch.new_local_admins (4720+4732)",
    "new_scheduled_task":    "explain.task_events / sketch.new_tasks (4698)",
    "new_service":           "explain.service_events / sketch.new_services (7045)",
    "powershell_spawns":     "explain.proc_spawns (4688, if audited)",
    "system_outbound_conn":  "netedges (Sysmon EID3 ring: SYSTEM-owned to 1.1.1.1:80)",
    "run_key":               "attackmap (T1547.001: registry Run key persistence)",
    "ifeo_hijack":           "attackmap (T1546.010: IFEO debugger hijack)",
}

def score(rows: list[dict], census_out: str, hunt_case_dir: Path,
          staged_verified: dict[str, set[str]] | None = None) -> dict:
    """Ask rmagent's OWN questions what it saw, vs what we VERIFIED we staged.

    staged_verified maps signal -> set of witness ids where the drill confirmed the
    artifact actually landed. Signals not in it (or not staged on that box) can never
    be counted as detected — that was the old false-positive path."""
    found = {}
    staged_verified = staged_verified or {}

    # EXPECTED signal name → key the drill's `verified` dict uses (they differ:
    # 'failed_admin_logons' vs drill's 'failed_logons', 'new_scheduled_task' vs
    # drill's 'scheduled_task'). system_outbound_conn is derived from the task.
    DRILL_KEY = {
        "failed_admin_logons": "failed_logons",
        "new_local_admin": "new_local_admin",
        "new_scheduled_task": "scheduled_task",
        "new_service": "new_service",
        "powershell_spawns": "powershell_spawns",
        "system_outbound_conn": "scheduled_task",
        "run_key": "run_key",
        "ifeo_hijack": "ifeo_hijack",
    }

    def staged_on(sig: str, wid: str) -> bool:
        """Was this signal verified as staged on this witness?"""
        return wid in staged_verified.get(DRILL_KEY.get(sig, sig), set())

    # --- sketch per box: the 'anything odd' question catches new admins/services/tasks/failures ---
    print("[redteam] scoring: asking rmagent sketch on each box...")
    for r in rows:
        wid = r.get("id")
        try:
            creds = rma.creds_for(r)
        except SystemExit:
            print(f"  {wid:6} sketch: no creds")
            continue
        sk = rma.ask(r, "sketch", since_hours=1, limit=50, creds=creds)
        if not (sk.get("ok") and sk.get("data")):
            print(f"  {wid:6} sketch: HOLE — {(sk.get('error') or '')[:60]}")
            continue
        d = sk["data"]
        nla = d.get("new_local_admins") or []
        nsv = d.get("new_services") or 0
        ntk = d.get("new_tasks") or 0
        nfl = d.get("admin_failed") or 0
        print(f"  {wid:6} sketch: failed={nfl} new_admins={nla} new_svcs={nsv} new_tasks={ntk}")
        # only count names that are actually the drill user (not leftover SIDs of
        # already-deleted users from earlier runs — those resolve to raw SIDs)
        if staged_on("failed_admin_logons", wid) and nfl:
            found["failed_admin_logons"] = True
        if staged_on("new_local_admin", wid) and \
                [a for a in nla if "RMAgentDrill" in str(a)]:
            found["new_local_admin"] = True
        if staged_on("new_service", wid) and nsv:
            found["new_service"] = True
        if staged_on("new_scheduled_task", wid) and ntk:
            found["new_scheduled_task"] = True

    # --- netedges per box: the Sysmon EID3 RING catches transient SYSTEM-owned conns ---
    # (edges is point-in-time and misses sub-second connections; netedges reads the ring)
    print("[redteam] scoring: asking rmagent netedges (Sysmon ring) on each box...")
    for r in rows:
        wid = r.get("id")
        if "netedges" not in (r.get("skills") or []):
            continue
        try:
            creds = rma.creds_for(r)
        except SystemExit:
            continue
        ne = rma.ask(r, "netedges", since_hours=1, limit=100, creds=creds)
        if not (ne.get("ok") and ne.get("data")):
            print(f"  {wid:6} netedges: HOLE — {(ne.get('error') or '')[:60]}")
            continue
        conns = ne["data"].get("conns") or []
        drill_conns = [c for c in conns if "1.1.1.1" in str(c.get("dest")) or "RMAgentDrill" in str(c.get("proc"))]
        print(f"  {wid:6} netedges: {len(conns)} SYSTEM/Admin-owned conns in ring "
              f"({len(drill_conns)} to 1.1.1.1 or drill-tagged)")
        if drill_conns:
            found["system_outbound_conn"] = True

    # --- attackmap per box: the STATE check catches registry persistence (T1547.001, T1546.010) ---
    print("[redteam] scoring: asking rmagent attackmap (state check) on each box...")
    for r in rows:
        wid = r.get("id")
        if "attackmap" not in (r.get("skills") or []):
            continue
        try:
            creds = rma.creds_for(r)
        except SystemExit:
            continue
        am = rma.ask(r, "attackmap", since_hours=1, limit=20, creds=creds)
        if not (am.get("ok") and am.get("data")):
            print(f"  {wid:6} attackmap: HOLE — {(am.get('error') or '')[:60]}")
            continue
        findings = am["data"].get("findings") or []
        run_key_hit = [f for f in findings if f.get("n") == "run_keys"
                       and any("RMAgentDrill" in str(v) for v in (f.get("v") or []))]
        ifeo_hit = [f for f in findings if f.get("n") == "ifeo_dbg"
                    and any("RMAgentDrill" in str(v) for v in (f.get("v") or []))]
        print(f"  {wid:6} attackmap: {len(findings)} techniques with findings "
              f"(run_key drill: {bool(run_key_hit)}, ifeo drill: {bool(ifeo_hit)})")
        if run_key_hit:
            found["run_key"] = True
        if ifeo_hit:
            found["ifeo_hijack"] = True

    # --- hunt explain hops: proc_spawns + service/task/group events ---
    # (only signals we verified we staged — otherwise real background activity
    #  like routine service restarts would count as drill detections)
    pj = hunt_case_dir / "path.json"
    if pj.exists():
        try:
            for h in json.loads(pj.read_text()):
                wid = h.get("witness")
                if h.get("skill") == "explain":
                    if staged_on("new_service", wid) and h.get("service_events", 0):
                        found["new_service"] = True
                    if staged_on("new_scheduled_task", wid) and h.get("task_events", 0):
                        found["new_scheduled_task"] = True
                    if staged_on("new_local_admin", wid) and \
                            (h.get("group_changes", 0) or h.get("identity_changes", 0)):
                        found["new_local_admin"] = True
                    if staged_on("powershell_spawns", wid) and h.get("proc_spawns", 0):
                        found["powershell_spawns"] = True
        except Exception:
            pass
    return found

# --- modes ---------------------------------------------------------------------
def stage(rows):
    """Stage the drill and return {signal -> set(witness ids)} for signals VERIFIED staged."""
    print(f"[redteam] staging drill on {len(rows)} box(es): {[r['id'] for r in rows]}")
    results = []
    verified: dict[str, set[str]] = {}
    for r in rows:
        res = run_payload(r, "drill", timeout=120)
        ok = res.get("ok")
        data = res.get("data") or {}
        v = data.get("verified") or {}
        print(f"  {r['id']:6} {'ok' if ok else 'FAIL'} — staged={data.get('staged', res.get('error'))}")
        print(f"  {r['id']:6}          verified={v}")
        for sig, landed in (v.items() if isinstance(v, dict) else []):
            if landed:
                verified.setdefault(sig, set()).add(r["id"])
        results.append((r["id"], res))
    return results, verified

def clean(rows):
    print(f"[redteam] cleaning drill artifacts on {len(rows)} box(es)")
    all_clean = True
    for r in rows:
        res = run_payload(r, "clean", timeout=90)
        ok = res.get("ok")
        data = res.get("data") or {}
        still = data.get("still_present") or []
        if still:
            all_clean = False
        print(f"  {r['id']:6} {'cleaned' if ok else 'FAIL'} — {data.get('cleaned', res.get('error'))}"
              + (f"  ⚠ STILL PRESENT: {still}" if still else ""))
    return all_clean

def run_full(rows, inventory, keep_dirty: bool):
    case_root = Path("./cases")
    case_root.mkdir(parents=True, exist_ok=True)
    case_dir = case_root / f"redteam-{time.strftime('%Y%m%d-%H%M%S')}"
    case_dir.mkdir(parents=True, exist_ok=True)

    telegram_send(f"🛰️ RMAgent red-team drill started\nStaging LOTL artifacts on "
                  f"{len(rows)} box(es): {[r['id'] for r in rows]}\n"
                  f"Expect: {', '.join(EXPECTED.keys())}")

    _, staged_verified = stage(rows)
    print("[redteam] waiting 8s for events to settle in the logs...")
    time.sleep(8)

    # run rmagent census + hunt
    census = subprocess.run(
        [sys.executable, str(RMA / "census.py"), "--inventory", inventory,
         "--case-dir", str(case_dir)],
        capture_output=True, text=True)
    census_out = census.stdout
    print("--- census ---"); print(census_out)

    hunt = subprocess.run(
        [sys.executable, str(RMA / "hunt.py"), "--inventory", inventory,
         "--since", "1h", "--case-dir", str(case_dir), "--limit", "8"],
        capture_output=True, text=True)
    print("--- hunt ---"); print(hunt.stdout)

    found = score(rows, census_out, case_dir, staged_verified)
    detected = list(found.keys())
    missed = [k for k in EXPECTED if k not in found]

    # distinguish "not staged" (drill couldn't create it — env limitation) from
    # "not detected" (rmagent missed something that WAS staged). A signal counts
    # as staged if it landed on at least one box.
    _DRILL_KEY = {
        "failed_admin_logons": "failed_logons",
        "new_local_admin": "new_local_admin",
        "new_scheduled_task": "scheduled_task",
        "new_service": "new_service",
        "powershell_spawns": "powershell_spawns",
        "system_outbound_conn": "scheduled_task",
        "run_key": "run_key",
        "ifeo_hijack": "ifeo_hijack",
    }
    def _staged_anywhere(sig: str) -> bool:
        return bool(staged_verified.get(_DRILL_KEY.get(sig, sig)))

    not_staged = [k for k in EXPECTED if not _staged_anywhere(k)]
    not_detected = [k for k in missed if _staged_anywhere(k)]

    WHY = {
        "new_local_admin": "4732 needs 'Audit Security Group Management' on; sketch's regex may miss workgroup-format names",
        "new_scheduled_task": "4698 needs 'Audit Other Object Access Events' on (off by default)",
        "powershell_spawns": "4688 needs 'Audit Process Creation' on (off by default)",
        "system_outbound_conn": "netedges (Sysmon EID3 ring) missed it — check Sysmon NetworkConnect config is on",
        "failed_admin_logons": "4625 needs 'Audit Logon' failure auditing ON (ws2 has it OFF — run: auditpol /set /subcategory:\"Logon\" /failure:enable)",
        "new_service": "7045 needs no extra audit policy; check the service was created",
        "run_key": "attackmap needs the run_key check; verify the registry value was created (HKLM Run key)",
        "ifeo_hijack": "attackmap needs the ifeo_dbg check; verify the IFEO Debugger value was created",
    }
    summary = (f"✅ RMAgent drill — detection report\n"
               f"Detected ({len(detected)}/{len(EXPECTED)}):\n"
               + ("".join(f"  • {k} — {EXPECTED[k]}\n" for k in detected) or "  (none)\n"))
    if not_staged:
        summary += (f"\nNot staged ({len(not_staged)}) — environment limitation, not a rmagent miss:\n"
                    + "".join(f"  • {k} — {WHY.get(k, EXPECTED[k])}\n" for k in not_staged))
    if not_detected:
        summary += (f"\nNot detected ({len(not_detected)}) — staged but rmagent missed:\n"
                    + "".join(f"  • {k} — {WHY.get(k, EXPECTED[k])}\n" for k in not_detected))
    if not missed:
        summary += "\nFull coverage. 🎯"
    summary += f"\nCase: {case_dir.name}"
    print("\n" + summary)
    ok = telegram_send(summary)
    print(f"[telegram] report sent: {ok}")

    # --- score history (Rev 8): persist N/8 over time for regression detection.
    # A Windows update or GPO change that silently disables 4688 shows as a
    # score drop here — the failure mode the drill doc itself warns about.
    try:
        hist_file = Path.home() / ".rmagent" / "drill_history.jsonl"
        hist_file.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "case": case_dir.name,
            "detected": len(detected),
            "total": len(EXPECTED),
            "detected_signals": detected,
            "not_detected": not_detected,
            "not_staged": not_staged,
        }
        with hist_file.open("a") as f:
            f.write(json.dumps(rec) + "\n")
        # regression check vs the previous run
        lines = [l for l in hist_file.read_text().splitlines() if l.strip()]
        if len(lines) >= 2:
            prev = json.loads(lines[-2])
            prev_n, now_n = prev.get("detected", 0), len(detected)
            if now_n < prev_n:
                drop = sorted(set(prev.get("detected_signals") or []) - set(detected))
                msg = (f"📉 RMAgent drill REGRESSION: {prev_n}/{len(EXPECTED)} -> {now_n}/{len(EXPECTED)}.\n"
                       f"Lost: {', '.join(drop)}\n"
                       f"Likely: an audit policy / GPO / Windows update disabled a log source.")
                print(f"[history] {msg}")
                telegram_send(msg)
            else:
                print(f"[history] score {now_n}/{len(EXPECTED)} (prev {prev_n}/{len(EXPECTED)}) — no regression")
    except Exception as e:
        print(f"[history] score-history write failed (non-fatal): {e}")

    if not keep_dirty:
        print("\n[redteam] cleaning up staged artifacts...")
        all_clean = clean(rows)
        telegram_send("🧹 Drill artifacts cleaned. Estate restored."
                      if all_clean else
                      "⚠️ Drill cleanup INCOMPLETE — artifacts still present! Check still_present in output.")
    else:
        print("\n[redteam] keeping artifacts (--keep). Clean later with: redteam.py clean")

    print(f"\n[redteam] done. case: {case_dir}")
    return detected, missed

def main():
    ap = argparse.ArgumentParser(description="RMAgent red-team drill")
    ap.add_argument("mode", choices=["stage", "clean", "run"])
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--confirm", action="store_true",
                    help="required for stage/run — this is a drill that changes hosts")
    ap.add_argument("--keep", action="store_true", help="don't clean after run")
    ap.add_argument("--target", help="only this witness id")
    args = ap.parse_args()

    if args.mode in ("stage", "run") and not args.confirm:
        sys.exit("This stages artifacts on production hosts. Re-run with --confirm.")

    inv = rma.load_inventory(args.inventory)
    rows = rma.witnesses(inv)
    if args.target:
        rows = [r for r in rows if r.get("id") == args.target]
    if not rows:
        sys.exit("no witnesses matched")

    ensure_creds(rows)

    if args.mode == "stage":
        stage(rows)
    elif args.mode == "clean":
        ok = clean(rows)
        if not ok:
            sys.exit(1)
    elif args.mode == "run":
        run_full(rows, args.inventory, args.keep)

if __name__ == "__main__":
    main()
