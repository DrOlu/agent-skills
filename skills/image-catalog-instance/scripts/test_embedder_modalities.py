#!/usr/bin/env python3
"""Phase 0 — prove whether an ollama embedding model actually processes
image input, or silently ignores it (text-only).

Method (decisive, no guessing):
  v_text  = embed(text)                 # no image
  v_img   = embed(text, images=[img])   # same text + image
  cos(v_text, v_img) == 1.0 (to float precision)  ->  images IGNORED
  cos < ~0.95                                      ->  images PROCESSED
Optionally, with two probe images: cos(text+img1, text+img2) distinguishes
pixel-driven variation from jitter.

Also probes the observed quirk: an empty `input` with only an image yields
NO embeddings on text-only models.

usage:
  test_embedder_modalities.py --model embeddinggemma-2:latest \
      --probe-image a.jpg [--probe-image2 b.jpg] [--ollama-url URL]

exit 0 always; prints a JSON verdict on stdout (machine-readable) and a
human summary on stderr.
"""
import argparse
import base64
import json
import math
import sys
import urllib.request


def embed(url, model, text, image_path=None, timeout=120):
    payload = {"model": model, "input": text}
    if image_path:
        with open(image_path, "rb") as f:
            payload["images"] = [base64.b64encode(f.read()).decode()]
    req = urllib.request.Request(
        f"{url}/api/embed", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.load(resp)
    vecs = out.get("embeddings") or []
    if not vecs:
        raise RuntimeError("no embeddings returned (empty input? wrong model?)")
    return vecs[0]


def cos(a, b):
    num = sum(x * y for x, y in zip(a, b))
    den = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return num / den if den else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--probe-image")
    ap.add_argument("--probe-image2")
    ap.add_argument("--ollama-url", default="http://localhost:11434")
    ap.add_argument("--text", default="a scanned document with handwritten numbers")
    args = ap.parse_args()

    if not args.probe_image:
        print(json.dumps({"error": "--probe-image required"}))
        sys.exit(2)

    result = {"model": args.model, "url": args.ollama_url}
    try:
        v_text = embed(args.ollama_url, args.model, args.text)
        v_img = embed(args.ollama_url, args.model, args.text, args.probe_image)
        c_change = cos(v_text, v_img)
        result["cos_text_vs_text_plus_image"] = round(c_change, 6)
        if args.probe_image2:
            v_img2 = embed(args.ollama_url, args.model, args.text, args.probe_image2)
            result["cos_img1_vs_img2_same_text"] = round(cos(v_img, v_img2), 6)
        # empty-input quirk
        try:
            embed(args.ollama_url, args.model, "", args.probe_image)
            result["empty_input_with_image"] = "returned embeddings"
        except Exception as exc:
            result["empty_input_with_image"] = f"no embeddings ({type(exc).__name__})"
    except Exception as exc:
        result["error"] = str(exc)[:300]
        print(json.dumps(result, indent=2))
        print(f"embedder test FAILED: {exc}", file=sys.stderr)
        sys.exit(1)

    ignored = c_change >= 0.99999
    result["verdict"] = "images_ignored" if ignored else "images_processed"
    print(json.dumps(result, indent=2))
    if ignored:
        print(
            f"\nVERDICT: TEXT-ONLY. {args.model} ignores the `images` field\n"
            "silently (cos = %.4f). Image embeddings must be embeddings of\n"
            "each image's CONTENT DESCRIPTION. Document this in the instance\n"
            "README — never market it as pixel-level image search."
            % c_change, file=sys.stderr)
    else:
        print(
            f"\nVERDICT: MULTIMODAL. {args.model} appears to process image\n"
            "input (cos = %.4f). You may embed image bytes directly — but\n"
            "still keep the description catalog for structured probes and\n"
            "provenance." % c_change, file=sys.stderr)


if __name__ == "__main__":
    main()
