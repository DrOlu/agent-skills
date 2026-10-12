#!/usr/bin/env python3
"""Index a catalog's description field into an embedding store via a local
ollama embedder.

Key properties:
  - Embeds the `description` TEXT per record (after test_embedder_modalities
    proved the model is text-only). With a multimodal model you may add
    --embed-images, but the description index is still built — it powers
    structured provenance and honest docs.
  - INCREMENTAL: vectors are keyed by sha1(embedded_text). Records whose
    description did not change are not re-embedded; edits re-embed only the
    changed rows. Orphaned vectors (text changed away) are dropped.
  - Prompt styles follow EmbeddingGemma's retrieval recipe:
      documents: "title: none | text: {text}"
      queries:   "task: search result | query: {text}"
    Both configurable.
  - Ollama URL via --ollama-url or OLLAMA_URL env. Backend down = hard
    build error (index time MUST have the embedder; ask time must not
    require it for stored-vector probes).

usage:
  build_embeddings.py --catalog catalog.json --out embeddings.json \
      [--text-field description] [--model embeddinggemma-2:latest] \
      [--ollama-url http://localhost:11434] [--id-field image_id]
"""
import argparse
import hashlib
import json
import os
import sys
import urllib.request


def embed(url, model, text, timeout=120):
    payload = json.dumps({"model": model, "input": text}).encode()
    req = urllib.request.Request(f"{url}/api/embed", data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.load(resp)
    vecs = out.get("embeddings") or []
    if not vecs:
        raise RuntimeError(f"no embedding returned for {text[:40]!r}")
    return vecs[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--text-field", default="description")
    ap.add_argument("--id-field", default="image_id")
    ap.add_argument("--file-field", default="filename")
    ap.add_argument("--model", default="embeddinggemma-2:latest")
    ap.add_argument("--ollama-url",
                    default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--doc-prompt", default="title: none | text: {text}")
    args = ap.parse_args()

    with open(args.catalog) as f:
        records = json.load(f)

    # load existing store for incrementality
    store = {"model": args.model, "dims": None,
             "prompt_style": {"document": args.doc_prompt,
                              "query": "task: search result | query: {text}"},
             "items": {}}
    if os.path.exists(args.out):
        try:
            old = json.load(open(args.out))
            if old.get("model") == args.model:
                store["items"] = old.get("items", {})
        except Exception:
            pass

    wanted = {}
    for rec in records:
        text = (rec.get(args.text_field) or "").strip()
        if not text:
            print(f"SKIP {rec.get(args.id_field)}: empty {args.text_field}",
                  file=sys.stderr)
            continue
        doc_prompt = args.doc_prompt.format(text=text)
        wanted[rec[args.id_field]] = {
            "file": rec.get(args.file_field),
            "key": hashlib.sha1(doc_prompt.encode()).hexdigest(),
            "text": doc_prompt,
        }

    # reuse unchanged vectors
    reused, embedded = 0, 0
    for rid, item in wanted.items():
        old = store["items"].get(rid)
        if old and old.get("text_sha") == item["key"] and old.get("vector"):
            item["vector"] = old["vector"]
            item["text_sha"] = item["key"]
            reused += 1
            continue
        item["vector"] = embed(args.ollama_url, args.model, item["text"])
        item["text_sha"] = item["key"]
        embedded += 1
        store["dims"] = len(item["vector"])
        print(f"  embedded {rid} ({item['file']}) dims={store['dims']}")

    # drop orphans, strip bulky intermediates, write
    store["items"] = {rid: {"file": it["file"], "vector": it["vector"],
                            "text_sha": it["text_sha"],
                            "embedded_text": it["text"]}
                      for rid, it in wanted.items()}
    with open(args.out, "w") as f:
        json.dump(store, f)

    print(f"{len(store['items'])} vectors -> {args.out} "
          f"({embedded} embedded, {reused} reused; model {args.model})")
    if embedded == 0 and reused == 0:
        sys.exit("nothing embedded — check the catalog text field")


if __name__ == "__main__":
    main()
