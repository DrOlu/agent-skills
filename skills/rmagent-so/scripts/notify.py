"""RMAgent Telegram notifier — send detection alerts to Telegram.

Token + chat come from the secrets scrt store (telegram-bot-token / telegram-chat-id)
or env overrides (RMAgent_TELEGRAM_TOKEN / RMAgent_TELEGRAM_CHAT). Disable with
RMAgent_TELEGRAM_OFF=1.

Cross-platform jump host: works on macOS, Linux, and Windows. The scrt master
password is resolved in order: SCRT_PASS env var → macOS Keychain (macOS only)
→ ~/.scrt_pass file (one line, mode 600) — so Linux/Windows jump hosts just
export SCRT_PASS or write that file.

Never sends credentials, Event Log contents, or full case data — only short summaries.
"""
from __future__ import annotations
import os, subprocess, urllib.request, urllib.parse, json
from pathlib import Path
import sys

SCRT_STORE = os.environ.get(
    "SCRT_STORE", str(Path.home() / ".claude" / "skills" / "secrets" / "connectors.scrt"))


def _resolve_store() -> str:
    """Return the first existing scrt store among known locations (env + defaults)."""
    cands = [SCRT_STORE,
             str(Path.home() / ".claude" / "skills" / "secrets" / "connectors.scrt"),
             str(Path.home() / ".pi" / "agent" / "skills" / "secrets" / "connectors.scrt"),
             str(Path.home() / ".pi" / "agent" / "skills-2" / "secrets" / "connectors.scrt")]
    for c in cands:
        if c and Path(c).exists():
            return c
    return SCRT_STORE


def _scrt_master_password() -> str | None:
    """Resolve the scrt master password cross-platform:
    1. SCRT_PASS env var (everywhere)
    2. macOS Keychain via `security` (macOS only)
    3. ~/.scrt_pass file, first line, mode 600 (Linux/Windows fallback)
    Never logs the value."""
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
    # Linux / Windows fallback: read the master password from a file
    passfile = Path(os.environ.get("SCRT_PASS_FILE", str(Path.home() / ".scrt_pass")))
    try:
        if passfile.exists():
            return passfile.read_text().splitlines()[0].strip()
    except Exception:
        pass
    return None


def _scrt(key: str) -> str | None:
    if os.environ.get("RMAgent_TELEGRAM_OFF"):
        return None
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


def _creds() -> tuple[str | None, str | None]:
    token = os.environ.get("RMAgent_TELEGRAM_TOKEN") or _scrt("telegram-bot-token")
    chat = os.environ.get("RMAgent_TELEGRAM_CHAT") or _scrt("telegram-chat-id")
    return token, chat


def send(text: str) -> bool:
    """Send a short Markdown alert. Returns False if disabled/unconfigured (non-fatal)."""
    if os.environ.get("RMAgent_TELEGRAM_OFF"):
        return False
    token, chat = _creds()
    if not token or not chat:
        return False
    # keep messages well under Telegram's 4096-char limit
    if len(text) > 1800:
        text = text[:1797] + "..."
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": chat, "text": text,
             "disable_web_page_preview": "true"}).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False


def alert_critical(witness: str, why: str) -> bool:
    return send(f"🔴 RMAgent CRITICAL\nWitness {witness} missed 2 attestations.\n"
                f"Reason: {why}\n\nThis is a sensor failure or a stripped witness — not 'nothing happened.'")


def alert_smoke(witness: str, findings: list[str], case: str) -> bool:
    body = "\n".join(f"  • {f}" for f in findings)
    return send(f"🟠 RMAgent SMOKE detected on {witness}\n"
                f"{body}\n\nCase: {case}\n\nHunter walked it. A human (Judge) should review the case.")
