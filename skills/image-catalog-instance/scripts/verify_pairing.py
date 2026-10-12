#!/usr/bin/env python3
"""Phase 1 — establish per-file identity BEFORE transcription.

For every image in a folder, emits:
  <out-dir>/identity__<filename>.png   top-band crop, upscaled (read ONE per tool call)
  <out-dir>/manifest.json              filename -> {sha256, width, height, bytes, format}

The agent workflow this enforces (print it, follow it):
  1. Read each identity crop in its OWN tool call (never batch).
  2. After each read, write down explicitly: "identity__X.png shows content Y".
  3. Only then claim the content->filename mapping, anchored by sha256.
  4. Any later transcription record must cite the file whose identity crop
     you actually saw.

Why: parallel image reads in agent harnesses do not reliably pair returned
attachments to invocations. Two of four records shipped swapped once because
call ORDER was trusted. File identity is only real when you forced the pair
yourself.

usage: verify_pairing.py --folder /path/to/images --out-dir /tmp/pairing
"""
import argparse
import hashlib
import json
import os
import struct
import sys

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
BAND_FRACTION = 0.28  # top 28% usually carries headers/titles


def image_size(path):
    """PNG/JPEG header dims (stdlib); returns (w, h, format)."""
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


def make_identity_crop(path, out_path):
    try:
        from PIL import Image
    except ImportError:
        print("PIL not available — falling back to full-file copy for "
              f"{path} (install pillow for proper identity crops)", file=sys.stderr)
        with open(path, "rb") as src, open(out_path, "wb") as dst:
            dst.write(src.read())
        return
    img = Image.open(path)
    W, H = img.size
    crop = img.crop((0, 0, W, max(1, int(H * BAND_FRACTION))))
    scale = min(2.5, max(1.0, 1400 / max(1, crop.width)))
    crop = crop.resize((int(crop.width * scale), int(crop.height * scale)),
                       Image.LANCZOS)
    crop.save(out_path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    files = sorted(f for f in os.listdir(args.folder)
                   if os.path.splitext(f)[1].lower() in IMAGE_EXTS)
    if not files:
        sys.exit(f"no images found in {args.folder}")

    manifest, seen_hashes = {}, {}
    for name in files:
        path = os.path.join(args.folder, name)
        w, h, fmt = image_size(path)
        digest = sha256_of(path)
        if digest in seen_hashes:
            print(f"DUPLICATE CONTENT: {name} is byte-identical to "
                  f"{seen_hashes[digest]} — one of them is probably wrong",
                  file=sys.stderr)
        seen_hashes[digest] = name
        crop_name = f"identity__{name}.png"
        make_identity_crop(path, os.path.join(args.out_dir, crop_name))
        manifest[name] = {"sha256": digest, "width": w, "height": h,
                          "bytes": os.path.getsize(path), "format": fmt}
        print(f"  identity crop -> {crop_name}  ({w}x{h}, {fmt})")

    with open(os.path.join(args.out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n{len(files)} identity crops + manifest.json in {args.out_dir}")
    print("NOW, AGENT: read each identity__*.png in its OWN tool call and")
    print("write down 'crop X shows content Y' per file BEFORE transcribing.")
    print("Anchor every later claim to the sha256 in manifest.json.")


if __name__ == "__main__":
    main()
