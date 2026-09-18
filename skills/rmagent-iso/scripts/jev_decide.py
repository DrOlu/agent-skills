#!/usr/bin/env python3
"""
jev_decide.py — run a Jev decision matrix (decisions/<name>.json) over a state.

Usage:
  echo "<state>" | scripts/jev_decide.py <matrix>
  scripts/jev_decide.py <matrix> --state-file case.json
  scripts/jev_decide.py <matrix> --state "…" --raw

The matrix file in decisions/ is the reviewable source of truth: the questions,
criteria and policy live there — edit it deliberately, in the light. This
wrapper merges {state, questions} and calls the use-jev helper, then prints the
answers plus the policy verdict (confidence below the matrix threshold is
flagged ESCALATE).

This is a judgment, not an actuator: it never executes anything, and any
gate/queue verdict remains advisory — operator approval rules are unchanged.
"""
import json, os, subprocess, sys

REQ_PATH = os.path.join(os.environ.get("TMPDIR", "/tmp"), "jev-decide-request.json")

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

    request = {
        "model": matrix.get("model", "~typesafe/jev-latest"),
        "state": state_text,
        "questions": matrix["questions"],
    }

    helper = os.environ.get("JEV_HELPER") or os.path.expanduser(
        "~/Library/Application Support/SuperAgent/Data/Skills/use-jev/jev")
    if not os.path.exists(helper):
        print(f"jev helper not found: {helper} (set JEV_HELPER)")
        sys.exit(2)

    with open(REQ_PATH, "w") as f:
        json.dump(request, f)
    out = subprocess.run([helper, REQ_PATH], capture_output=True, text=True)
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        sys.exit(1)
    resp = json.loads(out.stdout)

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
