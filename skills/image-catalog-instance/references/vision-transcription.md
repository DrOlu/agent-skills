# Vision transcription protocol

How to read images so the catalog deserves trust. Written from a build
where two of four records shipped swapped and three figures were wrong —
all while every automated check passed.

## The three failure modes (and their counters)

| Failure | Counter |
|---|---|
| Content bolted to the wrong file | identity crops read one-per-call (Phase 1); sha256 manifest as anchor |
| Handwriting misread at page scale | ≥3.5× crops on every handwritten region; re-crop tighter rather than guess |
| Errors survive "green" checks | exhaustive per-record verification (Phase 5); sampled checks are a rumor |

## Reading order per image

1. **Identity crop first** (top band) — confirm what the file is before any
   field work. Write the mapping down explicitly.
2. **Structure pass** (2–2.5×): printed headers, table grids, row/column
   labels, checkboxes. Printed text is near-certain; note the layout so the
   handwritten values land in the right fields.
3. **Values pass** (3.5–4.5×): numbers, names, dates, signatures-as-text.
   One region per crop; one crop per tool call.

## Confidence rules

- **Printed text**: read at 2×; re-crop at 3× if the print is small or
  blurred (serial numbers often are).
- **Handwritten digits**: read at ≥3.5×. Cross-check the "in words" column
  when the form has one; figures agreeing with words is strong evidence.
- **Handwritten names**: transcribe best-effort, mark the record
  `uncertain_fields: true`, and name the uncertain fields in `notes`
  ("PO surname letters Ademiyi/Adeniyi uncertain"). Do not substitute a
  real-world person's name for what is written — note the resemblance if
  useful ("matches candidate X of election Y"), but store the reading.
- **Ambiguity you cannot resolve at zoom**: keep the best reading ONLY with
  the uncertainty flag; if genuinely illegible, store null and say so in
  notes. A blank is honest; a wrong value is poison.

## The as-written rule

Transcribe what is ON the form, never what SHOULD be:

- If the form's arithmetic doesn't reconcile (issued − unused ≠ used),
  record the written values and put the discrepancy in `notes`. Real
  scanned forms contain errors, and those errors are frequently THE story
  (irregular result sheets, padded invoices). "Correcting" them destroys
  the evidence.
- A dash "—", "NIL", or a crossed-out cell means what it means on the form:
  dash/nil → 0 with a note saying it was written as a dash; crossed-out →
  note the crossing, store what is actually the case after the crossing.
- Blank office/election lines → null election, with a note; if the content
  identifies the event anyway (candidate lineup), say that in notes and the
  description — as inference, clearly labeled.

## descriptions = embedding inputs

The `description` field is not documentation — it IS the semantic-search
index for that image. Write it as a complete, self-contained content
summary: form type, jurisdiction, location codes, every key figure, all
party/category scores in words, people, dates, physical features (QR code,
stamps, watermark), and caveats. 100–800 words. If it isn't in the
description, semantic search can't find it.

## Bookkeeping

- Every record: `uncertain_fields: bool` + `notes` naming exactly which
  fields are shaky and why.
- Every correction pass increments the version note in the extraction
  script's docstring (v1 → v2 with the delta). verification.txt keeps both
  passes. The correction trail is part of the deliverable.
- File facts (sha256, dims, size) are ALWAYS programmatic, never visual.
