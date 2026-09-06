#!/usr/bin/env python3
"""Extract the full Rev 17 actuate.py content from the RTerm session log.

The Sep 3 session (local-b9228892) echoed the complete write_file content
for actuate.py. It appears as raw text between the '#!/usr/bin/env python3'
shebang that starts the actuate file and its final 'if __name__ == "__main__":'
block. Multiple occurrences exist (the original write + edits). Strategy:
find each occurrence of the docstring header 'RMAgent Actuate — Phase 1
response. Named, dry-run-first', take the LARGEST span to the main-guard,
and among candidates prefer the one containing ALL Rev 17 markers."""
import re
from pathlib import Path

LOG = Path.home() / "Library/Application Support/rterm/session-logs/local-b9228892-0e47-4b05-9dec-aef30bef5d83.log"
OUT = Path.home() / ".agents/skills/rmagent-actuate/scripts/actuate.py"
OUT_BAK = Path("/tmp/actuate_rev17_recovered.py")

text = LOG.read_text(errors="replace")
print(f"log size: {len(text):,} chars")

START = 'RMAgent Actuate \u2014 Phase 1 response'  # em-dash in the docstring
END = 'if __name__ == "__main__":'

candidates = []
for m in re.finditer(re.escape('RMAgent Actuate'), text):
    start = m.start()
    # back up to the shebang line just before it
    shebang = text.rfind('#!/usr/bin/env python3', max(0, start - 400), start)
    if shebang == -1:
        continue
    end = text.find(END, start)
    if end == -1:
        continue
    end = text.find('\n', end) + 1
    body = text[shebang:end]
    candidates.append((len(body), shebang, body))

print(f"candidates: {len(candidates)}")
MARKERS = ["validate_target", "REDACT_KEYS", "find_plan", "rotate_credential",
           "isolate_host", "postcheck", "precheck", "parse_verify",
           'journal.append', "REDACT"]

best = None
for size, pos, body in sorted(candidates, reverse=True):
    n = sum(1 for mk in MARKERS if mk in body)
    print(f"  candidate at {pos}: {size:,} chars, {n}/{len(MARKERS)} markers")
    if best is None or n > best[0]:
        best = (n, body)

if best and best[0] >= len(MARKERS) - 1:
    body = best[1]
    OUT_BAK.write_text(body)
    print(f"\nRECOVERED: {len(body):,} chars with {best[0]}/{len(MARKERS)} markers -> {OUT_BAK}")
    print("(written to /tmp first — review, then install over the reverted actuate.py)")
else:
    print("\nNO candidate carried the full marker set — inspect manually.")
