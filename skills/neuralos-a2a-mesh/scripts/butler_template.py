#!/usr/bin/env python3
"""butler_template.py — cross-platform neuralOS butler harness.

Serves ONE named skill by grounding every question through the on-device
neuralOS/needle engine against READ-ONLY probes, and returning a small capped
digest. No model key. No keyword fallback. Honest holes.

Config (environment):
  NEEDLE_ENGINE_DIR   folder holding the engine binary + weights   (required)
  BUTLER_SKILL        skill served, e.g. butler.query              (default butler.query)
  BUTLER_MENU         path to needle_menu.json                     (default: beside this file)
  BUTLER_BRIDGE       python module name providing the probes      (default: bridge)
  BUTLER_K            retrieval shortlist size                     (default 8)
  BUTLER_CAP_BYTES    digest byte cap                              (default 32768)
  BUTLER_ENGINE_TIMEOUT seconds for one engine call                (default 60)

Every failure returns a structured hole ({"ok": false, "hole": true, "error": …})
rather than a traceback: the harness must never die on misconfiguration — the
gateway should see a diagnosable answer, not a dead skill.

Usage:
  python3 butler_template.py "which customer spent the most?"      # local test

Wire it into the gateway as the skill it serves (see references/butler-harness.md).
"""
import io
import json
import os
import re
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ENGINE_DIR = os.environ.get("NEEDLE_ENGINE_DIR", "")
MENU = os.environ.get("BUTLER_MENU", os.path.join(HERE, "needle_menu.json"))
BRIDGE_MOD = os.environ.get("BUTLER_BRIDGE", "bridge")
K = int(os.environ.get("BUTLER_K", "8"))
CAP = int(os.environ.get("BUTLER_CAP_BYTES", "32768"))
ENGINE_TIMEOUT = int(os.environ.get("BUTLER_ENGINE_TIMEOUT", "60"))

STOP = set("the a an of in on for to and or is are was were what which who how many "
           "show me give get all with their from by at it its do does did i we you this "
           "that those these there have has had more than one not use between during "
           "along per into over under about".split())


def find_engine():
    """Resolve the engine through NEEDLE_ENGINE_DIR — never hardcode."""
    if not ENGINE_DIR or not os.path.isdir(ENGINE_DIR):
        raise SystemExit("NEEDLE_ENGINE_DIR is unset or missing")
    binary = weights = None
    for c in ("needle", "needle.exe", "neural", "neural.exe"):
        p = os.path.join(ENGINE_DIR, c)
        if os.path.isfile(p):
            binary = p
            break
    for c in ("needle3.cact", "neuralOS.engine"):
        p = os.path.join(ENGINE_DIR, c)
        if os.path.isfile(p):
            weights = p
            break
    if not binary or not weights:
        raise SystemExit("engine binary and/or weights not found in %s" % ENGINE_DIR)
    return binary, weights


def resolve_engine():
    """(binary, weights, error). Never raises: a misconfigured engine is a
    diagnosable hole, not a dead skill."""
    try:
        binary, weights = find_engine()
        return binary, weights, None
    except SystemExit as exc:
        return None, None, hole(str(exc))


def load_menu(path):
    """(tools, error). Never raises: a missing or corrupt menu is a hole."""
    try:
        with open(path, encoding="utf-8") as fh:
            menu = json.load(fh)
    except FileNotFoundError:
        return None, hole("menu not found at %s (set BUTLER_MENU)" % path)
    except json.JSONDecodeError as exc:
        return None, hole("menu is not valid JSON: %s" % exc)
    except OSError as exc:
        return None, hole("menu could not be read: %s" % exc)
    tools = menu if isinstance(menu, list) else menu.get("tools", [])
    return (tools, None) if tools else (None, hole("menu has no probes: %s" % path))


def tokens(text):
    return set(re.findall(r"[a-z0-9_]+", str(text).lower())) - STOP


def score_probe(probe, q_tokens):
    s = 0.0
    for trig in probe.get("triggers", []):
        s += 3.0 * len(q_tokens & tokens(trig))
    s += 1.0 * len(q_tokens & tokens(probe["name"].replace("_", " ")))
    s += 0.3 * len(q_tokens & tokens(probe.get("description", "")))
    return s


def hole(error, **extra):
    return {"ok": False, "hole": True, "error": error, **extra}


def answer(question):
    t0 = time.time()
    # resolve both dependencies up front; every failure becomes a structured hole
    tools, err = load_menu(MENU)
    if err:
        return err
    binary, weights, err = resolve_engine()
    if err:
        return err

    q = tokens(question)
    shortlist = [p for _, p in sorted(
        ((score_probe(p, q), p) for p in tools), key=lambda x: x[0], reverse=True)][:K]

    ctx = os.path.join(HERE, "_probe_context.json")
    try:
        with open(ctx, "w", encoding="utf-8") as fh:
            json.dump(shortlist, fh, indent=0)
    except OSError as exc:
        return hole("probe context could not be written: %s" % exc)

    try:
        out = subprocess.run([binary, "--model", weights, "--tools", ctx,
                              "--prompt", question],
                             capture_output=True, text=True,
                             timeout=ENGINE_TIMEOUT, cwd=HERE).stdout.strip()
    except subprocess.TimeoutExpired:
        return hole("needle engine timeout after %ss" % ENGINE_TIMEOUT)
    except FileNotFoundError:
        return hole("needle engine not found at %s" % binary)

    try:
        resp = json.loads(out)
    except json.JSONDecodeError:
        return hole("needle engine returned unparseable output", raw=out[:300])

    calls = resp.get("function_calls", [])
    if not calls:
        return hole("needle engine did not select a probe", response=out[:500])

    call = calls[0]
    name, args = call["name"], call.get("arguments") or {}

    sys.path.insert(0, HERE)
    try:
        bridge = __import__(BRIDGE_MOD)
    except Exception as exc:                                    # noqa: BLE001
        return hole("bridge module %r could not be imported: %s" % (BRIDGE_MOD, exc))
    fn = getattr(bridge, name, None)
    if fn is None:
        return hole("probe %r not implemented by the bridge" % name)

    try:
        result = fn(**args) if isinstance(args, dict) else fn()
    except Exception as exc:                                    # noqa: BLE001
        return hole("probe %r failed: %s" % (name, str(exc)[:200]))

    payload = json.dumps(result, indent=1, default=str, ensure_ascii=False)
    if len(payload) > CAP:
        payload = payload[:CAP]
    return {"ok": True, "reply": {
        "result": payload,
        "elapsed_s": round(time.time() - t0, 2),
        "grounding": "needle engine",
        "probe": name,
    }}


def main():
    question = " ".join(sys.argv[1:]).strip()
    if not question:
        raise SystemExit('usage: python3 butler_template.py "your question"')
    print(json.dumps(answer(question), ensure_ascii=False))


if __name__ == "__main__":
    main()