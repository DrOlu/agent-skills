# Full workflow — images folder to verified instance

Walkthrough with copy-paste templates. Paths/examples use a generic
`/data/images` folder and a `my-images` instance dir; substitute yours.
Composes with the `neuralos` skill for generation + gate contract.

## Phase 0 — embedder modality proof

```bash
python3 scripts/test_embedder_modalities.py \
    --model embeddinggemma-2:latest --probe-image /data/images/a.jpg
```

Read the verdict. Document it in the instance README verbatim:

> `embeddinggemma-2:latest` is a TEXT embedding model: ollama's `/api/embed`
> silently ignores the `images` field (verified at build time — vectors
> identical with and without image input). The pipeline is
> image → content description → embedding; semantic search matches
> descriptions, not pixels.

If multimodal (verdict `images_processed`), you may embed bytes directly —
still keep descriptions for structured probes.

## Phase 1 — identity + pairing

```bash
python3 scripts/verify_pairing.py --folder /data/images --out-dir /tmp/pairing
```

Then, in the agent loop:

```
[tool call 1] Read /tmp/pairing/identity__01.png   -> note: "shows EDO form"
[tool call 2] Read /tmp/pairing/identity__02.jpg   -> note: "shows LAGOS form"
[tool call 3] Read /tmp/pairing/identity__03.jpeg  -> note: "shows BAUCHI form"
[tool call 4] Read /tmp/pairing/identity__04.jpg   -> note: "shows PLATEAU form"
```

Write the notes down AS YOU GO. If any later step disagrees with these
notes, the sha256 in manifest.json decides. NEVER transcribe from a batch
read whose pairing you did not force.

## Phase 2 — zoom transcription

```bash
# structure pass (printed text): 2-2.5x bands
python3 scripts/crop_bands.py --image /data/images/02.jpg --out-dir /tmp/crops \
    --auto 3 --scale 2.2
# handwriting pass: 3.5-4.5x on the regions that matter
python3 scripts/crop_bands.py --image /data/images/02.jpg --out-dir /tmp/crops \
    --box 400,290,800,480 --scale 4.0        # turnout number stack
python3 scripts/crop_bands.py --image /data/images/02.jpg --out-dir /tmp/crops \
    --box 0,1020,954,1393 --scale 2.0        # signature/date band
```

Per image, read each crop in its own call and note values field-by-field.
Adjudicate ambiguous digits with the form's own arithmetic as a signal, then
STILL record what is written (as-written rule). See
`vision-transcription.md` for the full protocol and uncertainty bookkeeping.

## Phase 3 — records.json → catalog.json

records.json is authored by you (the transcriptions). Shape:

```json
[
  {
    "filename": "02.jpg",
    "form_type": "EC 8A",
    "election": "2023 Presidential Election",
    "state": "LAGOS", "state_code": "024",
    "polling_unit": "FAGBAYI ST. (BY HOUSE 9)",
    "voters_on_register": 490,
    "spoiled_ballot_papers": 0,
    "party_scores": {"APC": 81, "PDP": 17, "LP": 12, "ZLP": 1},
    "leading_party": "APC",
    "uncertain_fields": true,
    "notes": "#5 spoiled written as dash (nil); #3 issued reads 396 at 4x",
    "description": "Full content transcription — this text IS the embedding input..."
  }
]
```

Hard rules encoded by `transcribe_catalog.py`:
- NO `{}` / `[]` values anywhere — omit the key instead.
- Zero-padded codes are strings ("024").
- uncertain_fields=True requires notes naming the fields.
- description always present (semantic search would otherwise be blind).

## Phase 4 — instance wiring

```bash
# profile the CATALOG (not the folder):
<neuralos-skill>/scripts/profile_data.py --source catalog.json --sample 10 --out profile.json
python3 scripts/fix_profile.py --profile profile.json --config fixups.json --catalog catalog.json
<neuralos-skill>/scripts/gen_pydantic.py --profile profile.json --out models.py --model-name MyImage
# HAND-EDIT models.py: relax over-fit bounds, add labels
<neuralos-skill>/scripts/gen_needle_instance.py --profile profile.json \
    --models models.py --out . --runtime python --agent-name my-images
# (if graph_edges.json already sits in out dir, stage profile+edges in a
#  build/ subdir to dodge the generator's same-file copy)
```

Then extend the generated `bridge.py` (imports + constants):

```python
import hashlib, math, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
EMBEDDINGS_FILE = os.path.join(HERE, "embeddings.json")
EMBED_CACHE_FILE = os.path.join(HERE, ".embed_cache.json")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "embeddinggemma-2:latest"
QUERY_PROMPT = "task: search result | query: {text}"

def _cos(a, b):
    num = sum(x*y for x, y in zip(a, b))
    den = math.sqrt(sum(x*x for x in a)) * math.sqrt(sum(y*y for y in b))
    return num / den if den else 0.0

def _embed_store():
    with open(EMBEDDINGS_FILE) as fh:
        return json.load(fh)

def _ollama_embed(text):
    key = hashlib.sha1(text.encode()).hexdigest()
    try:
        cache = json.load(open(EMBED_CACHE_FILE))
    except Exception:
        cache = {}
    if key in cache:
        return cache[key]
    payload = json.dumps({"model": EMBED_MODEL,
                          "input": QUERY_PROMPT.format(text=text)}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/embed", data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            out = json.load(resp)
    except Exception as exc:
        raise RuntimeError(f"embedder unreachable at {OLLAMA_URL}: {exc}")
    vecs = out.get("embeddings") or []
    if not vecs:
        raise RuntimeError("embedder returned no embedding")
    cache[key] = vecs[0]
    try:
        json.dump(cache, open(EMBED_CACHE_FILE, "w"))
    except Exception:
        pass
    return vecs[0]
```

Semantic probe (free-text arg is REQUIRED + pattern-caged in the menu so
the deterministic fast path captures the whole question — no model fumble):

```python
def semantic_search_images(query: str = "", limit: int = 4) -> dict:
    query = (query or "").strip() or "scanned document"
    try:
        qvec = _ollama_embed(query)
    except RuntimeError as exc:
        return {"query": query, "backend": "unavailable", "matches": [],
                "note": str(exc)[:200]}          # honest, never fabricated
    store = _embed_store()
    by_file = {r.get("filename"): r for r in _rows()}   # your row loader
    scored = []
    for rid, item in store["items"].items():
        rec = by_file.get(item.get("file") or _id_to_file(rid))
        if rec is None:
            continue
        scored.append((_cos(qvec, item["vector"]), rec))
    scored.sort(key=lambda t: -t[0])
    limit = max(1, min(int(limit), ROW_CAP))
    return {"query": query, "model": store["model"],
            "matches": [_digest(rec, sim) for sim, rec in scored[:limit]]}
```

Similar-image probe (stored vectors only — no ollama at ask time):

```python
def find_similar_image(filename: str, limit: int = 3) -> dict:
    store = _embed_store()
    by_file = {r.get("filename"): r for r in _rows()}
    target = next((i for i in store["items"].values()
                   if i.get("file", "").lower() == filename.lower()), None)
    if target is None:
        return {"error": f"unknown filename {filename!r}",
                "known": sorted(i.get("file") for i in store["items"].values())}
    scored = sorted(((_cos(target["vector"], it["vector"]), it)
                     for it in store["items"].values()
                     if it is not target), key=lambda t: -t[0])
    return {"target": filename,
            "most_similar": [_digest(by_file[it["file"]], s)
                             for s, it in scored[:max(1, min(limit, ROW_CAP))]
                             if it.get("file") in by_file]}
```

Menu entry for the semantic probe (the pattern cage is the trick):

```json
{
  "name": "semantic_search_images",
  "description": "Free-text semantic search over the image catalog: the query is embedded with <model> and cosine-ranked against each image's content embedding. For discovery questions.",
  "parameters": {"type": "object",
    "properties": {
      "query": {"type": "string", "pattern": "[\\s\\S]{3,}",
                "description": "free-text search query"},
      "limit": {"type": "integer", "minimum": 1, "maximum": 10}},
    "required": ["query"]},
  "triggers": ["find images about", "search images", "which image shows",
               "image matching", "semantic search images"]
}
```

Trigger-mass rule of thumb: if a generic-word probe steals another probe's
questions, cut the generic triggers and put the distinguishing tokens
(party names, form codes) in ONE compact trigger plus the description.

### details probe behavior

`image_details(filename="")` with NO filename returns an all-records digest
(not an error) so stat-questions that route there still answer; give the
probe honest stat triggers ("rejected ballots", "accredited voters") so the
gate recognizes the vocabulary.

## Phase 5 — verification battery

See `verification.md`. Order: per-record parse → lint_triggers → golden
selection suite + traps → truth_checks.json battery → gate conformance →
clear `.ask_cache.json` → write verification.txt (keep superseded passes).
