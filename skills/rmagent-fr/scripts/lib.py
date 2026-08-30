"""RMAgent engine — allowlisted remote ask over pywinrm. No arbitrary shell.

Estate: two workgroup Windows servers (WS1/WS2), Administrator/SYSTEM tracking.
Caps mirror HT-ARCH-SEC-2026-01 §5. Phase 0 is WATCH ONLY — there is no
`actuate` skill and `ask()` refuses it.

Credentials are NEVER read from the inventory file. They come from:
  1. env  RMAgent_<ID>_USER / RMAgent_<ID>_PASS        (preferred)
  2. ~/.rmagent/creds.json  (mode 600)                  (convenience, gitignored)

The jump host does NOT become a lake: every answer is capped at MAX_PULL_BYTES
and oversized pulls are turned into a hole, not stored.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    import winrm  # pywinrm
except ImportError:
    winrm = None  # surfaced with a clear message at ask() time

SKILL_DIR = Path(__file__).resolve().parents[1]
QDIR = SKILL_DIR / "scripts" / "questions"

ALLOWED = {"attest", "sketch", "edges", "explain", "netedges", "pslogs", "kernring", "attackmap",
           "flowstats", "deepwindow", "profile", "lineage", "dns", "attackmap2"}
PHASE0_SKILLS = ALLOWED
MAX_PULL_BYTES = 32 * 1024
WALK_DEPTH = 8
WALK_FANOUT = 3
MAX_CONCURRENT = 2          # hunt walks per jump host
MAX_CONCURRENT_ATTEND = 3   # census knock pool (all-windows budget)
ASK_TIMEOUT_SEC = 25
EXPLAIN_TIMEOUT_SEC = 15 * 60
COOLDOWN_SEC = 5 * 60

_CREDS_FILE = Path.home() / ".rmagent" / "creds.json"


# ---------------------------------------------------------------- inventory
def load_inventory(path: str) -> dict:
    p = Path(path)
    text = p.read_text()
    if p.suffix == ".json":
        return json.loads(text)
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        raise SystemExit("Install pyyaml (`pip install pyyaml`) or pass a .json inventory")


def witnesses(inv: dict) -> list[dict]:
    rows = list(inv.get("witnesses") or inv.get("hosts") or [])
    return [r for r in rows if r]


def find(inv: dict, wid: str) -> dict | None:
    for r in witnesses(inv):
        if (r.get("id") or "").lower() == wid.lower():
            return r
    return None


# ---------------------------------------------------------------- credentials
# scrt secrets store support (BUG FIX 2026-08-19): census.py / hunt.py used to fail
# with "no credential for ws1" because creds_for() only looked at env + creds.json.
# The runbook (and redteam.py) expect passwords to flow from the scrt store
# (windows-server1-password / windows-server2-password), so we add that fallback
# here too. Master password: SCRT_PASS env → macOS Keychain → ~/.scrt_pass.
SCRT_STORE = os.environ.get(
    "SCRT_STORE", str(Path.home() / ".claude" / "skills" / "secrets" / "connectors.scrt")
)

def _resolve_store() -> str:
    """First existing scrt store among env + known locations."""
    cands = [SCRT_STORE,
             str(Path.home() / ".claude" / "skills" / "secrets" / "connectors.scrt"),
             str(Path.home() / ".pi" / "agent" / "skills" / "secrets" / "connectors.scrt"),
             str(Path.home() / ".pi" / "agent" / "skills-2" / "secrets" / "connectors.scrt")]
    for c in cands:
        if c and Path(c).exists():
            return c
    return SCRT_STORE

def _scrt_master_password() -> str | None:
    pw = os.environ.get("SCRT_PASS")
    if pw:
        return pw.strip()
    if sys.platform == "darwin":
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
    """Read a secret from scrt; never raises, never prints the value."""
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

# witness id → scrt key for the Windows password (extend when you add boxes)
_SCRT_KEY_MAP = {
    "ws1": "windows-server1-password",
    "ws2": "windows-server2-password",
}

def creds_for(row: dict) -> dict:
    """Resolve credentials WITHOUT ever printing them.
    Order: env → ~/.rmagent/creds.json → scrt store."""
    rid = (row.get("id") or "").upper()
    user = os.environ.get(f"RMAgent_{rid}_USER") or row.get("user") or "Administrator"
    pw = os.environ.get(f"RMAgent_{rid}_PASS")
    if not pw and _CREDS_FILE.exists():
        try:
            data = json.loads(_CREDS_FILE.read_text())
            entry = data.get(row.get("id")) or data.get(rid.lower())
            if isinstance(entry, dict):
                pw = entry.get("password")
                if not user or user == "Administrator":
                    user = entry.get("user", user)
            elif isinstance(entry, str):
                pw = entry
        except (json.JSONDecodeError, OSError):
            pass
    if not pw:
        # last resort: the scrt secrets store (same source redteam.py uses)
        sec = _scrt(_SCRT_KEY_MAP.get((row.get("id") or "").lower(), ""))
        if sec:
            pw = sec
            os.environ[f"RMAgent_{rid}_PASS"] = pw   # cache for later calls in this process
    if not pw:
        raise SystemExit(
            f"No credential for {row.get('id')}. Set RMAgent_{rid}_PASS / RMAgent_{rid}_USER "
            f"in env, or store {row.get('id')} in {_CREDS_FILE} (mode 600), "
            f"or add key '{_SCRT_KEY_MAP.get((row.get('id') or '').lower(), '?')}' to the scrt store. "
            f"Never put the password in the inventory file."
        )
    return {"user": user, "password": pw}


# ---------------------------------------------------------------- holes + caps
def hole(asked: str, why: str, extra: dict | None = None) -> dict:
    """A hole is a first-class hop: asked, empty, why. Same shape as an answer."""
    rec = {"asked": asked, "empty": True, "why": why}
    if extra:
        rec.update(extra)
    return rec


def _clamp_timeout(skill: str, timeout: int) -> int:
    cap = EXPLAIN_TIMEOUT_SEC if skill == "explain" else ASK_TIMEOUT_SEC
    return min(max(timeout, 1), cap)


def _cap(result: dict, row: dict, skill: str) -> dict:
    """Refuse to become a lake: clip oversized answers to a hole."""
    if not result.get("ok"):
        result.setdefault("hole", hole(f"{row.get('id')} {skill}", result.get("error") or "empty"))
        return result
    raw = json.dumps(result.get("data"), default=str)
    if len(raw.encode()) > MAX_PULL_BYTES:
        result["ok"] = False
        result["error"] = f"pull exceeded {MAX_PULL_BYTES} bytes"
        result["data"] = None
        result["hole"] = hole(f"{row.get('id')} {skill}", f"pull exceeded {MAX_PULL_BYTES} bytes")
    return result


def _parse(stdout: str) -> dict:
    stdout = (stdout or "").strip()
    if not stdout:
        return {"ok": True, "data": {"raw": ""}}
    try:
        return {"ok": True, "data": json.loads(stdout)}
    except json.JSONDecodeError:
        # some WinRM endpoints prefix a banner (e.g. "PowerShell is ready!").
        # skip to the first JSON object and parse from there.
        i = stdout.find("{")
        if i > 0:
            try:
                return {"ok": True, "data": json.loads(stdout[i:])}
            except json.JSONDecodeError:
                pass
        return {"ok": True, "data": {"raw": stdout[:4000]}}


# ---------------------------------------------------------------- preamble + ask
# Rev 8 FP allowlist: OS-default registry values that are NOT persistence.
# Applied ENGINE-SIDE to attackmap answers (the payload itself cannot grow —
# it must fit the ~8191-char WinRM UTF-16LE base64 budget).
FP_ALLOWLIST = {
    "T1546.007": (  # netsh helper DLLs — OS default on every Windows box
        # names (older list)
        "dotnet", "wfpdiag", "dhcp", "whhelper", "rpc", "authhost", "napmon",
        "trace", "console", "lanhelper", "wshelper", "elshelper", "rasmontr",
        "hnetmon", "remoteaccess", "nshipsec", "dot3svc", "vmms", "wlan",
        "wwancfg", "dot3cfg", "authhelper", "wcn", "mbn", "nshipsec6", "p2p",
        "rpc", "winhttp", "wwanapi", "hnsdiag", "trace", "wfpdiag",
        # live-observed 2026-08-29 (WS1/WS2 Server 2022): value=name=dll pairs
        "ifmon", "authfwcfg", "fwcfg", "netiohlp", "netprofm", "nshhttp",
        "nshwfp", "peerdistsh",
    ),
    "T1547.005": (  # default SecurityPackages (SSPs)
        "kerberos", "msv1_0", "schannel", "wdigest", "tspkg", "pku2u",
        "cloudap", "negotiate", "credssp", "ntlmssp",
    ),
    "T1547.002": (  # default LSA notification packages
        "scecli", "rasman", "rasauto", "rdpws", "samsrv", "kdcsvc", "certprop",
        "wdigest", "security",
    ),
}


def _filter_attackmap_fps(data: dict) -> dict:
    """Drop OS-default values from attackmap findings. Pure. A non-default
    value (a real attacker netsh helper / SSP) still fires."""
    findings = data.get("findings")
    if not isinstance(findings, list):
        return data
    kept = []
    for f in findings:
        t = f.get("t")
        allowed = FP_ALLOWLIST.get(t)
        if not allowed:
            kept.append(f)
            continue
        vals = [v for v in (f.get("v") or [])
                if not any(a in str(v).lower() for a in allowed)]
        if vals:
            kept.append({**f, "c": len(vals), "v": vals})
    out = {**data, "findings": kept, "found": len(kept)}
    return out


def _strip_payload(text: str) -> str:
    """Drop comment lines / blank lines before sending. They cost WinRM
    command-line budget (UTF-16LE base64 ~2.7x) but carry no semantics.
    Rev 8 bug fix: attackmap's payload crossed the ~8191-char budget after
    the preamble grew ($Track/$SinceHours/$Limit) — every ask returned
    'The command line is too long.'"""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(line.rstrip())
    return "\n".join(out)


def _preamble(row: dict, since_hours: float, limit: int, skill: str = "") -> str:
    track = row.get("track") or ["Administrator", "SYSTEM"]
    # build a proper PowerShell array: @('Administrator','SYSTEM')
    track_items = "','".join(str(t).replace("'", "''") for t in track)
    out = (
        "$ErrorActionPreference='SilentlyContinue'\n"
        f"$Track = @('{track_items}')\n"
        f"$SinceHours = {float(since_hours)}\n"
        f"$Limit = {int(limit)}\n"
    )
    return out


def ask(row: dict, skill: str, since_hours: float = 2.0, limit: int = 50,
        timeout: int = 25, creds: dict | None = None) -> dict:
    """Send ONE allowlisted named question. Returns {ok, data?, error?, hole?}."""
    if skill == "actuate":
        return {"ok": False, "error": "actuate is off in Phase 0 (watch only)",
                "hole": hole(f"{row.get('id')} actuate", "watch is not actuate")}
    if skill not in ALLOWED:
        return {"ok": False, "error": f"skill not allowlisted: {skill}"}
    if skill not in (row.get("skills") or []):
        return {"ok": False, "error": f"{row.get('id')} does not advertise {skill}",
                "hole": hole(f"{row.get('id')} {skill}", f"not advertised")}
    if winrm is None:
        return {"ok": False, "error": "pywinrm not installed (`pip install pywinrm`)",
                "hole": hole(f"{row.get('id')} {skill}", "pywinrm not installed")}

    door = (row.get("door") or "winrm").lower()
    if door != "winrm":
        return {"ok": False, "error": f"this skill is Windows-only; door={door}",
                "hole": hole(f"{row.get('id')} {skill}", f"door {door} not supported")}

    payload = QDIR / "windows" / f"{skill}.ps1"
    if not payload.exists():
        return {"ok": False, "error": f"no payload {payload.name}",
                "hole": hole(f"{row.get('id')} {skill}", f"no payload {payload.name}")}

    try:
        creds = creds or creds_for(row)
    except SystemExit as e:
        return {"ok": False, "error": str(e), "hole": hole(f"{row.get('id')} {skill}", "no credential")}

    script = _preamble(row, since_hours, limit, skill) + _strip_payload(payload.read_text())
    timeout = _clamp_timeout(skill, timeout)
    endpoint = row.get("endpoint") or f"http://{row['address']}:5985/wsman"
    transport = row.get("transport") or "basic"

    try:
        session = winrm.Session(endpoint, auth=(creds["user"], creds["password"]),
                                transport=transport)
        r = session.run_ps(script)
        out = r.std_out
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        err = r.std_err
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        if r.status_code != 0:
            return _cap({"ok": False, "error": (err or out or "")[-500:] or f"exit {r.status_code}"}, row, skill)
        parsed = _parse(out)
        if skill == "attackmap" and parsed.get("ok") and isinstance(parsed.get("data"), dict):
            parsed["data"] = _filter_attackmap_fps(parsed["data"])
        return _cap(parsed, row, skill)
    except Exception as e:  # noqa: BLE001 — any transport failure is a hole, not a crash
        msg = str(e).split("\n")[0][:300]
        kind = "timeout" if "timed out" in msg.lower() else "unreachable"
        return _cap({"ok": False, "error": msg}, row, skill) | {
            "hole": hole(f"{row.get('id')} {skill}", f"{kind}: {msg}")
        }


# ---------------------------------------------------------------- case recording
def record_ask(case_dir: Path | None, row: dict, skill: str, result: dict) -> None:
    if not case_dir:
        return
    case_dir.mkdir(parents=True, exist_ok=True)
    line = {
        "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "witness": row.get("id"), "plane": row.get("plane"),
        "skill": skill, "ok": result.get("ok"),
        "error": result.get("error"), "hole": result.get("hole"),
    }
    with (case_dir / "asks.jsonl").open("a") as f:
        f.write(json.dumps(line) + "\n")
    # Rev 8: also persist the full answer payload so correlate.py can join
    # across witnesses without re-pulling. One file per witness+skill.
    try:
        adir = case_dir / "answers"
        adir.mkdir(parents=True, exist_ok=True)
        wid = (row.get("id") or "witness").replace("/", "_")
        (adir / f"{wid}__{skill}.json").write_text(
            json.dumps(result.get("data") or {}, default=str, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------- concurrency
class BoundedPool:
    """Max-3 census knock budget for an all-windows estate. Mixed estates stay serial."""
    def __init__(self, n: int = MAX_CONCURRENT_ATTEND):
        self._sem = threading.Semaphore(n)

    def __enter__(self):
        self._sem.acquire()
        return self

    def __exit__(self, *a):
        self._sem.release()
