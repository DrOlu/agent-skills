# Worked example: vote-images (4 INEC result sheets, ollama embeddinggemma)

The real build this skill was distilled from — kept as the reference case,
INCLUDING the correction pass, because the corrections are the lesson.

## The source

`george/vote/`: four scanned Nigerian election result sheets.

- `01.png` — INEC EC 60(E), Publication of Result of Poll, EDO, name NEW
  BENIN/ORODO, code 05/008/12. Candidates: Asue Ighodalo (PDP) 26, Monday
  Okpebhole (APC) 19, Olumide Akpata (LP) 9, NRM 2, ADC 1, ADP 1. Office
  line blank on the form; candidate lineup indicates the 2024 Edo
  governorship election. Crossed-out stray "P.D.P" line above row 1.
- `02.jpg` — INEC EC 8A, 2023 Presidential, LAGOS (024), Lagos Mainland,
  Otto/Iddo, FAGBAYI ST. (BY HOUSE 9), serial PE/0009130. Turnout AS
  WRITTEN: 490 / 114 / 396 / 283 / — (dash, nil) / 3 / 111 / 114. Scores:
  APC 81, PDP 17, LP 12, ZLP 1. PO Solagbade Saheed A., 25/02/2023.
- `03.jpeg` — INEC EC 8A, 2023 Presidential, BAUCHI (005), Birshi/Miri,
  OPP: DIVINE INTERNATIONAL ACADEMY, serial PE/0000923. Turnout: 479 / 371
  / 471 / 160 / NIL / — / 370 / 371 (accredited 371 = used 371; issued−
  unused does NOT reconcile — a known-irregular sheet). Scores: LP 313,
  PDP 51, ZLP 2, ADC 1, APC 1, BP 1, NNPP 1.
- `04.jpg` — INEC EC 8A(i), 2024 Plateau North Senatorial Re-run, PLATEAU
  (031), Jos South, Gyel 'A', GSS GYEL, serial SD/0001825, QR code present.
  Turnout: 198 / 53 / 198 / 145 / 0 / 0 / 53 / 53 — fully reconciling.
  Scores: ADP 39, ADC 7, LP 3, NNPP 2, APC 1, ZLP 1.

## Phase 0 result (the reason descriptions power the embeddings)

`test_embedder_modalities.py` equivalent run:
cos(text-only, text+image) = **1.0000** → `images_ignored`. embeddinggemma
is text-only; ollama accepts the `images` field and silently ignores it.
Pipeline: image → full content transcription → `title: none | text: …`
embedding (768-dim) → cosine index. Query side: `task: search result |
query: …`, cached by sha1.

## Instance shape (14 probes)

peek / count_records / summary / count_by_{form_type, form_title,
election, state, leading_party, format} + image-specific:
`semantic_search_images` (free-text query, REQUIRED + pattern-caged
`[\s\S]{3,}` so the deterministic fast path captures the whole question),
`find_similar_image` (enum-caged filename; stored vectors, no ollama at
ask time), `image_details` (enum-caged; no-arg → all-records digest),
`party_votes` (18-party enum), `rank_by_valid_votes`.

Trigger-mass war story: "votes for LP" first routed to
`rank_by_valid_votes` because four of rank's triggers contained the bare
token "votes" vs party_votes' three. Fix: trimmed rank to two triggers and
gave party_votes one compact multi-party trigger
("votes for lp apc pdp adp nnpp") plus the party abbreviations in its
description. Re-ran the FULL suite after the menu change (rule).

## The correction pass (v1 → v2) — the core lesson

v1 read images in parallel batches and trusted call order for file
identity. Result: **01.png and 02.jpg were content-swapped** (both
transcriptions were pixel-accurate — attached to the wrong files). Also
shipped: Lagos #5 spoiled read as "3" (actually a dash), Lagos issued read
as "376" (actually 396), Edo name "TORBO" (actually ORODO), Edo APC
candidate "Osakhinde" (actually OKPEBHOLE), Bauchi turnout stack misread
row-shifted (237/160/100 instead of 371/471/160), Bauchi reg area
"BIRSHIM/RI" (actually BIRSHI/MIRI).

The user flagged ONE cell: "#5 on 02.jpg has - not 3". Full re-examination
at 2.2×–4× (single-file crops, one read per call) found everything above.

Latent bug the re-pass surfaced: Bauchi's record carried
`"party_agents": {}` → flattened to a bare `party_agents` key → strict
model `extra=forbid` reject → `image_details('03.jpeg')` had been crashing
all along, unseen because v1 truth checks never asked for that specific
record. Hence the skill rules: no empty dict/list values (build-time
rejection) and per-record parse verification (not sampled).

## v2 verification results

- per-file identity + parse: 4/4
- selection + traps through ask.py: 20/20
- truth battery: 8/8 — LP per-sheet {01:9 Edo, 02:12 Lagos, 03:313 Bauchi,
  04:3 Plateau}; Lagos details = 396/dash/111/114; Bauchi = 371/471/160
  Birshi/Miri; rank = Bauchi 370 > Lagos 111 > Plateau 53 (EC 60E listed
  separately — it has no valid-votes count); semantic "senatorial re-run"
  → 04.jpg first.
- gate conformance: 17/17, exit 0
- embeddings rebuilt from corrected descriptions; `.ask_cache.json`
  cleared before re-verification.

## Ask examples that work on this instance

```
find images about a senatorial re-run        -> semantic, 04.jpg first
similar image to 01.png                      -> embedding neighbors
votes for LP                                 -> deterministic, Bauchi 313
details of image 02.jpg                      -> full parsed record
which sheets are from the 2023 Presidential Election
highest valid votes                          -> rank + honest EC 60E note
```
