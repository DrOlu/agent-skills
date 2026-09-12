#!/usr/bin/env python3
"""pack: artifact_recipes — Velociraptor-style collection recipes as LOGIC.

These are the *idea* half of a Velociraptor artifact: what to collect, which
files/keys/events, which fields matter, how to keep the answer small. The
execution half is a rmagent payload (questions/windows/*.ps1) that runs the
recipe ON THE BOX and returns a capped JSON answer — one-shot, no server, no
agent, no reporting home.

Recipe shape mirrors Velociraptor's distinction:
  parameters  what the collector needs (here: the tracked principal)
  sources     which underlying artifact(s) feed it
  fields      the only columns worth returning (keeps the answer small)
  on_missing  the answer when the artifact is absent -> "hole", never empty
"""
from __future__ import annotations

from rulepack import Pack, Rule

ARTIFACT_RECIPES = Pack(
    id="artifact_recipes",
    title="Forensic collection recipes (one-shot, no agent)",
    description="Prefetch / Amcache / MFT / USB / shimcache / LNK as capped pulls.",
    source_kind="windows-artifact",
    rules=[
        Rule(
            id="art.prefetch",
            title="Program execution (Prefetch)",
            events=[],                     # prefetch is files, not event IDs
            source="art.prefetch",
            filters={"Image": {"regex": r"(?i)\.exe$"}},
            thresholds={"distinct": "Image", "count_field": "count", "count": 1},
            severity="info",
            technique="T1204",
            why="Prefetch proves a binary EXECUTED even after the file is gone — "
                "the execution evidence 4688/ETW often misses.",
        ),
        Rule(
            id="art.amcache",
            title="Execution provenance (Amcache)",
            events=[],
            source="art.amcache",
            filters={},
            thresholds={"distinct": "Path", "count_field": "count", "count": 1},
            severity="info",
            technique="T1204",
            why="Amcache retains the first-seen time and path of executed "
                "binaries — the 'when did this first appear' question.",
        ),
        Rule(
            id="art.usb",
            title="USB mass-storage insertion",
            events=[20001, 20003],
            source="art.usb",
            filters={},
            thresholds={"any": True},
            severity="medium",
            technique="T1052.001",
            why="USB insertion before an exfil or an implant drop is a "
                "physical-access timeline marker.",
        ),
        Rule(
            id="art.shimcache",
            title="Shimcache / AppCompatCache entries",
            events=[],
            source="art.shimcache",
            filters={},
            thresholds={"distinct": "Path", "count_field": "count", "count": 1},
            severity="info",
            technique="T1204",
            why="Shimcache is a weak execution signal but the only one left "
                "when prefetch is disabled — carry it as corroboration, not proof.",
        ),
    ],
)
