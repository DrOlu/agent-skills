#!/usr/bin/env python3
"""RMAgent engine — allowlisted remote ask. No arbitrary shell.

rmagent-linux is the Linux/macOS sibling of rmagent-so. REV 20: instead of
shipping a THIRD copy of the engine, this skill resolves the shared engine
from the rmagent-so tree (same constitution, same caps, same holes) and only
changes two things:

  - the door is SSH (bash payloads under questions/linux/)
  - the payload directory is questions/linux/

Everything else — allowlist, 32 KB signal-aware cap, unparseable-as-hole,
silent-host cooldown, credential resolution — comes from the shared engine so
a fix in one place is a fix everywhere.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
QDIR = SKILL_DIR / "scripts" / "questions" / "linux"

# ---- resolve the shared engine (rmagent-so preferred, windows fallback) ----
# REV 20 note: we deliberately do NOT sys.path.insert the shared dir and
# `import lib` — that re-imports THIS module (circular). Instead the shared
# file is loaded explicitly under a private module name.
import importlib.util as _ilu


def _load_shared():
    for _p in _CANDIDATES:
        f = _p / "lib.py"
        if f.exists():
            spec = _ilu.spec_from_file_location("_rmagent_shared_lib", f)
            m = _ilu.module_from_spec(spec)
            spec.loader.exec_module(m)
            return m
    raise ImportError("shared rmagent engine (lib.py) not found in any rmagent tree")


_SHARED_DIRS = [
    SKILL_DIR.parent / "rmagent-so" / "scripts",
    Path.home() / ".agents" / "skills" / "rmagent-so" / "scripts",
    Path.home() / ".agents" / "skills" / "rmagent-windows" / "scripts",
    Path.home() / ".claude" / "skills" / "rmagent-windows" / "scripts",
]
_CANDIDATES = _SHARED_DIRS
_shared = _load_shared()

# The five documented questions (rmagent-linux SKILL.md).
ALLOWED = {"attest", "sketch", "edges", "explain", "attackmap"}
# re-export the shared-engine helpers the CLI scripts use
load_inventory = _shared.load_inventory
witnesses = _shared.witnesses
find = _shared.find
hole = _shared.hole
cooldown_left = _shared.cooldown_left
mark_silent = _shared.mark_silent
clear_silent = _shared.clear_silent
MAX_PULL_BYTES = _shared.MAX_PULL_BYTES
_cap_signal = _shared._cap_signal
_parse = _shared._parse
record_ask = getattr(_shared, "record_ask", lambda *a, **k: None)

# Distro-default persistence that is not a finding (netsh×17 lesson).
_ATTACKMAP_FP = (
    "anacron", "cron.deny", "0hourly", "0anacron", "sysstat",
    "e2scrub_all", "mdadm", "logrotate", "apt-compat", "dpkg",
    "popularity-contest", "phpsessionclean",
)


def _filter_attackmap_fps(data: dict) -> dict:
    """Drop known-good cron/timer names; keep unexpected persistence."""
    if not isinstance(data, dict):
        return data
    cron = str(data.get("cron") or "")
    kept = []
    for part in cron.split(";"):
        p = part.strip()
        if not p:
            continue
        if any(fp in p.lower() for fp in _ATTACKMAP_FP):
            continue
        kept.append(p)
    data = dict(data)
    data["cron"] = ";".join(kept)
    data["n_cron"] = len(kept)
    data["fp_shed"] = True
    return data


def _sh_preamble(row: dict, since_hours: float, limit: int) -> str:
    track = row.get("track") or ["root"]
    t_items = ",".join(str(t).replace("'", "") for t in track)
    return (
        "export TRACK='" + t_items + "'\n"
        f"export SINCE_HOURS={float(since_hours)}\n"
        f"export LIMIT={int(limit)}\n"
    )


def ask(row: dict, skill: str, since_hours: float = 2.0, limit: int = 50,
        timeout: int = 25, creds: dict | None = None) -> dict:
    """Send ONE allowlisted named question over SSH. {ok, data?, error?, hole?}."""
    if skill == "actuate":
        return {"ok": False, "error": "actuate is off in Phase 0 (watch only)",
                "hole": hole(f"{row.get('id')} actuate", "watch is not actuate")}
    if skill not in ALLOWED:
        return {"ok": False, "error": f"skill not allowlisted: {skill}"}
    if skill not in (row.get("skills") or []):
        return {"ok": False, "error": f"{row.get('id')} does not advertise {skill}",
                "hole": hole(f"{row.get('id')} {skill}", "not advertised")}

    payload = QDIR / f"{skill}.sh"
    if not payload.exists():
        return {"ok": False, "error": f"no payload {payload.name}",
                "hole": hole(f"{row.get('id')} {skill}", f"no payload {payload.name}")}

    wid = row.get("id") or ""
    cd = _shared.cooldown_left(wid)
    if cd > 0:
        return {"ok": False, "error": f"silent-host cooldown {int(cd)}s",
                "hole": hole(f"{wid} {skill}", f"cooldown {int(cd)}s")}

    script = _sh_preamble(row, since_hours, limit) + "\n" + payload.read_text()
    try:
        r = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
             "-p", str(row.get("port") or 22),
             f"{row.get('user')}@{row['address']}", "bash -s"],
            input=script.encode(), capture_output=True, timeout=timeout)
    except FileNotFoundError:
        return {"ok": False, "error": "ssh binary not found on the jump host",
                "hole": hole(f"{wid} {skill}", "no ssh binary")}
    except subprocess.TimeoutExpired:
        _shared.mark_silent(wid, "ssh timeout")
        return {"ok": False, "error": "ssh timeout",
                "hole": hole(f"{wid} {skill}", "timeout")}
    except Exception as e:  # noqa: BLE001
        msg = str(e).split("\n")[0][:300]
        _shared.mark_silent(wid, f"unreachable: {msg}")
        return {"ok": False, "error": msg,
                "hole": hole(f"{wid} {skill}", f"unreachable: {msg}")}

    out = r.stdout.decode("utf-8", "replace")
    if r.returncode != 0 and not out.strip().startswith("{"):
        err = r.stderr.decode("utf-8", "replace")
        _shared.mark_silent(wid, f"exit {r.returncode}: {(err or out)[-120:]}")
        return {"ok": False, "error": (err or out)[-400:],
                "hole": hole(f"{wid} {skill}", (err or out)[-200:] or f"exit {r.returncode}")}
    _shared.clear_silent(wid)
    parsed = _shared._cap_signal(_shared._parse(out), row, skill)
    if skill == "attackmap" and parsed.get("ok") and isinstance(parsed.get("data"), dict):
        parsed["data"] = _filter_attackmap_fps(parsed["data"])
    return parsed
