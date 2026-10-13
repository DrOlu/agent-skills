---
name: image-catalog-instance
description: >
  Turn a folder of images (scanned forms, receipts, documents, photos with
  text) into a queryable structured catalog + a neuralOS-style on-device
  instance with semantic search — using a local text embedder (e.g. ollama
  embeddinggemma) as the "image embedding" via content descriptions. Encodes
  the vision-transcription discipline that prevents the three classic
  failures: file/attachment mis-pairing, low-zoom handwriting misreads, and
  sampled (non-exhaustive) verification. Use whenever the user brings images
  and wants them searched, queried, transcribed, tabulated, or wired into an
  agent/instance — or when correcting/suspecting an existing image catalog.
---

# image-catalog-instance

Build an honest, queryable data layer over a folder of images, and wire it
into an on-device instance whose semantic search is powered by a local text
embedder (ollama `embeddinggemma-2:latest` by default).

This skill exists because of a real build where ALL THREE of these failures
happened at once — and every automated check stayed green:

1. **File/attachment mis-pairing** — images read in parallel tool calls were
   transcribed correctly but bolted to the WRONG filenames. Two of four
   records were entirely swapped.
2. **Low-zoom misreads** — a handwritten dash "—" read as "3"; "396" read as
   "376"; a whole turnout stack misattributed row-by-row.
3. **Sampled verification** — every check that was *run* passed, but three of
   four records were never individually exercised, so a strict-model
   validation bug (empty-dict field) and two wrong figures survived delivery.

The user caught #1's symptom with a single observation. Don't need a user to
be your verifier — this skill makes you your own.

## When to use / not use

**Use when**: a folder of scans/photos (forms, IDs, receipts, result sheets,
handwritten pages) must become searchable/queriable/structured; when an
existing image catalog is suspected wrong; when wiring images into a
neuralOS/needle-style instance or any tool-calling agent with local
embeddings.

**Not when**: images need NO transcription (pure pixel similarity — use a
real image-embedding model like CLIP/SigLIP instead); OCR-at-scale of clean
printed text (dedicated OCR is cheaper); you have no vision capability at
all (then transcription must come from elsewhere — never guess).

**Composes with**: the `neuralos` skill (instance generation, gate, ask.py
contract) — this skill produces the catalog + embeddings and the image-
specific probes; neuralos turns them into the instance.

## The prime directive

> **The image file is the only oracle.** Transcribe what is WRITTEN, never
> what should be. Never reconcile arithmetic. Mark what you can't read.
> Verify every record, not a sample. And never trust tool-call ORDER to tell
> you which pixels belong to which file.

---

## Workflow (6 phases — run in order, every time)

```
P0 EMBEDDER PROOF ──► P1 IDENTITY/PARING ──► P2 ZOOM TRANSCRIPTION ──►
P3 CATALOG BUILD ──► P4 INSTANCE WIRING ──► P5 EXHAUSTIVE VERIFICATION
```

### Phase 0 — Prove the embedder's modality FIRST

Do not assume the embedding model can see images. `ollama's /api/embed`
**silently ignores** an `images` field for text-only models (verified live
with embeddinggemma-2:latest: vectors bit-identical with/without image,
cos = 1.0000). Run:

```bash
python3 scripts/test_embedder_modalities.py \
    --model embeddinggemma-2:latest \
    --probe-image /path/to/any.jpg [--probe-image2 /path/to/other.jpg]
```

- Verdict `images_ignored` (cos ≥ 0.99999 with/without image) → the image
  embedding IS the embedding of the image's **content description**. This is
  the pipeline this skill implements. Say so plainly in the README and to
  the user — never market it as pixel-level image search.
- Verdict `images_processed` → you have a true multimodal embedder; you may
  embed image bytes directly, but STILL keep the description catalog (it
  powers the structured probes and honest provenance).

Full API quirks: `references/embedding-backends.md`.

### Phase 1 — Establish per-file identity BEFORE any transcription

Run once at the start (and any time files change):

```bash
python3 scripts/verify_pairing.py --folder /path/to/images --out-dir /tmp/pairing
```

This emits, per image: an **identity crop** (top band, upscaled) named
`identity__<filename>.png` and a `manifest.json` (filename, sha256, width,
height, bytes). Then:

- **Read each identity crop in its OWN tool call** (one per message). Never
  batch image reads for identification.
- After each read, write down: "crop file X shows content Y". Only then
  claim the mapping.
- Re-derive nothing later from memory: every transcription record cites the
  filename whose identity crop you actually saw.

Why: parallel image reads do not reliably pair attachments to invocations
in many harnesses. The sha256 in the manifest anchors everything: if two
records ever disagree about a file, the hash decides.

### Phase 2 — Zoom transcription (the discipline)

For EACH image, generate zoomed crops and read them one per call:

```bash
python3 scripts/crop_bands.py --image /path/01.png --out-dir /tmp/crops \
    --bands 0:320,300:620,560:860 --scale 2.4
# or equal bands with 15% overlap:
python3 scripts/crop_bands.py --image /path/01.png --out-dir /tmp/crops \
    --auto 3 --scale 2.2
# tight crop on one region (e.g. a handwritten number stack), 4x:
python3 scripts/crop_bands.py --image /path/01.png --out-dir /tmp/crops \
    --box 350,180,660,360 --scale 4.0
```

Transcription protocol, per image (full rules: `references/vision-transcription.md`):

1. Read printed structure first at 2–2.5× (headers, table grids, labels) —
   near-certain.
2. Read handwritten regions at ≥3.5×. A value you cannot read at zoom is
   recorded as uncertain — with a `notes` caveat naming the exact field.
3. Cross-validate: figures vs their written-out words ("313" vs "three
   hundred & thirteen"), and the form's own arithmetic (#3−#4, #5+#6+#7)
   as a *consistency signal only*.
4. **Transcribe as-written.** If the form's numbers don't add up, record the
   written values and note the discrepancy. Never "correct" a form.
5. One crop per read. Crops are cheap; re-crop anything ambiguous at higher
   scale rather than squinting.

### Phase 3 — Build the catalog (and sanitize it)

Author the transcriptions as a records file (the one creative artifact —
the agent writes it from its zoom reads), then let the script add file facts
and enforce sanity. Format: a **bare JSON list** of records (a
`{"records": [...]}` wrapper is also accepted); every record carries a
`description` — that text IS the semantic-search embedding input:

```bash
python3 scripts/transcribe_catalog.py \
    --folder /path/to/images --records records.json --out catalog.json
```

The script computes size/dimensions/sha256/format from the files (stdlib
header parsing), merges with your records, and FAILS the build on:
- a record whose filename doesn't exist, or an image with no record;
- duplicate sha256 (same image twice under two names);
- **any empty-dict or empty-list value** — these flatten into bare fields
  that strict Pydantic models (`extra="forbid"`) reject. Omit the key
  instead. (This exact bug shipped once; the check is non-negotiable.)
- zero-padded code-like values that arrived as ints (warns: codes are
  strings, "024" not 24).

Then fix the profile for instance generation:

```bash
python3 scripts/fix_profile.py --profile profile.json --config fixups.json
# fixups.json: {"force_str": ["state_code", "pu_code"], "enums": {"state": ["LAGOS","EDO"]}}
```

### Phase 4 — Wire the instance

Profile the **catalog.json** (profilers cannot ingest bare directories or
pixels):

```bash
neuralos-profile --source catalog.json --sample 10 --out profile.json   # per your neuralos skill
gen_pydantic → hand-relax over-fit bounds → gen_needle_instance
```

Hand-edit the generated models: bounds derived from N observed records are
over-fit (a `max_length` pinched to one string's length will reject the next
scan). Relax numerics to domain-sane ranges (counts ≤ few thousand, string
lengths generous) and add human labels to every field.

Add the image-specific probes to the bridge (full copy-paste templates in
`references/workflow.md` §4):

- `semantic_search_images(query, limit)` — embeds the free-text query with
  the query-prompt style and cosine-ranks the stored vectors. **Make the
  query arg required + pattern-caged (`[\s\S]{3,}`)** so the deterministic
  fast path can capture it from the question — semantic search then needs no
  model fumbling.
- `find_similar_image(filename)` — ranks stored vectors against one image;
  no ollama call at ask time; filename enum-caged.
- `image_details(filename)` — full record; **with no filename returns an
  all-records digest, not an error** (so stat-questions that route there
  still answer honestly).
- `party_votes(party)` / domain equivalents — deterministic per-field
  lookups; enum-caged; this is where NUMERIC questions must route.
- Backend-down behavior: if the embedder is unreachable, return an honest
  `{"backend": "unavailable", "matches": []}` digest. Never raise past the
  envelope, never fabricate matches.

Copy the semantic/similar probe templates from `references/workflow.md` §4
**verbatim** — the embeddings store schema (`items.<file>.vector`,
`prompt_style.query`) and the `/api/embed` endpoint are load-bearing; a
re-derived probe that guesses `store["vectors"]` or `/api/embeddings`
returns empty matches with every check still green.

**Triple-wire every probe.** A probe exists in THREE places, and ask.py
needs all three:

1. `bridge.py` — the implementation (yours to author);
2. `needle_menu.json` — the menu entry (retrieval scoring runs off this);
3. `instance.py` — a `@needle.tool(triggers=...)` wrapper + `TOOLS.append(name)`
   (execution resolves through `inst.TOOLS`).

A probe wired into the menu but not instance.py *scores fine and then
silently vanishes* — the envelope reads `no probe scored > 0` even though
scoring found it. Never hand-sync the three files; use:

```bash
python3 scripts/register_probes.py --instance /path/to/instance \
    --probes probes.json          # triple-wires idempotently, clears ask cache
python3 scripts/register_probes.py --instance ... --probes probes.json --check
#   --check audits and exits 1 on half-wired probes (run it before delivery)
```

**Gate vocabulary is triggers + name + enum values ONLY.** The refusal
gate's `known_anywhere` check never reads probe descriptions. Every
domain noun a user might say — dataset words ("bills", "dataset"),
customer names, street names — must appear in some probe's **triggers**,
or the gate refuses a perfectly answerable question as
`no_probe_matches`. Putting those nouns in descriptions (the natural
instinct) fixes retrieval scoring and does NOTHING for the gate.

Key design fact: **semantic search is for discovery** ("which sheet is about
a re-run"); **precise numeric questions route to deterministic probes**
(votes, counts, rankings). Rebalancing trigger mass between a generic-word
probe and a specific one is expected fiddling — see the worked example.

### Phase 5 — Exhaustive verification

Run ALL of it; partial green is how v1 shipped wrong:

```bash
# a) every record parses through the strict model, individually:
python3 - <<'PY'   # or run_truth_checks.py --instance . --mode parse
import bridge
for fn in [...all filenames...]:
    r = bridge.image_details(fn); assert "record" in r, (fn, r)
PY

# b) full selection suite + traps through ask.py (one process per question):
python3 run_selection.py            # golden bank with expect_probe + MUST-refuse traps

# c) truth checks for EVERY record vs the catalog (not one exemplar):
python3 scripts/run_truth_checks.py --instance /path/to/instance

# d) gate/envelope conformance, exit 0 required
# e) clear the ask cache after ANY data change:
python3 -c "import json; json.dump({}, open('.ask_cache.json','w'))"
```

`run_truth_checks.py` reads `truth_checks.json` from the instance dir —
see `examples/truth_checks.json`. Record everything in `verification.txt`,
including corrections and superseded passes (keep the v1 record; the delta
IS the audit trail).

---

## Non-negotiable rules

1. Prove embedder modality before wiring (Phase 0). Never claim image-level
   search from a text embedder.
2. Identity crops before transcription; one image read per tool call; sha256
   as the anchor of record.
3. Zoom ≥3.5× before reading handwriting; uncertain ⇒ flagged + noted, never
   guessed.
4. Transcribe as-written; arithmetic disagreements are data (notes), not
   bugs to fix.
5. No empty dict/list values in catalog records. Ever.
6. Every record individually exercised in verification. A sampled pass is a
   rumor, not a result.
7. Semantic probes = discovery; numeric questions route to deterministic
   probes. Free-text args pattern-caged so the fast path owns them.
8. After any data OR menu change: rebuild embeddings for changed
   descriptions and clear the ask cache (menu edits change the menu version
   the cache is keyed by — stale triggers refuse fresh questions).
9. Embedder unreachable ⇒ honest unavailable digest; never fabricated
   matches.
10. Secrets/backend URLs via env (`OLLAMA_URL`), never model-facing args.

## Gotchas (earned the hard way)

| Symptom | Cause | Fix |
|---|---|---|
| Two records' contents swapped | parallel image reads paired by order | Phase 1 identity crops, one read per call |
| Handwritten digit wrong ("3" vs "—") | page-scale reading | Phase 2 ≥3.5× crops |
| "all checks green but data wrong" | sampled verification | Phase 5 per-record battery |
| `Extra inputs are not permitted` at ask time | empty `{}`/`[]` value flattened to bare key | transcribe_catalog rejects; omit key |
| `"024"` became `24` | profiler int-coercion | fix_profile force_str |
| model rejects valid future records | generator bounds over-fit to N samples | hand-relax constraints post-gen |
| stale answers after data change | ask cache keyed by menu version only | clear `.ask_cache.json` |
| probe X steals probe Y's questions | bare-token trigger mass imbalance | trim generic triggers (e.g. "documents") from the thief; put the distinguishing VERB tokens ("add up", "reconcile") in a compact trigger on the right probe |
| gate refuses an answerable question (`no_probe_matches`) though a probe clearly covers it | gate vocab = triggers+name+enums ONLY; descriptions are invisible to it | put the dataset's own nouns (customer names, "dataset", doc types) in TRIGGERS, not descriptions |
| new probe refuses with `no probe scored > 0` though scoring clearly finds it | probe in menu but NOT wrapped in instance.py (`inst.TOOLS` resolves execution) | triple-wire via `register_probes.py`; run it with `--check` before delivery |
| semantic probe returns `matches: []` with all checks green | probe re-derived with wrong store keys or endpoint | copy workflow.md §4 template verbatim: `items.<file>.vector`, `/api/embed` + `input`, `prompt_style.query` |
| `AttributeError: 'str' object has no attribute 'get'` building catalog | records.json wrapped in an object | now tolerated (bare list or `{"records": [...]}`); prefer bare list |
| zero-retrieval questions die as `no_probe_matches` before qualifier checks | gate order | expected; write traps to expect it |

## File map

```
scripts/test_embedder_modalities.py  Phase 0 — prove text-only vs multimodal
scripts/verify_pairing.py            Phase 1 — identity crops + sha256 manifest
scripts/crop_bands.py                Phase 2 — band/box zoom crops
scripts/transcribe_catalog.py        Phase 3 — records + file facts → catalog.json (with poison checks)
scripts/build_embeddings.py          Phase 3/4 — description → ollama embeddings (incremental by text-sha)
scripts/fix_profile.py               Phase 4 — profiler fixups from a config file
scripts/register_probes.py           Phase 4 — triple-wire probes (bridge→menu→instance.py), idempotent, --check audits
scripts/run_truth_checks.py          Phase 5 — exhaustive per-record + per-question truth battery
references/workflow.md               full walkthrough incl. probe code templates
references/vision-transcription.md   the transcription/uncertainty protocol
references/embedding-backends.md     ollama /api/embed behavior, prompt styles
references/verification.md           the battery + why sampled checks lie
examples/vote-images.md              complete worked case (incl. the v1→v2 correction)
examples/truth_checks.json           truth-battery format
```
