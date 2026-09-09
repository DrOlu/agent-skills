#!/usr/bin/env python3
"""rmagent-core is not a witness. ask() always holes. ALLOWED is empty.

Other skills load rmagent-so via loader.py and apply their grain map.
"""
from __future__ import annotations

MAX_PULL_BYTES = 32 * 1024
ALLOWED: set[str] = set()


def hole(asked: str, why: str) -> dict:
    return {"asked": asked, "empty": True, "why": why}


def ask(*_a, **_k) -> dict:
    if _k.get("question") == "actuate" or (_a and _a[-1] == "actuate"):
        return {"ok": False, "error": "actuate is off", "hole": hole("core actuate", "watch is not actuate")}
    return {"ok": False, "error": "rmagent-core does not knock",
            "hole": hole("core", "not a witness — load so/linux/at/ao/pay/iso")}
