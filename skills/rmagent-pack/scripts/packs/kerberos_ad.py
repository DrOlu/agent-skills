#!/usr/bin/env python3
"""pack: kerberos_ad — Domain-controller Kerberos / directory abuse.

Source facts: Windows Security 4768/4769/4771/4776/4624/4662/5136 on a DC,
cross-checked against the well-known Kerberos attack literature
(AS-REP roasting, Kerberoasting, pre-auth spray, DCSync, DCShadow) and the
Velociraptor / Sigma community rule packs. The FACTS are borrowed; the
execution is rmagent's (a capped pull, holes, no lake).

Thresholds are deliberately conservative: a rule that fires on a healthy DC
trains the operator to ignore it.
"""
from __future__ import annotations

from rulepack import Pack, Rule

KERBEROS_AD = Pack(
    id="kerberos_ad",
    title="Kerberos & directory abuse (DC)",
    description="Roasting, spray, DCSync, DCShadow, privileged group changes.",
    rules=[
        # ---- Kerberoasting: many TGS for RC4-encrypted SPNs (etype 0x17) ----
        Rule(
            id="krb.kerberoast",
            title="Kerberoasting: bulk RC4 TGS requests",
            events=[4769],
            source="dc.krb",
            filters={
                # RC4-HMAC = 0x17; AES would be 0x12 — attackers ask for RC4
                # because it cracks faster.
                "TicketEncryptionType": {"in": ["0x17", "23"]},
                # a machine account asking for itself is noise
                "TargetUserName": {"regex": r"[^$]$"},
            },
            thresholds={"distinct": "ServiceName", "count_field": "count",
                        "count": 3},
            severity="high",
            technique="T1558.003",
            why="3+ distinct SPNs requested with RC4 in the window: the classic "
                "Kerberoast sweep — one crackable ticket per service account.",
        ),
        # ---- AS-REP roasting: TGT without pre-auth (0x17 etype, no 4771 fail) ----
        Rule(
            id="krb.asrep",
            title="AS-REP roasting: TGT with RC4 for a user",
            events=[4768],
            source="dc.krb",
            filters={
                "TicketEncryptionType": {"in": ["0x17", "23"]},
                "PreAuthType": {"eq": "0"},
            },
            thresholds={"any": True},
            severity="high",
            technique="T1558.004",
            why="A 4768 with PreAuthType 0 means the account has pre-auth "
                "disabled — its AS-REP is crackable offline.",
        ),
        # ---- pre-auth spray: many 4771 failures across many users ----
        Rule(
            id="krb.spray",
            title="Kerberos pre-auth spray",
            events=[4771],
            source="dc.krb",
            filters={"Status": {"ne": "0x0"}},
            thresholds={"count": 20, "distinct": "TargetUserName", "count_field": "count"},
            severity="medium",
            technique="T1110.003",
            why="20+ failed pre-auths across multiple users in the window: "
                "a password spray, not a typo.",
        ),
        # ---- DCSync: 4662 carrying DRS replication GUIDs ----
        Rule(
            id="ad.dcsync",
            title="DCSync: directory replication rights used",
            events=[4662],
            source="dc.dc",
            filters={
                "Properties": {"contains": "1131f6ad-9c07-11d1-f79f-00c04fc2dcd2"},
                "SubjectUserName": {"notin": ["", "SYSTEM", "ANONYMOUS LOGON"]},
            },
            thresholds={"any": True},
            severity="critical",
            technique="T1003.006",
            why="4662 with the DS-Replication-Get-Changes GUID from a "
                "non-machine principal is DCSync — credential theft at the DC.",
        ),
        # ---- DCShadow: directory service changes from a rogue DC ----
        Rule(
            id="ad.dcshadow",
            title="DCShadow: rogue directory replication source",
            events=[5136],
            source="dc.dc",
            filters={"SubjectUserName": {"notin": ["", "SYSTEM"]}},
            thresholds={"any": True},
            severity="high",
            technique="T1207",
            why="A directory object change attributed to a non-SYSTEM "
                "principal can be a rogue DC pushing changes.",
        ),
        # ---- privileged group add ----
        Rule(
            id="ad.privesc",
            title="Privileged group membership added",
            events=[4728, 4732, 4756],
            source="dc.dc",
            filters={"MemberName": {"regex": r"."}},
            thresholds={"any": True},
            severity="high",
            technique="T1098",
            why="A global/local/universal privileged group gained a member — "
                "pair with 4648 to see where that principal then went.",
        ),
        # ---- audit policy cleared ----
        Rule(
            id="ad.audit_cleared",
            title="Audit log cleared on the DC",
            events=[1102],
            source="dc.dc",
            thresholds={"any": True},
            severity="critical",
            technique="T1070.001",
            why="1102 on a DC is the attacker covering their tracks — every "
                "conclusion from this DC after that instant is suspect.",
        ),
    ],
)
