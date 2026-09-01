#!/usr/bin/env python3
"""test_stc_v2 — the app_trace_id field: round-trip, propagation, injection,
OTel emission, and CLI wiring. Pure logic, no hosts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import stc as stc_mod

PASS = FAIL = 0
def ok(cond, label):
    global PASS, FAIL
    if cond: PASS += 1; print(f"  PASS  {label}")
    else:     FAIL += 1; print(f"  FAIL  {label}")

print("== 1. round-trip ==")
s = stc_mod.STC(case="CASE-20260831-120000", principal="Administrator",
                window_h=2.0, origin="jh1", depth=1,
                ticket="PAY-4419", app_trace_id="4bf92f3577b34da6a3ce929d0e0e4736")
enc = s.encode()
ok("apptrace=4bf92f3577b34da6a3ce929d0e0e4736" in enc, "encodes as apptrace=...")
d = stc_mod.STC.decode(enc)
ok(d.app_trace_id == "4bf92f3577b34da6a3ce929d0e0e4736", "decodes back")
ok(d.ticket == "PAY-4419", "existing fields unaffected")
ok(d.principal == "Administrator" and d.depth == 1, "principal/depth intact")

print("\n== 2. absent stays absent (back-compat) ==")
s2 = stc_mod.STC(case="C1", principal="Administrator")
d2 = stc_mod.STC.decode(s2.encode())
ok(d2.app_trace_id is None, "no app_trace_id -> None after round-trip")
ok("apptrace" not in s2.encode(), "not emitted when unset")

print("\n== 3. propagation: child/sibling carry it ==")
c = s.child()
ok(c.app_trace_id == s.app_trace_id, "child() carries app_trace_id")
ok(c.depth == s.depth + 1, "child() still increments depth")
sib = s.sibling()
ok(sib.app_trace_id == s.app_trace_id, "sibling() carries app_trace_id")

print("\n== 4. injection guards (the walk-budget attack) ==")
try:
    stc_mod.STC(case="C", principal="A", app_trace_id="X; depth=9; principal=root")
    ok(False, "delimiter injection in app_trace_id rejected at construction")
except ValueError:
    ok(True, "delimiter injection in app_trace_id rejected at construction")
try:
    stc_mod.STC.decode("stc: case=C; principal=A; apptrace=X; depth=9; depth=0")
    ok(False, "duplicate-key injection rejected at decode")
except ValueError:
    ok(True, "duplicate-key injection rejected at decode")
try:
    bad = stc_mod.STC.decode("stc: case=C; principal=A; apptrace=X; principal=root")
    ok(False, "key-duplication via apptrace rejected")
except ValueError:
    ok(True, "key-duplication via apptrace rejected")

print("\n== 5. OTel emission carries it ==")
import otel_emit
entry = {"id": 3, "parent": 1, "t": "2026-08-31T12:00:00Z",
         "kind": "observation", "skill": "edges", "witness": "ws1",
         "content": "test"}
span = otel_emit.span_from_entry(entry, s)
ok(span["attributes"]["rmagent.app_trace_id"] == "4bf92f3577b34da6a3ce929d0e0e4736",
   "rmagent.app_trace_id attribute present")
ok(span["attributes"]["rmagent.ticket"] == "PAY-4419", "ticket attribute still present")
ok(span["traceId"] == s.trace_id, "traceId still derived from case")
# absent -> empty string, never breaks the span shape
span2 = otel_emit.span_from_entry(entry, s2)
ok(span2["attributes"]["rmagent.app_trace_id"] == "", "absent -> empty string (span shape stable)")

print("\n== 6. CLI wiring (hunt.py accepts --app-trace-id) ==")
import subprocess
r = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "hunt.py"), "--help"],
                   capture_output=True, text=True)
ok("--app-trace-id" in r.stdout, "hunt.py --help documents --app-trace-id")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
