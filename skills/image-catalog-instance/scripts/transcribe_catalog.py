#!/usr/bin/env python3
"""Phase 3 — merge agent-authored transcriptions with programmatic file
facts into catalog.json, enforcing catalog sanity.

The agent authors `records.json` (the ONE creative artifact — written from
zoom reads per references/vision-transcription.md). This script:

  - computes per-file facts (sha256, width, height, bytes, format) from the
    actual images (stdlib header parsing — never from transcription);
  - merges facts into each record;
  - FAILS THE BUILD on catalog poison:
      * record filename missing on disk / image with no record
      * duplicate sha256 (same bytes, two names)
      * ANY empty-dict or empty-list value anywhere in a record — nested
        dicts flatten into bare keys that strict Pydantic models
        (extra="forbid") reject at ask time. Omit the key instead.
        (This exact bug shipped once and survived sampled verification.)
  - WARNS on: int-looking values in *_code fields (zero-padded codes are
    strings), missing `description` (it is the embedding input),
    uncertain_fields=True without a `notes` caveat.

usage:
  transcribe_catalog.py --folder /path/images --records records.json --out catalog.json
"""
import argparse
import hashlib
import json
import os
import re
import struct
import sys


def image_size(path):
    with open(path, "rb") as f:
        data = f.read(65536)
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        w, h = struct.unpack(">II", data[16:24])
        return w, h, "PNG"
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return w, h, "JPEG"
            seg_len = struct.unpack(">H", data[i + 2:i + 4])[0]
            i += 2 + seg_len
    return None, None, "UNKNOWN"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_poison(obj, path="record"):
    """Yield paths of empty-dict / empty-list values (flatten poison)."""
    if isinstance(obj, dict):
        if not obj:
            yield path
        else:
            for k, v in obj.items():
                yield from find_poison(v, f"{path}.{k}")
    elif isinstance(obj, list):
        if not obj:
            yield path
        else:
            for i, v in enumerate(obj):
                yield from find_poison(v, f"{path}[{i}]")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--records", required=True, help="agent-authored records.json")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    with open(args.records) as f:
        records = json.load(f)
    # accept a bare list (canonical) or a {"records": [...]} wrapper — the
    # wrapper shape crashed with a confusing AttributeError once; be tolerant
    if isinstance(records, dict):
        records = next((v for v in records.values() if isinstance(v, list)), None)
        if records is None:
            sys.exit('records.json: object has no list value — expected a bare '
                     'list of records or {"records": [...]}')
    if not isinstance(records, list):
        sys.exit("records.json must be a JSON list of records")
    if not records:
        sys.exit("records.json is empty — nothing to build")

    image_files = sorted(os.listdir(args.folder))
    fatal, warnings = [], []

    by_name = {r.get("filename"): r for r in records}
    for r in records:
        if not r.get("filename"):
            fatal.append(f"record without filename: {json.dumps(r)[:120]}")

    # coverage both ways
    for r in records:
        p = os.path.join(args.folder, r.get("filename", ""))
        if not os.path.exists(p):
            fatal.append(f"record references missing image: {r.get('filename')}")
    for f_ in image_files:
        if f_.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")) \
                and f_ not in by_name:
            fatal.append(f"image on disk with no record: {f_}")

    seen = {}
    for r in records:
        p = os.path.join(args.folder, r["filename"])
        w, h, fmt = image_size(p)
        digest = sha256_of(p)
        if digest in seen:
            fatal.append(f"{r['filename']} byte-identical to {seen[digest]}")
        seen[digest] = r["filename"]
        r["path"] = os.path.abspath(p)
        r["size_bytes"] = os.path.getsize(p)
        r["width"], r["height"], r["format"] = w, h, fmt
        r["sha256"] = digest

        for bad in find_poison(r, r["filename"]):
            fatal.append(f"EMPTY dict/list value at {bad} — omit the key "
                         "(flattens into a bare field strict models reject)")
        for k, v in r.items():
            if k.endswith("_code") and isinstance(v, int):
                warnings.append(f"{r['filename']}.{k}={v} is int — zero-padded "
                                "codes must be strings")
        if not (r.get("description") or "").strip():
            warnings.append(f"{r['filename']} has no description — it is the "
                            "embedding input; semantic search will be blind")
        if r.get("uncertain_fields") and not (r.get("notes") or "").strip():
            fatal.append(f"{r['filename']}: uncertain_fields=True without a "
                         "notes caveat — name the uncertain fields")
        if not r.get("uncertain_fields") and not (r.get("notes") or "").strip():
            r.setdefault("notes", None)

    for w_ in warnings:
        print(f"WARNING: {w_}", file=sys.stderr)
    if fatal:
        for f_ in fatal:
            print(f"FATAL: {f_}", file=sys.stderr)
        sys.exit(f"catalog build failed: {len(fatal)} fatal issue(s)")

    with open(args.out, "w") as f:
        json.dump(records, f, indent=2)
    print(f"{len(records)} records -> {args.out}")
    for r in records:
        print(f"  {r['filename']:12s} {r['format']:4s} {r['width']}x{r['height']} "
              f"{r['size_bytes']:>8d}B  sha256={r['sha256'][:12]} "
              f"lead={r.get('leading_party', r.get('leading_category', '?'))}")
    print("sanity: no empty-dict/list poison, coverage complete, hashes unique")


if __name__ == "__main__":
    main()
