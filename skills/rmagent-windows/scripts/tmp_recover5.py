#!/usr/bin/env python3
"""Extract the full Rev 17 actuate.py from the current session log.

The current session (340365f7) log contains 'def validate_target' 6 times —
these are echoes of the write_file diff from the Sep 3 work (session logs
persist across the conversation). Reconstruct the file from the log:
find the shebang before it, run to the main-guard, keep the LARGEST
candidate carrying all markers."""
import re
from pathlib import Path

LOG = Path.home() / "Library/Application Support/rterm/session-logs/local-340365f7-0054-49d1-bbcd-9a21a7af6d5f.log"
text = LOG.read_text(errors="replace")
print(f"log: {len(text):,} chars")

MARKERS = ["validate_target", "REDACT_KEYS", "find_plan", "rotate_credential",
           "isolate_host", "postcheck", "precheck", "parse_verify", "journal.append"]

candidates = []
for m in re.finditer(r"def validate_target", text):
    # walk BACKWARD from this point to the nearest shebang
    shebang = text.rfind("#!/usr/bin/env python3", 0, m.start())
    if shebang == -1:
        continue
    end = text.find('if __name__ == "__main__":', m.start())
    if end == -1:
        continue
    end = text.find("\n", end) + 1
    body = text[shebang:end]
    n = sum(1 for mk in MARKERS if mk in body)
    candidates.append((n, len(body), shebang, body))
    print(f"candidate @ shebang={shebang}: {len(body):,} chars, {n}/{len(MARKERS)} markers")

if candidates:
    candidates.sort(key=lambda x: (-x[0], -x[1]))
    n, size, pos, body = candidates[0]
    if n >= len(MARKERS) - 1:
        out = Path("/tmp/actuate_rev17_recovered.py")
        out.write_text(body)
        print(f"\nRECOVERED {size:,} chars ({n}/{len(MARKERS)} markers) -> {out}")
        # quick syntax check
        import ast
        try:
            ast.parse(body)
            print("AST parses OK")
        except SyntaxError as e:
            print(f"AST FAILS: {e} — needs cleanup (log truncation mid-file?)")
    else:
        print("best candidate incomplete — inspect manually")
else:
    print("no candidates")
