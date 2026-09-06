#!/usr/bin/env python3
"""Recovery attempt 4 (the right one): the Rev 17 actuate.py full content was
sent through write_file in the Sep 3 session. Session logs store terminal
OUTPUT, not tool-call args — so the full file text may never have hit the
log. BUT: test_actuate.py (which DID get pushed to github at 38ab437)
exercises the entire Rev 17 surface and the journal at ~/.rmagent contains
journal entries with plan_id/hash fields written BY the Rev 17 code.

The pragmatic recovery: REBUILD actuate.py + journal.py from the session
log of the CURRENT conversation — the write_file diff echo. Check whether
the tool-result echo contains it (search for the unique docstring with the
em-dash escaped). If not present anywhere, the honest path is: rebuild from
the spec (the SKILL.md/SAFETY.md sections we wrote describe every gate, and
test_actuate.py — 201 assertions, pushed to github — IS the executable spec).

This script first scans ALL local logs for the escaped form."""
import re
from pathlib import Path

hits = []
for log in sorted(Path.home().glob("Library/Application Support/rterm/session-logs/*.log")):
    t = log.read_text(errors="replace")
    # escaped-in-JSON form
    for pat in (r"def validate_target", r"def\\svalidate_target", r"REDACT_KEYS = \{"):
        found = len(re.findall(pat, t))
        if found:
            hits.append((log.name, pat, found))

for h in hits:
    print(h)
if not hits:
    print("no form of the Rev 17 actuate.py content exists in any session log")
    print("-> REBUILD FROM SPEC: test_actuate.py at 38ab437 is the executable spec;")
    print("   journal.py at 38ab437 has the hash chain. actuate.py must be rewritten.")
