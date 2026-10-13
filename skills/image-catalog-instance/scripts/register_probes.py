#!/usr/bin/env python3
"""Triple-wire domain probes into a factory-generated instance.

A probe must exist in ALL THREE places or ask.py silently refuses its
questions with a misleading "no probe scored > 0" (scoring runs off the
menu, but execution resolves through inst.TOOLS — a probe in the menu but
missing from instance.py scores fine and then vanishes):

  1. bridge.py          — the implementation (you author this)
  2. needle_menu.json   — the menu entry (name/description/parameters/triggers)
  3. instance.py        — a @needle.tool wrapper + TOOLS.append(name)

This script wires 2 + 3 from a probes.json spec, idempotently, and clears
.ask_cache.json (menu content changed → cached envelopes are stale).
Use --check to audit an instance without changing it; exits 1 on any
half-wired probe (the dangerous state).

probes.json shape (list):
[
  {"name": "record_details",
   "menu":   { ...complete needle_menu.json entry... },
   "wrapper": "def record_details(filename: str = \"\") -> dict:\n"
              "    \"\"\"Full record for one document.\"\"\"\n"
              "    return bridge.record_details(filename=filename)"}
]

The wrapper source is emitted verbatim under a generated
@needle.tool(triggers=<menu triggers>) decorator — keep it a plain
function that delegates to bridge.
"""
import argparse
import json
import os
import re
import sys


def load_menu(instance):
    with open(os.path.join(instance, "needle_menu.json")) as fh:
        return json.load(fh)


def save_menu(instance, menu):
    with open(os.path.join(instance, "needle_menu.json"), "w") as fh:
        json.dump(menu, fh, indent=2)
        fh.write("\n")


def wrapper_state(instance, name):
    src = open(os.path.join(instance, "instance.py")).read()
    decorated = re.search(r"@needle\.tool\([^)]*\)\s*\ndef %s\(" % re.escape(name), src)
    appended = re.search(r"^TOOLS\.append\(%s\)\s*$" % re.escape(name), src, re.M)
    defined = re.search(r"^def %s\(" % re.escape(name), src, re.M)
    return bool(decorated), bool(appended), src, bool(defined)


def probe_in_menu(menu, name):
    return any(p.get("name") == name for p in menu)


def build_wrapper_block(spec, menu_entry):
    name = spec["name"]
    triggers = menu_entry.get("triggers") or []
    body = spec["wrapper"].rstrip()
    return ("@needle.tool(triggers=%r)\n%s\nTOOLS.append(%s)\n"
            % (triggers, body, name))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", required=True, help="generated instance dir")
    ap.add_argument("--probes", required=True, help="probes.json spec")
    ap.add_argument("--check", action="store_true",
                    help="audit only; exit 1 on half-wired probes")
    args = ap.parse_args()

    specs = json.load(open(args.probes))
    menu = load_menu(args.instance)
    inst_path = os.path.join(args.instance, "instance.py")
    cache_path = os.path.join(args.instance, ".ask_cache.json")

    rows, conflicts, missing, to_wire, add_menu = [], [], [], [], []
    for spec in specs:
        name = spec["name"]
        in_menu = probe_in_menu(menu, name)
        decorated, appended, src, defined = wrapper_state(args.instance, name)
        in_inst = decorated and appended
        if in_menu and in_inst:
            rows.append((name, True, True, "ok"))
        elif not in_menu and not in_inst:
            rows.append((name, False, False, "missing"))
            missing.append(name)
            to_wire.append(spec)
            add_menu.append(spec)
        elif in_menu and not defined:
            # safe repair: nothing in instance.py to collide with
            rows.append((name, True, False, "missing wrapper (repairable)"))
            to_wire.append(spec)
        elif not in_menu and in_inst:
            rows.append((name, False, True, "missing menu entry (repairable)"))
            add_menu.append(spec)
        else:
            # a stray `def name(` exists without proper decoration/appending —
            # appending would shadow it; this needs human eyes
            rows.append((name, in_menu, in_inst,
                         "CONFLICT: stray unmanaged def in instance.py"))
            conflicts.append(name)

    width = max(len(r[0]) for r in rows) if rows else 4
    for name, m, i, note in rows:
        print("%-*s  menu=%-5s instance=%-5s  %s" % (width, name, m, i, note))

    if args.check:
        bad = conflicts + [r for r in rows if "missing" in r[3] and "repairable" not in r[3]]
        print("\ncheck: %d/%d fully wired, %d missing, %d conflict(s)"
              % (sum(1 for r in rows if r[3] == "ok"), len(rows),
                 len(missing), len(conflicts)))
        if conflicts:
            sys.exit(1)
        return

    if conflicts:
        print("\nCONFLICTS: %s — instance.py has an unmanaged def; wire by "
              "hand (the script will not shadow it)." % ", ".join(conflicts))
        sys.exit(1)

    if not to_wire and not add_menu:
        print("\nnothing to do — all probes wired; clearing ask cache anyway")
    else:
        src = open(inst_path).read()
        blocks = []
        for spec in to_wire:
            entry = next((p for p in menu if p.get("name") == spec["name"]), None)
            if entry is None:
                menu.append(spec["menu"])
                entry = spec["menu"]
            blocks.append(build_wrapper_block(spec, entry))
        if add_menu:
            known = {p.get("name") for p in menu}
            for spec in add_menu:
                if spec["name"] not in known:
                    menu.append(spec["menu"])
        if blocks:
            save_menu(args.instance, menu)
            if "domain probes" not in src:
                src += "\n\n# ---- domain probes (image-catalog-instance P4) ----\n"
            src += "\n\n".join(blocks) + "\n"
            with open(inst_path, "w") as fh:
                fh.write(src)
            compile(src, inst_path, "exec")  # refuse to ship a syntax error
        elif add_menu:
            save_menu(args.instance, menu)
        print("\nwired: %d wrapper(s) appended, %d menu entrie(s) ensured"
              % (len(blocks), len(add_menu)))

    if os.path.exists(cache_path):
        with open(cache_path, "w") as fh:
            fh.write("{}")
        print("cleared .ask_cache.json (menu content changed)")


if __name__ == "__main__":
    main()
