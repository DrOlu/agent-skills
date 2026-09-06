#!/usr/bin/env python3
"""Recovery attempt 3: search the CURRENT session log (340365f7) and the big
log for the escaped/JSON-encoded form. write_file content may appear with
escaped newlines (\n as literal backslash-n) inside a JSON tool call record."""
import re
from pathlib import Path

for name in ("local-340365f7-0054-49d1-bbcd-9a21a7af6d5f.log",
             "local-b9228892-0e47-4b05-9dec-aef30bef5d83.log"):
    p = Path.home() / "Library/Application Support/rterm/session-logs" / name
    t = p.read_text(errors="replace")
    n1 = t.count("validate_target")
    n2 = t.count("REDACT_KEYS")
    n3 = t.count("REDACT_KEYS = {")          # the actual assignment
    n4 = len(re.findall(r"def validate_target", t))
    print(f"{name}: validate_target={n1} REDACT_KEYS={n2} assignment={n3} def-validate={n4}")
    for m in list(re.finditer(r"REDACT_KEYS = \{", t))[:3]:
        print(f"   assignment @ {m.start()}: ...{t[m.start()-80:m.start()+80]!r}...")
