#!/usr/bin/env python3
"""
needle_drift.py — baseline-drift detection for witness answers, offline.

Needle's strongest capability for the observatory is embeddings: a 3072-dim
vector for any fragment, computed on-device, no network. This script keeps a
named baseline of "what this answer normally looks like" (a routine attest,
the usual sketch for a host) and scores new answers against it by cosine
similarity. A dropping score is drift — the answer changed shape even when no
single field tripped a rule.

Usage:
  # record (or re-record) a baseline entry from a fragment on stdin
  echo "<routine attest answer>" | scripts/needle_drift.py record ws1-attest

  # score a new answer against its baseline (verdict + similarity)
  echo "<today's attest answer>" | scripts/needle_drift.py score ws1-attest

  # list baselines; show one baseline's text
  scripts/needle_drift.py list
  scripts/needle_drift.py show ws1-attest

Verdicts (advisory, like every matrix verdict in this family), calibrated
empirically against this needle build (v3.0.2, 3072-dim) — the embedding
space is compressed, so the bands are tight:
  similar   >= 0.995 — routine variation; the answer looks like itself
  drifted   0.975-0.995 — the answer's shape or content mix changed; worth a
                          Laya triage or a look (live test: a bad-day attest
                          with new admin/SYSTEM/failed-logon fields scored 0.993)
  changed   < 0.975 — the answer is a different animal; look now (live test: a
                      PowerShell script block scored 0.968 against an attest
                      baseline)
Honest limit: needle embeddings separate SHAPE and TOPIC, not field values.
A "values changed, fields same" answer still scores similar — value drift is
the job of the field rules and the Rev-15 correlate joins, not this script.

Baselines live in ~/.rmagent/needle-drift/<name>.json (text + embedding +
timestamp). They are small kilobyte holes, not a lake: one entry per named
answer per host, overwritten on re-record, nothing else stored.

Offline by design: the child needs a Python with `cactus-needle` installed
(NEEDLE_PYTHON override first, then the usual probe list).
"""
import json, math, os, subprocess, sys, time

PROBE = [os.environ.get("NEEDLE_PYTHON"),
         "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12",
         "python3.12", "python3", "python"]
SCRIPT_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "needle-drift-child.py")
STORE = os.path.expanduser("~/.rmagent/needle-drift")

CHILD = r'''
import json, sys
import needle
with needle.Needle(tools=None) as agent:
    v = agent.embed(sys.stdin.read())
print("EMBED:" + json.dumps(v))
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

def embed(text):
    py = find_python()
    if not py:
        print("no Python with cactus-needle found — set NEEDLE_PYTHON or "
              "pip install cactus-needle", file=sys.stderr); sys.exit(2)
    with open(SCRIPT_PATH, "w") as f:
        f.write(CHILD)
    r = subprocess.run([py, SCRIPT_PATH], input=text, capture_output=True,
                       text=True, timeout=180)
    for line in (r.stdout or "").splitlines():
        if line.startswith("EMBED:"):
            return json.loads(line[len("EMBED:"):])
    print((r.stderr or "embedding failed")[-400:], file=sys.stderr); sys.exit(1)

def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)); nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

def verdict(sim):
    return "similar" if sim >= 0.995 else ("drifted" if sim >= 0.975 else "changed")

def entry_path(name):
    return os.path.join(STORE, name + ".json")

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(2)
    cmd = args[0]
    text = sys.stdin.read() if not sys.stdin.isatty() else ""
    os.makedirs(STORE, exist_ok=True)

    if cmd == "list":
        names = sorted(os.path.basename(p)[:-5] for p in
                       [os.path.join(STORE, f) for f in os.listdir(STORE)]
                       if p.endswith(".json"))
        for n in names:
            e = json.load(open(entry_path(n)))
            print(f"{n}  recorded {e.get('recorded', '?')}  "
                  f"{len(e.get('text', ''))} chars")
        if not names:
            print("(no baselines recorded)")
        return

    if cmd == "show":
        p = entry_path(args[1])
        if not os.path.exists(p):
            print(f"no baseline named {args[1]}", file=sys.stderr); sys.exit(2)
        e = json.load(open(p))
        print(e["text"]); return

    if cmd == "record":
        name = args[1]
        if not text.strip():
            print("no fragment on stdin to record", file=sys.stderr); sys.exit(2)
        with open(entry_path(name), "w") as f:
            json.dump({"text": text, "embedding": embed(text),
                       "recorded": time.strftime("%Y-%m-%d %H:%M:%S")}, f)
        return

    if cmd == "score":
        name = args[1]
        p = entry_path(name)
        if not os.path.exists(p):
            print(f"no baseline named {name} — record one first "
                  "(scripts/needle_drift.py record " + name + ")", file=sys.stderr)
            sys.exit(2)
        if not text.strip():
            print("no fragment on stdin to score", file=sys.stderr); sys.exit(2)
        base = json.load(open(p))
        sim = cosine(embed(text), base["embedding"])
        print(f"baseline: {name}")
        print(f"similarity: {sim:.3f}")
        print(f"verdict: {verdict(sim)} — advisory only; route per policy")
        return

    print(f"unknown command: {cmd}", file=sys.stderr); sys.exit(2)

if __name__ == "__main__":
    main()
