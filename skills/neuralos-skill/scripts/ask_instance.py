#!/usr/bin/env python3
"""ask_instance.py — the harness-agnostic entry point for ANY neuralOS
instance, on macOS, Linux and Windows.

Every harness that wants to consume a neuralOS instance — Claude Code,
SuperAgent, Pi, OpenCode, a cron job, a CI pipeline, a shell one-liner —
executes the instance's `ask.py` and reads the JSON envelope. This script
is the thin, portable front-end for that contract, so no harness has to
re-implement interpreter discovery, exit-code semantics or error handling:

    python ask_instance.py <instance_dir> "which pages mention risk management"

Contract (stable — build against this):
  * stdout carries EXACTLY ONE JSON envelope, always — answered, refused,
    or a harness-level error envelope, so machine consumers never parse prose
  * exit 0 = answered | exit 2 = refused / nothing produced (the instance's
    own code) | exit 3 = harness-level failure (no ask.py, timeout,
    unparsable output, bad menu shape) — the error envelope names the cause
  * stderr carries human-readable diagnostics only

The interpreter running ask.py is resolved as: --python flag > NEURALOS_PYTHON
env > the interpreter running this script (sys.executable) — correct on every
OS including Windows, where `python3` often does not exist.

Menu validation mirrors the runtime contract: needle_menu.json may be a bare
probe array, {"menu": [...]} or {"probes": [...]} — anything else is a
level-3 error naming the offending shape.

The action-intent refusal gate (GATE_VERSION 1) is enforced HERE, before
ask.py runs: instances whose ask.py predates the gate (hand-authored ones)
would otherwise answer imperative questions for every non-SuperAgent
consumer. Capability words only — enum values are data.

Standard library only.
"""
import argparse
import json
import os
import subprocess
import sys

EXIT_ANSWERED = 0
EXIT_NOTHING = 2       # the instance's own refusal / no-results code
EXIT_HARNESS = 3       # harness-level failure (this script's code)

# The action-intent gate (GATE_VERSION 1), enforced here BEFORE ask.py runs —
# hand-authored instances may ship no gate of their own, and SuperAgent's TS
# backstop only protects SuperAgent. A plain CLI consumer gets the same
# protection on every OS: an imperative verb no probe claims as a capability
# is refused without executing anything. Vocabulary rules (no_probe_matches,
# low_coverage) are deliberately NOT applied here — an ask.py that answers
# knows more than its menu shows.
ACTION_VERBS = ("play", "erase", "delete", "remove", "drop", "wipe", "purge",
                "send", "execute", "restart", "shutdown", "kill", "exploit",
                "deploy", "cancel")


def _capability_vocab(menu):
    """triggers + probe names + descriptions — enum values are data, not
    capabilities (a bucket named do-not-delete-... must not teach the menu
    the verb)."""
    import re
    stop = set("the a an of in on for to and or is are was were what which "
               "who me give all with their from by at it its do does did i "
               "we you this that those these there have has had more than "
               "one not use between during along per into over under about".split())
    vocab = set()
    for probe in menu:
        text = " ".join([*probe.get("triggers", []), probe.get("name", ""),
                         probe.get("description", "")])
        text = text.replace("_", " ")
        for tok in re.findall(r"[a-z0-9_]+", text.lower()):
            if tok not in stop:
                vocab.add(tok[:-1] if len(tok) > 3 and tok.endswith("s") else tok)
    return vocab


def action_gate(question, menu):
    """Returns 'action_intent' when the question opens with an imperative
    verb no probe claims, else None."""
    first = question.lower().split()[:1]
    if first and first[0] in ACTION_VERBS and first[0] not in _capability_vocab(menu):
        return "action_intent"
    return None


def error_envelope(error, **extra):
    env = {"mode": "harness_error", "refused": None, "results": None,
           "error": error}
    env.update(extra)
    return json.dumps(env, ensure_ascii=False)


def resolve_python(cli_value):
    if cli_value and cli_value != "auto":
        return cli_value
    env = os.environ.get("NEURALOS_PYTHON", "").strip()
    if env:
        return env
    return sys.executable


def validate_menu(instance_dir):
    """Returns None when the menu is one of the three documented shapes,
    else an error string."""
    menu_path = os.path.join(instance_dir, "needle_menu.json")
    if not os.path.isfile(menu_path):
        return f"no needle_menu.json in {instance_dir} — not a neuralOS instance"
    try:
        with open(menu_path, encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return f"needle_menu.json unreadable: {exc}"
    if isinstance(parsed, list):
        return None
    if isinstance(parsed, dict) and any(
            isinstance(parsed.get(k), list) for k in ("menu", "probes")):
        return None
    keys = sorted(parsed.keys())[:5] if isinstance(parsed, dict) else type(parsed).__name__
    return (f"needle_menu.json is not a probe array (expected a bare list, "
            f"{{'menu': [...]}} or {{'probes': [...]}}); found keys: {keys}")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run one question against a neuralOS instance (always-JSON contract).")
    ap.add_argument("instance", help="path to the instance directory (must contain ask.py)")
    ap.add_argument("question", help="the plain-English question")
    ap.add_argument("--python", default="auto",
                    help="interpreter for ask.py (default: NEURALOS_PYTHON or this script's interpreter)")
    ap.add_argument("--no-cache", action="store_true",
                    help="bypass the instance's TTL answer cache")
    ap.add_argument("--timeout", type=int, default=120,
                    help="seconds before the ask is abandoned (default 120)")
    ap.add_argument("--cwd", default=None,
                    help=argparse.SUPPRESS)  # internal: tests point at a stub dir
    args = ap.parse_args(argv)

    instance_dir = os.path.abspath(args.instance)
    ask_py = os.path.join(instance_dir, "ask.py")
    if not os.path.isfile(ask_py):
        print(error_envelope(
            f"no ask.py in {instance_dir} — generate one with the 'neuralos' skill "
            "(profile → model → generate), or point --instance at the right directory",
            instance=instance_dir))
        return EXIT_HARNESS

    menu_error = validate_menu(instance_dir)
    if menu_error:
        print(error_envelope(menu_error, instance=instance_dir))
        return EXIT_HARNESS

    with open(os.path.join(instance_dir, "needle_menu.json"), encoding="utf-8") as fh:
        menu_parsed = json.load(fh)
    menu = (menu_parsed if isinstance(menu_parsed, list)
            else next((menu_parsed[k] for k in ("menu", "probes")
                       if isinstance(menu_parsed.get(k), list)), []))
    gate_reason = action_gate(args.question, menu)
    if gate_reason:
        print(json.dumps({
            "ask_id": "ask-instance", "question": args.question,
            "normalized": args.question.lower().strip(),
            "probe": None, "mode": "refused", "refused": True,
            "refusal_reason": gate_reason, "gate_version": 1,
            "error": f"refused ({gate_reason}): the menu cannot answer this "
                     "confidently, and guessing is worse",
            "results": None, "candidates_retrieved": [],
            "via": "ask-instance"}, ensure_ascii=False))
        return EXIT_NOTHING

    python_bin = resolve_python(args.python)
    cmd = [python_bin, ask_py, args.question]
    if args.no_cache:
        cmd.append("--no-cache")

    try:
        proc = subprocess.run(cmd, cwd=instance_dir, capture_output=True,
                              text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired:
        print(error_envelope(f"ask.py timed out after {args.timeout}s",
                             instance=instance_dir, question=args.question))
        return EXIT_HARNESS
    except OSError as exc:
        print(error_envelope(f"cannot run {python_bin}: {exc}",
                             instance=instance_dir))
        return EXIT_HARNESS

    if proc.stdout.strip():
        try:
            json.loads(proc.stdout)  # must be one JSON envelope
            sys.stdout.write(proc.stdout if proc.stdout.endswith("\n")
                             else proc.stdout + "\n")
        except json.JSONDecodeError:
            print(error_envelope(
                "ask.py stdout was not a single JSON envelope — regenerate the "
                "instance with a current generator (gate/envelope contract)",
                raw_output=proc.stdout[:400], instance=instance_dir))
            return EXIT_HARNESS
    else:
        print(error_envelope(
            f"ask.py produced no stdout (exit {proc.returncode})",
            stderr=proc.stderr[:400], instance=instance_dir))
        return EXIT_HARNESS

    if proc.returncode in (EXIT_ANSWERED, EXIT_NOTHING):
        return proc.returncode
    print(f"ask_instance: unexpected ask.py exit {proc.returncode} "
          f"(envelope above may be partial); stderr: {proc.stderr[:200]}",
          file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
