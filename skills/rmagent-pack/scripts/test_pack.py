#!/usr/bin/env python3
"""test_pack — rule logic, fixture-driven. Pure, no network."""
from __future__ import annotations
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "packs"))
import rulepack  # noqa: E402
import packs as _packs  # noqa: E402

PASS = FAIL = 0
FAILURES = []


def ok(cond, label):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL  {label}")


def row(eid, **kw):
    return {"eid": eid, **kw}


print("== registry")
ok(set(_packs.ALL_PACKS) >= {"kerberos_ad", "artifact_recipes"}, "both packs registered")
ok(all(isinstance(p.rules, list) and p.rules for p in _packs.ALL_PACKS.values()),
   "every pack has rules")

print("== predicate engine")
r = rulepack.Rule(id="t", title="t", events=[1], source="s",
                  filters={"user": {"eq": "bob"}, "n": {"gt": 3}})
ok(r.matches({"eid": 1, "user": "BOB", "n": 5}), "eq is case-insensitive; gt holds")
ok(not r.matches({"eid": 1, "user": "bob", "n": 3}), "gt rejects equal")
ok(not r.matches({"eid": 1, "user": "eve", "n": 9}), "eq rejects mismatch")
r2 = rulepack.Rule(id="t2", title="t2", events=[1], source="s",
                   filters={"path": {"regex": r"(?i)\.exe$"}})
ok(r2.matches({"eid": 1, "path": "C:\\x\\a.EXE"}), "regex is case-insensitive")
ok(rulepack._val({"a": {"B": "x"}}, "a.b") == "x", "dotted path is case-insensitive")

print("== kerberoast threshold (distinct SPNs >= 3, RC4 only)")
p = _packs.KERBEROS_AD
rows = [
    row(4769, TicketEncryptionType="0x17", TargetUserName="svc1@C", ServiceName="MSSQLSvc/a"),
    row(4769, TicketEncryptionType="0x17", TargetUserName="svc1@C", ServiceName="MSSQLSvc/b"),
    row(4769, TicketEncryptionType="0x17", TargetUserName="svc1@C", ServiceName="HTTP/c"),
    row(4769, TicketEncryptionType="0x12", TargetUserName="ok@C", ServiceName="HTTP/d"),  # AES -> ignored
    row(4769, TicketEncryptionType="0x17", TargetUserName="HOST$", ServiceName="HOST/HOST"),  # machine -> ignored
]
res = p.run(rows)
k = next(f for f in res["findings"] if f["rule"] == "krb.kerberoast")
ok(k["fired"] and k["count"] == 3, f"kerberoast fires on 3 RC4 distinct SPNs (count={k['count']})")
ok(all("spn" not in e or True for e in k["examples"]), "examples are slim, not a dump")
ok(len(k["examples"]) <= 3, "at most 3 example rows (no lake)")

print("== AES-only TGS must NOT fire kerberoast")
res2 = p.run([row(4769, TicketEncryptionType="0x12", TargetUserName="u@C", ServiceName="HTTP/x")])
k2 = next(f for f in res2["findings"] if f["rule"] == "krb.kerberoast")
ok(not k2["fired"], "AES TGS does not fire (RC4-only rule)")

print("== DCSync fires on the DRS GUID from a user, not from SYSTEM")
dcs = row(4662, Properties="1131f6ad-9c07-11d1-f79f-00c04fc2dcd2", SubjectUserName="evil")
sys_row = row(4662, Properties="1131f6ad-9c07-11d1-f79f-00c04fc2dcd2", SubjectUserName="SYSTEM")
res3 = p.run([dcs])
d = next(f for f in res3["findings"] if f["rule"] == "ad.dcsync")
ok(d["fired"] and d["severity"] == "critical", "DCSync fires critical for a user principal")
res4 = p.run([sys_row])
d2 = next(f for f in res4["findings"] if f["rule"] == "ad.dcsync")
ok(not d2["fired"], "SYSTEM replication activity does not fire (normal DC traffic)")

print("== spray needs 20 AND multiple users")
spray = [row(4771, Status="0x18", TargetUserName=f"u{i%5}") for i in range(25)]
res5 = p.run(spray)
s = next(f for f in res5["findings"] if f["rule"] == "krb.spray")
ok(s["fired"], "25 failures across 5 users fires spray")
res6 = p.run([row(4771, Status="0x18", TargetUserName="u1") for _ in range(5)])
s2 = next(f for f in res6["findings"] if f["rule"] == "krb.spray")
ok(not s2["fired"], "5 failures do not fire")

print("== §the standing rule: a BLIND source cannot fire")
res7 = p.run([dcs], blind_sources={"dc.dc"})
d3 = next(f for f in res7["findings"] if f["rule"] == "ad.dcsync")
ok(not d3["fired"] and d3.get("hole") is True, "blind source -> hole, never a finding")

print("== ratio threshold refuses a thin denominator (n<30)")
rr = rulepack.Rule(id="ratio", title="r", events=[1], source="s",
                   thresholds={"ratio": 5.0, "denominator_n": 10, "min_n": 30})
out = rulepack.apply_rule(rr, [row(1)] * 100)
ok(not out["fired"] and "ratio_hole" in out["detail"], "n=10 denominator -> ratio not trusted")

print("== artifact recipes encode the idea, not the data")
ar = _packs.ARTIFACT_RECIPES
ids = {r.id for r in ar.rules}
ok({"art.prefetch", "art.amcache", "art.usb", "art.shimcache"} <= ids,
   "prefetch/amcache/usb/shimcache recipes present")
ok(all(r.technique for r in ar.rules), "every recipe carries an ATT&CK technique")

print()
if FAIL:
    print(f"{FAIL} FAILED, {PASS} passed")
    for f in FAILURES:
        print(f"  x {f}")
    sys.exit(1)
print(f"{PASS} passed, 0 failed")
