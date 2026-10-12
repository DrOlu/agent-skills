#!/usr/bin/env python3
"""Phase 2 — generate zoomed crops for transcription reads.

Three modes:
  --bands 0:320,300:620       explicit horizontal bands (y ranges), full width
  --auto 3                    N equal bands with 15% overlap
  --box 350,180,660,360       one tight region (x0,y0,x1,y1) — for number
                              stacks, signature lines, serial corners

Crop filenames carry the source filename + region so a later reader can
provenance-check any transcription claim. ONE crop per agent tool call.

Requires pillow (PIL). Scales: 2.0-2.5x for printed text/grids, 3.5-4.5x
for handwriting. If a digit is ambiguous at 4x, RE-CROP tighter, don't squint.

usage:
  crop_bands.py --image f.jpg --out-dir /tmp/crops --bands 0:320,300:620 --scale 2.4
  crop_bands.py --image f.jpg --out-dir /tmp/crops --auto 3 --scale 2.2
  crop_bands.py --image f.jpg --out-dir /tmp/crops --box 350,180,660,360 --scale 4
"""
import argparse
import os
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--bands", help="comma list of y0:y1")
    ap.add_argument("--auto", type=int, help="N equal overlapping bands")
    ap.add_argument("--box", help="x0,y0,x1,y1 tight region")
    ap.add_argument("--scale", type=float, default=2.5)
    ap.add_argument("--overlap", type=float, default=0.15)
    args = ap.parse_args()

    try:
        from PIL import Image
    except ImportError:
        sys.exit("pillow required: pip install pillow (or use uv/pipx per your env)")

    img = Image.open(args.image)
    W, H = img.size
    stem = os.path.splitext(os.path.basename(args.image))[0]
    os.makedirs(args.out_dir, exist_ok=True)

    regions = []
    if args.box:
        x0, y0, x1, y1 = (int(v) for v in args.box.split(","))
        regions.append((x0, y0, x1, y1, "box"))
    elif args.bands:
        for i, part in enumerate(args.bands.split(",")):
            y0, y1 = (int(v) for v in part.split(":"))
            regions.append((0, y0, W, min(y1, H), f"band{i + 1}"))
    elif args.auto:
        n = args.auto
        step = H / n
        pad = int(step * args.overlap)
        for i in range(n):
            y0 = max(0, int(i * step) - (pad if i else 0))
            y1 = min(H, int((i + 1) * step) + pad)
            regions.append((0, y0, W, y1, f"band{i + 1}"))
    else:
        sys.exit("one of --bands / --auto / --box required")

    for x0, y0, x1, y1, label in regions:
        crop = img.crop((x0, y0, x1, y1))
        crop = crop.resize((int(crop.width * args.scale),
                            int(crop.height * args.scale)), Image.LANCZOS)
        out = os.path.join(args.out_dir,
                           f"{stem}__{label}__y{y0}-{y1}__x{x0}-{x1}.png")
        crop.save(out)
        print(f"  {out}  ({crop.width}x{crop.height}, scale {args.scale})")

    print(f"\n{len(regions)} crop(s). AGENT: read each crop in its OWN tool")
    print("call; note per crop exactly what you see before moving on.")


if __name__ == "__main__":
    main()
