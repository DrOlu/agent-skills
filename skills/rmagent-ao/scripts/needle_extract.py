#!/usr/bin/env python3
"""
needle_extract.py — offline structured extraction from a witness fragment.

Feed any rmagent witness answer (attest/sketch/edges/…, capped at 32 KB) and a
list of typed fields; needle (a 121M on-device model, ~100 MB RAM, no network,
no keys) fills them. Use it where a regex is too brittle and an LLM is too
expensive: normalising a logon line, pulling (user, count, source_ip) out of
prose, turning a free-text answer into matrix-ready state.

Usage:
  echo "<fragment>" | scripts/needle_extract.py user count:int source_ip
  scripts/needle_extract.py user count:int source_ip --fragment-file ans.json
  scripts/needle_extract.py user count:int source_ip --json

Field syntax: name, name:int (integer coercion) or name:ip (must match an
IPv4 address, anything else is rejected to the empty string). Missing or
unreliable values come back as empty string (or null with --json) — never a
guess: the 121M model is rock-solid on rigid tokens (numbers, IPs) but can
misplace semantic ones, so the wrapper validates what it can and blanks what
it cannot trust.

Notes:
  - Runs fully offline on the jump host. No keys, no network.
  - The child needs a Python with `cactus-needle` installed; the wrapper
    probes candidates (NEEDLE_PYTHON env override first) and re-execs.
  - The model is 121M — treat this as the free tier, not the best tier. If
    extraction quality matters more than cost, route the same fragment
    through Jev or an LLM instead.
"""
import json, os, subprocess, sys

PROBE = [os.environ.get("NEEDLE_PYTHON"),
         "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
         "python3.12", "python3", "python"]
SCRIPT_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "needle-extract-child.py")

def child_source(spec):
    ordered = sorted(spec, key=lambda ft: 0 if ft[1] == "int" else 1)  # ints first
    params = ", ".join(
        (f'{f} : int' if t == "int" else f'{f} : str = ""') for f, t in ordered)
    return f'''
import json, sys
import needle

@needle.tool(triggers=["extract the named values from the security fragment and report them"])
def extract({params}):
    """Report the values stated in the fragment."""
    print("CAPTURED:" + json.dumps({{"args": dict(locals())}}))
    return "ok"

with needle.Needle(tools=[extract]) as agent:
    r = agent.run("Fill each field with the exact value stated in the fragment: the account name, the number, the IP address. Copy only the value, nothing else.\\n\\nFRAGMENT:\\n" + sys.stdin.read())
    if r.get("results") != ["ok"]:
        print("CAPTURED:{{\\"args\\":{{}}}}")
'''

def find_python():
    for cand in PROBE:
        if not cand:
            continue
        try:
            if subprocess.run([cand, "-c", "import needle"], capture_output=True,
                              timeout=60).returncode == 0:
                return cand
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return None

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(2)
    fields, fragment_file, as_json = [], None, False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--fragment-file":
            fragment_file, i = args[i+1], i+2
        elif a == "--json":
            as_json, i = True, i+1
        else:
            fields.append(a); i += 1
    spec = [tuple(f.split(":", 1)) if ":" in f else (f, "str") for f in fields]
    spec = [(f, (t if t in ("int", "ip") else "str")) for f, t in spec]

    fragment = open(fragment_file).read() if fragment_file else sys.stdin.read()
    if not fragment.strip():
        print("no fragment (use --fragment-file or stdin)", file=sys.stderr); sys.exit(2)

    py = find_python()
    if not py:
        print("no Python with cactus-needle found — set NEEDLE_PYTHON or "
              "pip install cactus-needle", file=sys.stderr); sys.exit(2)

    with open(SCRIPT_PATH, "w") as f:
        f.write(child_source(spec))
    r = subprocess.run([py, SCRIPT_PATH], input=fragment, capture_output=True,
                       text=True, timeout=180)
    captured = {}
    for line in (r.stdout or "").splitlines():
        if line.startswith("CAPTURED:"):
            captured = json.loads(line[len("CAPTURED:"):]).get("args", {})
            break
    # sanity guard: the 121M model sometimes echoes the whole fragment (or a
    # sentence of it) as a value. Anything implausibly long for a short value
    # (username, number, IP, path) is rejected to the not-found marker instead
    # of being passed downstream as if it were real extraction.
    MAX_VALUE_CHARS = 64
    JUNK = {"FRAGMENT", "FRAGMENT:", "ok", "extract", "tool"}
    import re
    IPV4 = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")
    for k, v in list(captured.items()):
        if isinstance(v, str) and (v in JUNK or len(v) > MAX_VALUE_CHARS
                                   or v.count(" ") > 3):
            captured[k] = ""
    if not captured and r.returncode != 0:
        print((r.stderr or "")[-400:], file=sys.stderr); sys.exit(1)

    for f, t in spec:
        v = captured.get(f, "" if t != "int" else None)
        if t == "int" and isinstance(v, str):
            digits = "".join(ch for ch in v if ch.isdigit())
            v = int(digits) if digits else None
    # (values normalized below for output)
    if as_json:
        out = {f: (captured.get(f) if t == "int" else captured.get(f, "")) for f, t in spec}
        for f, t in spec:
            if t == "int" and isinstance(out[f], str):
                d = "".join(ch for ch in out[f] if ch.isdigit())
                out[f] = int(d) if d else None
            elif t == "ip" and not (isinstance(out[f], str) and IPV4.match(out[f])):
                out[f] = "" if out[f] is None else (out[f] if IPV4.match(str(out[f])) else "")
        print(json.dumps(out))
    else:
        for f, t in spec:
            v = captured.get(f, "" if t != "int" else "")
            if t == "int" and isinstance(v, str):
                d = "".join(ch for ch in v if ch.isdigit())
                v = d if d else ""
            if t == "ip" and not (isinstance(v, str) and IPV4.match(v)):
                v = ""
            print(f"{f}: {v}")

if __name__ == "__main__":
    main()
