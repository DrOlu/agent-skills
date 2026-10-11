#!/usr/bin/env python3
"""
laya_decide.py — run a decision matrix (decisions/<name>.json) over a state,
entirely OFFLINE through the local laya checkpoint.

Usage:
  echo "<state>" | scripts/laya_decide.py <matrix>
  scripts/laya_decide.py <matrix> --state-file case.json
  scripts/laya_decide.py <matrix> --state "…" --raw

The matrix file in decisions/ is the reviewable source of truth: the
questions, criteria and policy live there — edit it deliberately, in the
light. Matrices written for the old cloud-Jev tier load UNCHANGED (same
choice/noul/score question shapes); only the caller is different.

How the laya call is made (first match wins — there is NO cloud fallback,
no endpoint, no key anywhere in this script):
  1. `import laya` in this interpreter
  2. $LAYA_HELPER         — explicit override, must be executable
  3. sibling use-laya skill — <this skill>/../../use-laya/laya, then the
                             same check under ~/.agents/skills and the
                             SuperAgent Data/Skills store (the helper
                             self-resolves a laya-capable interpreter)
If none is available: `pip install laya` (one-time 843 MB checkpoint
download into the HF cache; offline afterwards — pre-seed the cache on
air-gapped hosts).

Calibration: choice questions with more than 10 options run in laya's
UNCALIBRATED bucket — keep matrices to <=10 options per choice question;
confidence-based policy is only meaningful there.

This is a judgment, not an actuator: it never executes anything, and any
gate/queue verdict remains advisory — operator approval rules are unchanged.
"""
import json, os, shutil, subprocess, sys, tempfile, time

DEFAULT_CKPT = "convaiinnovations/laya"
CALIBRATED_MAX_OPTIONS = 10


def find_helper():
    """Return the path to a laya helper, or None. No hardcoded absolute paths."""
    env = os.environ.get("LAYA_HELPER")
    if env and os.path.isfile(env) and os.access(env, os.X_OK):
        return env
    skill_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    bases = [
        skill_root,  # sibling skill in whatever store this skill lives in
        os.path.expanduser("~/.agents/skills"),
        os.path.expanduser("~/Library/Application Support/SuperAgent/Data/Skills"),
    ]
    for base in bases:
        cand = os.path.join(base, "use-laya", "laya")
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("laya")


def call_laya(request):
    """Run the typed-decisions request through local laya. No network."""
    try:
        from laya import load
    except ImportError:
        helper = find_helper()
        if not helper:
            print("no laya caller available: pip install laya into this "
                  "interpreter, install the use-laya skill next to this skill, "
                  "set LAYA_HELPER, or set LAYA_PYTHON to an interpreter that "
                  "has laya.", file=sys.stderr)
            sys.exit(2)
        req_path = os.path.join(tempfile.gettempdir(), "laya-decide-request.json")
        with open(req_path, "w") as f:
            json.dump(request, f)
        out = subprocess.run([helper, req_path], capture_output=True, text=True)
        if out.returncode != 0:
            print(out.stderr, file=sys.stderr)
            sys.exit(1)
        return json.loads(out.stdout)

    agent = load(request.get("model", DEFAULT_CKPT))
    return agent.system_one(request["state"], request["questions"])


def warn_uncalibrated(questions):
    for qid, q in questions.items():
        if isinstance(q, dict) and q.get("type") == "choice":
            crit = q.get("criteria")
            n = len(crit) if isinstance(crit, (dict, list)) else 0
            if n > CALIBRATED_MAX_OPTIONS:
                print(f"WARNING: question {qid!r} has {n} options — laya's "
                      f"choice:11+ confidence is UNCALIBRATED; keep <= 10 per "
                      f"choice question for the policy thresholds to mean "
                      f"anything.", file=sys.stderr)


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

    warn_uncalibrated(matrix.get("questions", {}))
    t0 = time.time()
    resp = call_laya({
        "model": matrix.get("model", DEFAULT_CKPT),
        "state": state_text,
        "questions": matrix["questions"],
    })
    latency = time.time() - t0

    if raw:
        print(json.dumps(resp, indent=2))
        return

    policy = matrix.get("policy", {})
    esc = policy.get("escalate_below", 0.5)
    usage = resp.get("usage", {})
    print(f"matrix: {matrix_name}  model: laya (offline)  "
          f"input_tokens: {usage.get('input_tokens')}  latency: {latency:.1f}s")
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