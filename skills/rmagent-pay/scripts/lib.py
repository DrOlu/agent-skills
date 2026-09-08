#!/usr/bin/env python3
"""rmagent-pay engine — pull one payment hop. Lake-less. PCI on the device.

Doors:
  fixture  — local JSONL samples (this tree). No network. Makes the skill runnable.
  winrm / psrp — Windows Postilion (reuses rmagent-so transport).
  ssh      — Linux/AIX Finacle (stdin script, no 8191 budget).

Credentials: never in the inventory. env RMAgent_<ID>_USER/_PASS or ~/.rmagent/creds.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

try:
    import winrm
except ImportError:
    winrm = None
try:
    from pypsrp.client import Client as _psrp_client
    from pypsrp.powershell import PowerShell as _psrp_ps, RunspacePool as _psrp_pool
    pypsrp = True
except ImportError:
    pypsrp = None

SKILL_DIR = Path(__file__).resolve().parents[1]
QDIR = SKILL_DIR / "scripts" / "questions"
FIXDIR = SKILL_DIR / "examples" / "fixtures"

ALLOWED = {
    "pay_attest", "switch_txn", "core_auth", "pay_sketch", "hop_delta",
}
MAX_PULL_BYTES = 32 * 1024
ASK_TIMEOUT_SEC = 25
COOLDOWN_SEC = 5 * 60
DEFAULT_TRANSPORT = "ntlm"
PCI_FORBIDDEN = ("pin", "pinblock", "track2", "track_2", "cvv", "full_pan")

_CREDS_FILE = Path.home() / ".rmagent" / "creds.json"
_SILENT_FILE = Path.home() / ".rmagent" / "silent.json"
_CRED_CACHE: dict[str, dict] = {}


def hole(where: str, why: str) -> dict:
    return {"where": where, "why": why[:400], "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


def load_inventory(path: str) -> dict:
    p = Path(path)
    text = p.read_text()
    if p.suffix == ".json":
        return json.loads(text)
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        raise SystemExit("Install pyyaml or pass a .json inventory")


def witnesses(inv: dict) -> list[dict]:
    return list(inv.get("witnesses") or inv.get("hosts") or [])


def find(inv: dict, wid: str) -> dict | None:
    for r in witnesses(inv):
        if r.get("id") == wid:
            return r
    return None


def creds_for(row: dict) -> dict:
    rid = (row.get("id") or "").upper()
    if rid in _CRED_CACHE:
        return _CRED_CACHE[rid]
    user = os.environ.get(f"RMAgent_{rid}_USER") or row.get("user") or "Administrator"
    pw = os.environ.get(f"RMAgent_{rid}_PASS")
    if not pw and _CREDS_FILE.exists():
        try:
            data = json.loads(_CREDS_FILE.read_text())
            entry = data.get(row.get("id")) or data.get(rid.lower())
            if isinstance(entry, dict):
                pw = entry.get("password")
                user = entry.get("user") or user
            elif isinstance(entry, str):
                pw = entry
        except (json.JSONDecodeError, OSError):
            pass
    if not pw:
        raise SystemExit(f"No credential for {row.get('id')}. Env or {_CREDS_FILE} (mode 600).")
    creds = {"user": user, "password": pw}
    _CRED_CACHE[rid] = creds
    return creds


def mark_silent(wid: str, why: str) -> None:
    try:
        state = json.loads(_SILENT_FILE.read_text()) if _SILENT_FILE.exists() else {}
        state[wid] = {"t": time.time(), "why": (why or "")[:200]}
        _SILENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _SILENT_FILE.write_text(json.dumps(state))
        _SILENT_FILE.chmod(0o600)
    except Exception:
        pass


def cooldown_left(wid: str) -> float:
    try:
        if not _SILENT_FILE.exists():
            return 0.0
        rec = json.loads(_SILENT_FILE.read_text()).get(wid) or {}
        return max(0.0, COOLDOWN_SEC - (time.time() - float(rec.get("t") or 0)))
    except Exception:
        return 0.0


def clear_silent(wid: str) -> None:
    try:
        if not _SILENT_FILE.exists():
            return
        state = json.loads(_SILENT_FILE.read_text())
        state.pop(wid, None)
        _SILENT_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def mask_pan(pan: str | None) -> str | None:
    if not pan:
        return None
    if "*" in str(pan):
        return str(pan)
    d = "".join(c for c in str(pan) if c.isdigit())
    if len(d) < 10:
        return "****"
    return d[:6] + "*" * (len(d) - 10) + d[-4:]


def pci_scrub(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = k.lower()
            if kl in PCI_FORBIDDEN:
                continue
            if kl in ("pan", "card", "account"):
                out[k] = mask_pan(str(v) if v is not None else None)
            else:
                out[k] = pci_scrub(v)
        return out
    if isinstance(obj, list):
        return [pci_scrub(x) for x in obj]
    return obj


def _parse(stdout: str) -> dict:
    stdout = (stdout or "").strip()
    if not stdout:
        return {"ok": False, "error": "empty answer", "hole": hole("parse", "empty")}
    try:
        return {"ok": True, "data": json.loads(stdout)}
    except json.JSONDecodeError:
        i = stdout.find("{")
        if i >= 0:
            try:
                return {"ok": True, "data": json.loads(stdout[i:])}
            except json.JSONDecodeError:
                pass
        return {"ok": False, "error": "unparseable answer",
                "hole": hole("parse", "not JSON; first 400: " + stdout[:400])}


def _cap(parsed: dict) -> dict:
    """Bound the answer to MAX_PULL_BYTES. REV 20 (P0): trim rows, then
    RE-MEASURE the serialized result — the old code trimmed once and returned
    without re-checking, so a 32 KB single row (or a big envelope) could still
    pass through, and the cap_note lied about the final size."""
    if not parsed.get("ok"):
        return parsed
    data = parsed.get("data") or {}
    trimmed = False
    for key in ("rows", "txns", "hits"):
        if isinstance(data.get(key), list) and len(data[key]) > 3:
            data = dict(data)
            data[key] = data[key][:3]
            data["capped"] = True
            data["cap_note"] = "trimmed to 3 rows (32 KB)"
            parsed["data"] = data
            parsed["capped"] = True
            trimmed = True
    # re-measure the COMPLETE serialized answer (envelope + diagnostics included)
    if len(json.dumps(parsed, default=str).encode()) <= MAX_PULL_BYTES:
        return parsed
    # still over cap → the honest answer is a hole, not a truncated lie
    parsed["ok"] = False
    parsed["error"] = "answer exceeded 32 KB even after row trim"
    parsed["hole"] = hole("cap", "answer > 32 KB after trim")
    parsed["data"] = None
    return parsed


def _strip_payload(text: str) -> str:
    return "\n".join(l.rstrip() for l in text.splitlines()
                     if l.strip() and not l.strip().startswith("#"))


def _ticket_preamble(row: dict, since_hours: float, limit: int, ticket: str) -> str:
    art = (row.get("artifacts") or {})
    iso = str(art.get("iso_trace") or art.get("auth_log") or "").replace("'", "''")
    t = (ticket or "").replace("'", "''")
    return (
        f"$ErrorActionPreference='SilentlyContinue'\n"
        f"$SinceHours = {float(since_hours)}\n"
        f"$Limit = {int(limit)}\n"
        f"$Ticket = '{t}'\n"
        f"$Artifact = '{iso}'\n"
    )


def _sh_preamble(row: dict, since_hours: float, limit: int, ticket: str) -> str:
    art = (row.get("artifacts") or {})
    iso = str(art.get("iso_trace") or art.get("auth_log") or "").replace("'", "'\\''")
    t = (ticket or "").replace("'", "'\\''")
    return (
        f"SINCE_HOURS={float(since_hours)}\n"
        f"LIMIT={int(limit)}\n"
        f"TICKET='{t}'\n"
        f"ARTIFACT='{iso}'\n"
    )


def _ask_fixture(row: dict, skill: str, ticket: str, since_hours: float, limit: int) -> dict:
    name = (row.get("fixture") or row.get("id") or "demo")
    path = FIXDIR / f"{name}.jsonl"
    if not path.exists():
        return {"ok": False, "error": f"no fixture {path.name}",
                "hole": hole(f"{row.get('id')} {skill}", f"missing {path.name}")}
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    role = (row.get("role") or "").lower()
    now = time.time()
    cutoff = now - since_hours * 3600

    def ts_ok(r):
        for k in ("in_ts", "recv_ts", "t"):
            v = r.get(k)
            if not v:
                continue
            try:
                from datetime import datetime
                tt = datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
                return tt >= cutoff
            except Exception:
                return True
        return True

    def match_ticket(r):
        if not ticket:
            return True
        t = ticket.upper().replace("RRN-", "").replace("STAN-", "")
        for k in ("rrn", "stan", "terminal_id"):
            if str(r.get(k) or "").upper() == t or str(r.get(k) or "").upper().endswith(t):
                return True
        return False

    vis = {
        "artifact_exists": True,
        "has_stan": any(r.get("stan") for r in rows),
        "has_rrn": any(r.get("rrn") for r in rows),
        "n_rows": len(rows),
        "oldest": (rows[0].get("in_ts") or rows[0].get("recv_ts")) if rows else None,
        "blind": False,
    }
    vis["blind"] = not (vis["has_stan"] or vis["has_rrn"])

    if skill == "pay_attest":
        return {"ok": True, "data": {"skill": "pay_attest", "host": row.get("id"),
                                     "role": role, **vis}}

    hits = [r for r in rows if ts_ok(r) and match_ticket(r)][:limit]

    if skill == "pay_sketch":
        rcs = {}
        for r in hits:
            rc = str(r.get("rc") or r.get("response_code") or "?")
            rcs[rc] = rcs.get(rc, 0) + 1
        return {"ok": True, "data": {"skill": "pay_sketch", "host": row.get("id"),
                                     "n": len(hits), "by_rc": rcs, "timeouts": rcs.get("91", 0) + rcs.get("68", 0)}}

    if skill == "switch_txn":
        if role not in ("fep", "switch", "postilion", ""):
            return {"ok": True, "data": {"skill": "switch_txn", "host": row.get("id"),
                                         "rows": [], "note": "not a switch hop"}}
        if vis["blind"]:
            return {"ok": False, "error": "artifact has no STAN/RRN",
                    "hole": hole(f"{row.get('id')} switch_txn", "blind-witness")}
        out = []
        for r in hits:
            out.append({
                "stan": r.get("stan"), "rrn": r.get("rrn"),
                "terminal_id": r.get("terminal_id"),
                "in_ts": r.get("in_ts"), "out_ts": r.get("out_ts"),
                "rc": r.get("rc") or r.get("response_code"),
                "mti": r.get("mti"),
                "pan": mask_pan(r.get("pan")),
            })
        return {"ok": True, "data": {"skill": "switch_txn", "host": row.get("id"), "rows": out}}

    if skill == "core_auth":
        if role not in ("cba", "core", "finacle", ""):
            return {"ok": True, "data": {"skill": "core_auth", "host": row.get("id"),
                                         "rows": [], "note": "not a core hop"}}
        if vis["blind"]:
            return {"ok": False, "error": "artifact has no STAN/RRN",
                    "hole": hole(f"{row.get('id')} core_auth", "blind-witness")}
        out = []
        for r in hits:
            out.append({
                "stan": r.get("stan"), "rrn": r.get("rrn"),
                "recv_ts": r.get("recv_ts") or r.get("in_ts"),
                "post_ts": r.get("post_ts") or r.get("out_ts"),
                "rc": r.get("rc") or r.get("response_code"),
                "pan": mask_pan(r.get("pan")),
            })
        return {"ok": True, "data": {"skill": "core_auth", "host": row.get("id"), "rows": out}}

    return {"ok": False, "error": f"fixture cannot serve {skill}"}


def _ask_psrp(row: dict, script: str, timeout: int) -> dict:
    creds = creds_for(row)
    client = _psrp_client(row["address"], username=creds["user"],
                          password=creds["password"], ssl=False,
                          connection_timeout=timeout)
    with _psrp_pool(client.wsman) as pool:
        ps = _psrp_ps(pool)
        ps.add_script(script)
        res = ps.invoke()
    if getattr(ps, "had_errors", False):
        err = "; ".join(str(e) for e in (ps.stream_error or []))[:500]
        return {"ok": False, "error": err}
    out = str(res[0]) if res else ""
    return _parse(out)


def _ask_winrm(row: dict, script: str, timeout: int) -> dict:
    creds = creds_for(row)
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    transport = row.get("transport") or DEFAULT_TRANSPORT
    if transport == "psrp":
        transport = DEFAULT_TRANSPORT
    session = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                            transport=transport)
    r = session.run_ps(script)
    out = r.std_out.decode("utf-8", "replace") if isinstance(r.std_out, bytes) else (r.std_out or "")
    err = r.std_err.decode("utf-8", "replace") if isinstance(r.std_err, bytes) else (r.std_err or "")
    if r.status_code != 0:
        return {"ok": False, "error": (err or out)[-400:]}
    return _parse(out)


def _ask_ssh(row: dict, script: str, timeout: int) -> dict:
    user = row.get("user") or creds_for(row)["user"]
    host = row["address"]
    port = str(row.get("port") or 22)
    r = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
         "-p", port, f"{user}@{host}", "bash -s"],
        input=script.encode(), capture_output=True, timeout=timeout)
    out = r.stdout.decode("utf-8", "replace")
    err = r.stderr.decode("utf-8", "replace")
    if r.returncode != 0 and not out.strip().startswith("{"):
        return {"ok": False, "error": (err or out)[-400:]}
    return _parse(out)


def hop_delta(switch: dict, core: dict) -> dict:
    """Join switch_txn + core_auth on rrn/stan. Kilobytes. No re-pull."""
    srows = ((switch.get("data") or {}).get("rows") or []) if switch.get("ok") else []
    crows = ((core.get("data") or {}).get("rows") or []) if core.get("ok") else []
    idx = {}
    for r in crows:
        k = (str(r.get("rrn") or ""), str(r.get("stan") or ""))
        idx[k] = r
        if r.get("rrn"):
            idx[("rrn", str(r["rrn"]))] = r
    out = []
    from datetime import datetime

    def parse_ts(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except Exception:
            return None

    for s in srows:
        c = idx.get(("rrn", str(s.get("rrn") or ""))) or idx.get((str(s.get("rrn") or ""), str(s.get("stan") or "")))
        t_in = parse_ts(s.get("in_ts"))
        t_out = parse_ts(s.get("out_ts"))
        t_recv = parse_ts((c or {}).get("recv_ts")) if c else None
        t_post = parse_ts((c or {}).get("post_ts")) if c else None
        ingress_ms = int((t_recv - t_in).total_seconds() * 1000) if (t_in and t_recv) else None
        core_ms = int((t_post - t_recv).total_seconds() * 1000) if (t_recv and t_post) else None
        switch_ms = int((t_out - t_in).total_seconds() * 1000) if (t_in and t_out) else None
        # REV 20 (P0): absence of a core row is NOT proof the txn never reached
        # the core. If the core hop itself failed/blind/cooldowned, the only
        # honest per-hop verdict is "not-observed-at-core". "never-reached-core"
        # is reserved for the case where the core hop answered, was sighted, and
        # genuinely had no row for this grain in its window.
        core_ok = bool(core.get("ok"))
        where = "unknown"
        if c is None:
            where = "not-observed-at-core" if not core_ok else "never-reached-core"
        elif core_ms is not None and ingress_ms is not None:
            where = "finacle-posting" if core_ms >= ingress_ms else "postilion-ingress"
        elif core_ms is not None:
            where = "finacle-posting"
        out.append({
            "rrn": s.get("rrn"), "stan": s.get("stan"),
            "terminal_id": s.get("terminal_id"),
            "switch_rc": s.get("rc"), "core_rc": (c or {}).get("rc"),
            "ingress_ms": ingress_ms, "core_ms": core_ms, "switch_e2e_ms": switch_ms,
            "delay_on": where,
            "core_hop_ok": core_ok,
            "evidence_class": ("corroborated" if where in ("finacle-posting", "postilion-ingress")
                               else "candidate-association"),
        })
    term = "origin"
    if not switch.get("ok"):
        term = (switch.get("hole") or {}).get("why") or "switch-hole"
        if "blind" in str(term):
            term = "blind-witness"
    elif not srows:
        term = "no-signal"
    elif not crows and core.get("ok"):
        term = "no-signal-core"
    elif not core.get("ok"):
        term = "blind-witness" if "blind" in str((core.get("hole") or {}).get("why")) else "core-hole"
    return {"ok": True, "data": {"skill": "hop_delta", "termination": term, "hops": out}}


def ask(row: dict, skill: str, since_hours: float = 2.0, limit: int = 20,
        timeout: int = ASK_TIMEOUT_SEC, ticket: str = "", creds: dict | None = None) -> dict:
    # REV 20: explicit actuate refusal — the payments plane is watch-only.
    # Configuration changes belong to Postilion/Finacle change management,
    # never to this knock.
    if skill == "actuate":
        return {"ok": False, "error": "actuate is off (payments plane is watch-only)",
                "hole": hole(f"{row.get('id')} actuate", "watch is not actuate")}
    if skill not in ALLOWED:
        return {"ok": False, "error": f"skill not allowlisted: {skill}"}
    if skill not in (row.get("skills") or []):
        return {"ok": False, "error": f"{row.get('id')} does not advertise {skill}",
                "hole": hole(f"{row.get('id')} {skill}", "not advertised")}
    if skill == "hop_delta":
        return {"ok": False, "error": "hop_delta is local: call hop_delta(switch, core)"}

    door = (row.get("door") or "fixture").lower()
    use_psrp = door == "psrp" or (row.get("transport") or "").lower() == "psrp"

    if door == "fixture":
        parsed = _ask_fixture(row, skill, ticket, since_hours, limit)
        parsed["data"] = pci_scrub(parsed.get("data")) if parsed.get("ok") else parsed.get("data")
        return _cap(parsed)

    cd = cooldown_left(row.get("id") or "")
    if cd > 0:
        return {"ok": False, "error": f"silent-host cooldown {int(cd)}s",
                "hole": hole(f"{row.get('id')} {skill}", f"cooldown {int(cd)}s")}

    osname = (row.get("os") or ("windows" if door in ("winrm", "psrp") else "linux")).lower()
    if osname in ("windows", "win32") or door in ("winrm", "psrp"):
        payload = QDIR / "windows" / f"{skill}.ps1"
        if not payload.exists():
            return {"ok": False, "error": f"no payload {payload.name}",
                    "hole": hole(f"{row.get('id')} {skill}", "no payload")}
        script = _ticket_preamble(row, since_hours, limit, ticket) + _strip_payload(payload.read_text())
        try:
            parsed = _ask_psrp(row, script, timeout) if use_psrp else _ask_winrm(row, script, timeout)
        except Exception as e:
            msg = str(e).split("\n")[0][:300]
            mark_silent(row.get("id") or "", msg)
            return {"ok": False, "error": msg, "hole": hole(f"{row.get('id')} {skill}", msg)}
    elif door == "ssh" or osname in ("linux", "aix", "unix", "darwin"):
        payload = QDIR / "linux" / f"{skill}.sh"
        if not payload.exists():
            return {"ok": False, "error": f"no payload {payload.name}",
                    "hole": hole(f"{row.get('id')} {skill}", "no payload")}
        script = _sh_preamble(row, since_hours, limit, ticket) + "\n" + payload.read_text()
        try:
            parsed = _ask_ssh(row, script, timeout)
        except Exception as e:
            msg = str(e).split("\n")[0][:300]
            mark_silent(row.get("id") or "", msg)
            return {"ok": False, "error": msg, "hole": hole(f"{row.get('id')} {skill}", msg)}
    else:
        return {"ok": False, "error": f"door={door} not supported",
                "hole": hole(f"{row.get('id')} {skill}", f"door {door}")}

    if parsed.get("ok"):
        clear_silent(row.get("id") or "")
        parsed["data"] = pci_scrub(parsed.get("data"))
    else:
        mark_silent(row.get("id") or "", str(parsed.get("error") or "")[:200])
    return _cap(parsed)
