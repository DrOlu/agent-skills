#!/usr/bin/env python3
"""Apply domain fixups to a generated profile.json — driven by a config
file so this works for ANY catalog without editing the script.

Generic profilers coerce zero-padded codes to int (state_code "024" -> 24),
over-fit bounds to tiny samples, and only enum-ify fields that meet generic
thresholds. This tool restores source-true types and pins small enums the
menu generator will use as argument cages.

fixups.json format (all keys optional):
{
  "force_str":   ["image_id", "state_code", "lga_code", "ra_code", "pu_code"],
  "enums":       {"state": ["LAGOS", "EDO", "BAUCHI", "PLATEAU"]},
  "relax":       {"description": {"min_length": 50, "max_length": 4000}}
}
  force_str : field -> str type; min/max cleared; samples from catalog
  enums     : field -> explicit value list (Literal cages downstream)
  relax     : field -> constraint overrides applied to the generated model
              NOTE: relax is recorded in the profile for the modeling step;
              the Pydantic file itself is edited by hand after gen_pydantic.

usage:
  fix_profile.py --profile profile.json --config fixups.json \
                 [--catalog catalog.json]
"""
import argparse
import json
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--catalog", help="optional: refresh sample_values from it")
    args = ap.parse_args()

    profile = json.load(open(args.profile))
    cfg = json.load(open(args.config))
    catalog = []
    if args.catalog:
        try:
            catalog = json.load(open(args.catalog))
        except Exception as exc:
            sys.exit(f"cannot read --catalog: {exc}")

    force_str = set(cfg.get("force_str", []))
    enums = cfg.get("enums", {})
    relax = cfg.get("relax", {})

    touched = []
    for field in profile.get("fields", []):
        name = field.get("name")
        if name in force_str:
            field["python_type"] = "str"
            field["detected_type"] = "str"
            field["min"] = None
            field["max"] = None
            if catalog:
                vals = sorted({r.get(name) for r in catalog
                               if r.get(name) is not None})
                if vals:
                    field["sample_values"] = vals
            touched.append(f"str:{name}")
        if name in enums:
            field["enum_values"] = enums[name]
            touched.append(f"enum:{name}")
        if name in relax:
            field.setdefault("constraint_overrides", {}).update(relax[name])
            touched.append(f"relax:{name}")

    profile["fixups"] = {
        "applied": True,
        "touched": touched,
        "note": "code fields restored to strings; small enums pinned; "
                "relaxations recorded for the modeling step",
    }
    json.dump(profile, open(args.profile, "w"), indent=2)
    print("fixups applied:", ", ".join(touched) or "(none matched)")


if __name__ == "__main__":
    main()
