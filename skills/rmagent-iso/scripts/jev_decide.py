#!/usr/bin/env python3
"""
jev_decide.py — run a Jev decision matrix (decisions/<name>.json) over a state.

Usage:
  echo "<state>" | scripts/jev_decide.py <matrix>
  scripts/jev_decide.py <matrix> --state-file case.json
  scripts/jev_decide.py <matrix> --state "…" --raw

The matrix file in decisions/ is the reviewable source of truth: the questions,
criteria and policy live there — edit it deliberately, in the light.

How the Jev call is made (first match wins, no hardcoded paths):
  1. $JEV_HELPER          — explicit override, must be executable
  2. sibling use-jev skill — <this skill>/../../use-jev/jev, then the same
                            check under ~/.agents/skills and the SuperAgent
                            Data/Skills store
  3. a `jev` binary on PATH
  4. direct fallback      — POST to OpenRouter's decisions endpoint
                            (https://openrouter.ai/api/alpha/decisions) with the
                            key from $OPENROUTER_API_KEY or the local scrt vault

This is a judgment, not an actuator: it never executes anything, and any
gate/queue verdict remains advisory — operator approval rules are unchanged.
"""
import json, os, shutil, subprocess, sys, urllib.request

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
SCRT_STORE = os.path.expanduser("~/.pi/agent/skills/secrets/connectors.scrt")
KEYCHAIN_SERVICE = "scrt-connectors-store"
REQ_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "jev-decide-request.json")

def find_helper():
    """Return the path to a jev helper, or None. No hardcoded absolute paths."""
    env = os.environ.get("JEV_HELPER")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    skill_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bases = [
        skill_root,  # sibling skill in whatever store this skill lives in
        os.path.expanduser("~/.agents/skills"),
        os.path.expanduser("~/Library/Application Support/SuperAgent/Data/Skills"),
    ]
    for base in bases:
        cand = os.path.join(base, "use-jev", "jev")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("jev")

def vault_key():
    """OpenRouter key from the local scrt vault, or None. Never printed."""
    try:
        pw = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, timeout=10).stdout.strip()
        if not pw:
            return None
        out = subprocess.run(
            ["scrt", "get", "--password", pw, "--storage", "local",
             "--local-path", SCRT_STORE, "openrouter-api-key"],
            capture_output=True, text=True, timeout=15)
        if out.returncode == 0:
            key = out.stdout.strip().splitlines()[-1]
            return key or None
    except Exception:
        pass
    return None

def call_jev(request):
    helper = find_helper()
    if helper:
        with open(REQ_PATH, "w") as f:
            json.dump(request, f)
        out = subprocess.run([helper, REQ_PATH], capture_output=True, text=True)
        if out.returncode != 0:
            print(out.stderr, file=sys.stderr)
            sys.exit(1)
        return json.loads(out.stdout)
    # direct fallback — no helper installed anywhere
    key = os.environ.get("OPENROUTER_API_KEY") or vault_key()
    if not key:
        print("no Jev caller available: install the use-jev skill next to this skill "
              "(or anywhere on this machine), set JEV_HELPER, or set OPENROUTER_API_KEY "
              "to use the direct decisions-endpoint fallback.", file=sys.stderr)
        sys.exit(2)
    body = json.dumps(request).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST", headers={
        "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        print(f"decisions endpoint returned HTTP {e.code}: {e.read().decode()[:400]}",
              file=sys.stderr)
        sys.exit(1)

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(2)
    matrix_name, state_file, state_text, raw = args[0], None, None, False
    i = 1
    while i < len(args):
        a = args[i]
        if a == "--state-file":
            state_file, i = args[i + 1], i + 2
        elif a == "--state":
            state_text, i = args[i + 1], i + 2
        elif a == "--raw":
            raw, i = True, i + 1
        else:
            print(f"unknown arg: {a}")
            sys.exit(2)

    skill_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    matrix_path = os.path.join(skill_dir, "decisions", matrix_name + ".json")
    if not os.path.exists(matrix_path):
        print(f"matrix not found: {matrix_path}")
        sys.exit(2)
    with open(matrix_path) as f:
        matrix = json.load(f)

    if state_text is None:
        state_text = open(state_file).read() if state_file else sys.stdin.read()
    if not state_text.strip():
        print("no state provided (use --state, --state-file, or stdin)")
        sys.exit(2)

    resp = call_jev({
        "model": matrix.get("model", "~typesafe/jev-latest"),
        "state": state_text,
        "questions": matrix["questions"],
    })

    if raw:
        print(json.dumps(resp, indent=2))
        return

    policy = matrix.get("policy", {})
    esc = policy.get("escalate_below", 0.5)
    print(f"matrix: {matrix_name}  model: {resp.get('model')}  cost: ${resp['usage']['cost']:.6f}")
    for qid, ans in resp["answers"].items():
        t = ans.get("type")
        if t == "noul":
            print(f"  {qid}: {ans['noul']}")
        elif t == "choice":
            print(f"  {qid}: {ans['choice']}")
        elif t == "score":
            print(f"  {qid}: {ans['score']}")
        else:
            print(f"  {qid}: {ans}")
        conf = ans.get("confidence")
        if conf is not None:
            flag = "  <-- ESCALATE (below policy threshold)" if conf < esc else ""
            print(f"    confidence: {conf}{flag}")
    gate_field = policy.get("gate_field")
    if gate_field and gate_field in resp["answers"]:
        verdict = resp["answers"][gate_field].get("choice")
        print(f"policy gate ({gate_field}): {verdict} — advisory only; existing operator rules still apply.")

if __name__ == "__main__":
    main()
