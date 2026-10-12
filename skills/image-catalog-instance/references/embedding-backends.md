# Embedding backends — ollama specifics

Verified against ollama 0.40.3 + `embeddinggemma-2:latest` (2026-10-12).
Re-prove with `test_embedder_modalities.py` before trusting any of it on a
different version/model.

## The silent-ignores-images trap

`POST /api/embed` accepts an `images` array (base64) in the payload for
ANY model — and a text-only model **silently ignores it**:

- `embed(text)` vs `embed(text, images=[img])` → **bit-identical vectors**
  (cos = 1.0000). No error, no warning.
- Empty `input` + image only → **no embeddings returned at all** (empty
  list), not an error.

Consequence: an agent that "tests" by checking for a 200 response or a
768-dim vector will conclude images work. The only honest test is vector
comparison. Hence Phase 0.

## EmbeddingGemma prompt styles

EmbeddingGemma models are trained with task prompts; using them improves
retrieval measurably:

- Index time (documents): `title: none | text: {content}`
- Ask time (retrieval queries): `task: search result | query: {question}`

Both are configurable in `build_embeddings.py` / the bridge. Even if a
future model ignores them, cosine ranking still works — the prompts are an
optimization, not a correctness dependency.

## Endpoint notes

- `POST /api/embed` → `{"embeddings": [[floats]], "total_duration", ...}`;
  dims for embeddinggemma-2:latest = 768.
- Keep the query-embedding cache (`.embed_cache.json` keyed by sha1 of the
  final prompt string) — identical questions must not re-hit the model, and
  the cache makes semantic probes ~instant on repeats.
- Backend down at ASK time ⇒ return `{"backend": "unavailable", "matches":
  [], "note": ...}`. Backend down at BUILD time ⇒ hard failure (index-time
  embedding is mandatory).
- `OLLAMA_URL` env override everywhere; never bake alternate URLs into
  model-facing arguments.

## When you have a real multimodal embedder

If Phase 0 returns `images_processed` (e.g. a CLIP/SigLIP-class model or a
future multimodal gemma embedding):

- You may embed image bytes directly; image↔text similarity becomes
  possible.
- STILL build the description index: it powers structured probes, honest
  provenance ("what the model saw"), and gives the small tool-calling model
  something textual to cite.
- Consider hybrid ranking (pixel-space + description-space) only if you can
  truth-check it; otherwise ship one honest ranker.

## Sizing notes

- 768-dim vectors × few hundred images ≈ a few MB JSON — fine to store
  alongside the instance. For tens of thousands, move to sqlite + blob or
  an ANN index; keep the same text-sha incremental keying.
- Embedding latency is dominated by model load on first call; the cache and
  batched build keep build time ~linear in records.
