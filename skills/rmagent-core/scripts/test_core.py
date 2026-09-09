#!/usr/bin/env python3
"""Pure-logic tests for rmagent-core (no live estate)."""
from __future__ import annotations

from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import grains
import paths
import loader

N = F = 0


def ok(cond, label):
    global N, F
    N += 1
    print(("  ok  " if cond else "  FAIL ") + label)
    if not cond:
        F += 1


print("== grain firewall ==")
ok("apptrace" not in grains.IDENTITY, "so grain has no apptrace")
ok("attest" not in grains.APP, "at grain has no attest")
ok(len(grains.FR) == 0, "fr asks nothing")
ok("pay_attest" in grains.PAY, "pay grain has pay_attest")
ok("txntrace" in grains.ISO, "iso grain has txntrace")
ok("agents" in grains.AGENT, "ao grain has agents")
try:
    grains.assert_grain("rmagent-so", grains.IDENTITY | {"apptrace"})
    extra_caught = False
except ValueError:
    extra_caught = True
ok(extra_caught, "so+apptrace fails assert_grain")
grains.assert_grain("rmagent-so", grains.IDENTITY)
ok(True, "so identity assert_grain passes")

print("== paths ==")
ok(paths.CASES == Path.home() / ".rmagent" / "cases", "cases under ~/.rmagent")
ok("skills" not in str(paths.CASES), "cases not in skill tree")

print("== loader ==")
eng = loader.load_engine()
ok(hasattr(eng, "ask") and hasattr(eng, "ALLOWED"), "engine has ask+ALLOWED")
ok("engine.py" in str(getattr(eng, "__file__", "") or ""), "engine loaded from core/engine.py")
so_dir = Path.home() / ".agents" / "skills" / "rmagent-so"
loader.bind(eng, "rmagent-so", so_dir)
ok("apptrace" not in eng.ALLOWED, "bind so drops apptrace")
ok("attest" in eng.ALLOWED, "bind so keeps attest")
ok(eng.QDIR == so_dir / "scripts" / "questions", "bind so QDIR is so tree")
loader.apply_grain(eng, "rmagent-at")
ok("attest" not in eng.ALLOWED, "apply_grain at drops attest")
ok("appslow" in eng.ALLOWED, "apply_grain at keeps appslow")
ok("ringhealth" in eng.ALLOWED, "apply_grain at keeps ringhealth")
loader.apply_grain(eng, "rmagent-fr")
ok(len(eng.ALLOWED) == 0, "apply_grain fr is empty")

print()
if F:
    print(f"{F} FAILED, {N} run")
    sys.exit(1)
print(f"{N}/{N} passed — rmagent-core: ALL TESTS PASSED")
