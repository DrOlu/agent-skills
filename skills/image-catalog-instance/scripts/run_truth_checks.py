#!/usr/bin/env python3
"""Phase 5 — exhaustive truth battery for an image-catalog instance.

Runs TWO layers, because sampled checks are how wrong data ships green:

  Layer 1 (always): PER-RECORD PARSE — every catalog filename is asked for
  by details through the instance's ask.py and must come back with a parsed
  record (catches strict-model rejects like flattened empty dicts, on EVERY
  record, not one exemplar).

  Layer 2: declared checks from <instance>/truth_checks.json — each entry
  asks a question (fresh process, --no-cache), walks a JSON path into the
  envelope, and compares to an expected literal:
    {"q": "votes for LP", "path": "results.0.sheets",
     "equals": [{"image_id": "01", "votes": 9}, ...]}
    {"q": "how many records", "path": "results.0.count", "equals": 4}
    {"q": "find images about a re-run", "path": "results.0.matches.0.filename",
     "equals": "04.jpg"}
  - `equals` supports scalars, lists, dicts (subset-matched against the
    corresponding part of dicts).
  - details_question_template: template per record, e.g.
    "details of image {filename}" — Layer 1 asks it and asserts
    path results.0.record.<key> == <expected> per entry in per_record_expect.

usage: run_truth_checks.py --instance /path/to/instance [--python PATH]
exit 0 only if every layer passes.
"""
import argparse
import json
import os
import subprocess
import sys


def ask(instance, py, question):
    r = subprocess.run([py, "ask.py", "--no-cache", question],
                       capture_output=True, text=True, cwd=instance)
    if r.returncode != 0 or not r.stdout.strip():
        raise RuntimeError(f"ask failed (exit {r.returncode}): {question}\n"
                           f"{r.stderr[-400:]}")
    return json.loads(r.stdout)


def get_path(obj, dotted):
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, list):
            cur = cur[int(part)]
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def subset_match(expected, actual):
    """True if expected == actual, or expected dict/list is a subset shape."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return all(k in actual and subset_match(v, actual[k])
                   for k, v in expected.items())
    if isinstance(expected, list) and isinstance(actual, list):
        return len(expected) == len(actual) and all(
            subset_match(e, a) for e, a in zip(expected, actual))
    return expected == actual


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True)
    ap.add_argument("--python", default=sys.executable)
    args = ap.parse_args()

    inst = args.instance
    cfg_path = os.path.join(inst, "truth_checks.json")
    if not os.path.exists(cfg_path):
        sys.exit(f"no truth_checks.json in {inst} — author it (see examples/)")
    cfg = json.load(open(cfg_path))

    # locate catalog for Layer 1 (records file used at build time)
    catalog_path = os.path.join(inst, "catalog.json")
    records = json.load(open(catalog_path))
    file_field = cfg.get("file_field", "filename")
    passed = failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        passed, failed = passed + bool(cond), failed + (not cond)
        print(f"  {'PASS' if cond else 'FAIL'}  {name} {detail if not cond else ''}")

    print(f"== Layer 1: per-record parse ({len(records)} records) ==")
    tmpl = cfg.get("details_question_template")
    if not tmpl:
        print("  (no details_question_template — skipping per-record asks; "
              "NOT RECOMMENDED)")
    for rec in records:
        fname = rec[file_field]
        if not tmpl:
            continue
        try:
            env = ask(inst, args.python, tmpl.format(filename=fname))
            rec_out = get_path(env, "results.0.record")
            ok = isinstance(rec_out, dict) and not env.get("refused")
            if ok:
                for key, exp in cfg.get("per_record_expect", {}).items():
                    val = rec_out.get(key)
                    ok_key = (val is not None) if exp is None else subset_match(exp, val)
                    if not ok_key:
                        ok = False
                        check(f"parse+expect {fname}", False,
                              f"{key}={val!r} want {'present' if exp is None else exp!r}")
                        break
            check(f"parse {fname}", ok,
                  f"got {str(rec_out)[:120]}")
        except Exception as exc:
            check(f"parse {fname}", False, str(exc)[:200])

    print(f"== Layer 2: declared checks ({len(cfg.get('checks', []))}) ==")
    for chk in cfg.get("checks", []):
        q = chk["q"]
        try:
            env = ask(inst, args.python, q)
            actual = get_path(env, chk["path"])
            expected = chk.get("equals")
            check(q, subset_match(expected, actual),
                  f"at {chk['path']}: got {str(actual)[:160]} "
                  f"want {str(expected)[:160]}")
        except Exception as exc:
            check(q, False, str(exc)[:200])

    print(f"== truth battery: {passed} pass, {failed} fail ==")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
