#!/usr/bin/env python3
"""Recovery attempt 2: find validate_target occurrences directly and dump
context around them to understand how the content appears in the log."""
from pathlib import Path

LOG = Path.home() / "Library/Application Support/rterm/session-logs/local-b9228892-0e47-4b05-9dec-aef30bef5d83.log"
text = LOG.read_text(errors="replace")

import re
hits = [m.start() for m in re.finditer("def validate_target", text)]
print(f"'def validate_target' occurrences: {len(hits)}")
for pos in hits[:6]:
    ctx = text[max(0, pos-200):pos+120].replace("\n", "\\n")
    print(f"\n@{pos}: ...{ctx[:320]}")
