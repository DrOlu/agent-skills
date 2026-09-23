---
name: use-laya
description: Call Laya — ConvAI Innovations' open-source System One decision model (421M, RLCD-calibrated, Apache-2.0) — for fast, typed, probabilistic decisions that run entirely OFFLINE on CPU/Apple GPU, no API key, no cloud, no cost per call. Use whenever code or a task needs a quick semantic judgment instead of generated text — classify, route, triage, score severity, verify a claim, guardrail a prompt, yes/no detection, pick the best option, or rank candidates — especially where cloud calls are not allowed (air-gapped, privacy, cost, offline fleet). Question and matrix files written for the old cloud Jev (use-jev skill) work UNCHANGED — same choice/noul/score shapes. NOT for generation, summarization, rewriting, drafting, open-ended extraction, or multi-step reasoning — use an LLM (or neuralOS for tool calls) for those.
---

# Laya — typed decisions, offline

Laya (`convaiinnovations/laya`) is a **System One decision model** in the Jev
class: it takes a *state* (text or JSON) plus typed *questions*, and returns
*typed answers with probabilities and calibrated confidence* — no strings to
parse, no hallucinated values, no options outside the ones you defined.

Unlike cloud Jev, Laya runs **on your machine**: a 421M-parameter
ModernBERT-large encoder with an RLCD-calibrated decision head, shipped as a
plain `pip` package under Apache-2.0. First use downloads one checkpoint
(~843 MB fp16); after that it is fully offline — no key, no endpoint, no
per-call cost, no network.

Think of it as a local function call:
`unstructured state in → typed probabilistic decisions out`.

Live-verified on this machine (Sept 2026): **~0.6–0.9s per decision on Apple
GPU (mps), including an embedding shortlist; checkpoint loads in ~17s from
cache.** Confidence buckets and their gotchas are measured, not claimed.

## When to use / not use

**Use Laya for** — a judgment a knowledgeable person makes in a few seconds
given the right context, where cloud calls are unwanted or unavailable:

- Classify / route: "Which team handles this ticket?", "Which probe answers this?"
- Detect: "Does this message request a refund?", "Is this prompt a jailbreak?"
- Score on a rubric: "How severe is this incident?", "How frustrated is this customer?"
- Verify / judge: "Does this passage support the claim?", "Is this tool call unsafe?"
- Guardrail LLMs: score prompts, reasoning traces, or outputs before acting.
- Offline fleets: no egress, privacy-sensitive data, or $0 marginal cost.

**Do NOT use Laya for** — generation, summarization, rewriting, drafting,
open-ended extraction, multi-step reasoning, or *writing arguments for a
tool call*. Those are LLM/action-model tasks. Laya only picks among options
you listed — pair it with neuralOS when the decision must become an action
with arguments (see the neuralos skill's decision-model integration note).

## Install

```
pip install laya                    # Python 3.9+; macOS, Linux, Windows
```

- Pulls `torch` if absent; no GPU required (CPU, Apple mps, and CUDA all work;
  the device is picked automatically and falls back to CPU on GPU memory
  errors).
- First call downloads the checkpoint into the HF cache:
  `~/.cache/huggingface/hub/models--convaiinnovations--laya` (Windows:
  `%USERPROFILE%\.cache\huggingface\hub\...`). ~843 MB.
- **Air-gapped hosts:** pre-seed that cache directory from another machine —
  after the first download no network is ever needed.
- **Slow CDN?** `pip install hf_transfer` and set
  `HF_HUB_ENABLE_HF_TRANSFER=1` for parallel chunked download.
- **Multi-Python gotcha:** on machines with several Pythons, install into the
  interpreter that will run your code (`python3.12 -m pip install laya`) and
  check with `python3.12 -c "import laya"` — same discipline as the
  neuralOS/needle runtime.

## Quick start (Python API)

```python
from laya import load

agent = load("convaiinnovations/laya")   # or a local checkpoint dir path

result = agent.system_one(
    "Customer says their card was charged twice for the same order.",
    {
        "is_billing": {"type": "noul",
                       "instructions": "Is this a billing problem?"},
        "team": {"type": "choice",
                 "instructions": "Which team handles it?",
                 "criteria": {"billing": "payment disputes",
                              "technical": "bugs or integration problems"}},
    },
)
print(result["answers"]["team"]["choice"])        # "billing"
print(result["answers"]["team"]["confidence"])    # calibrated 0-1
```

Every question sees the same state, is evaluated independently, and all
questions in one call share a single forward pass — adding questions barely
changes latency.

## The three question primitives

| Type | Answers | Returns |
|------|---------|---------|
| `noul` | Is this true? | `noul` 0–1 (probability of yes) |
| `choice` | Which option? | `choice`, `probabilities` (full distribution), `confidence` |
| `score` | Which level? | `score` (probability-weighted, may fall between levels), `legend`, `probabilities`, `confidence` |

Shapes (identical to the old cloud-Jev shapes — Jev-era matrix files load
unchanged):

```json
{
  "is_urgent": {"type": "noul", "instructions": "Does this convey urgency?"},
  "department": {"type": "choice", "instructions": "Which team?",
                 "criteria": {"billing": "...", "technical": "...", "sales": "..."}},
  "frustration": {"type": "score", "instructions": "How frustrated?",
                  "criteria": ["Calm, just stating facts", "Frustrated but civil", "Very angry"]}
}
```

`instructions` is required on every question. Choice `criteria` is a dict of
label → description (or a bare list of labels); score `criteria` is an
ordered list of level descriptions, index 0 first; noul `criteria` is
optional `{"true": ..., "false": ...}`.

## Calibration rules — measured, and load-bearing

Laya ships per-bucket temperatures; **the checkpoint's `choice:11+`
temperature is invalid (0.10, outside [0.5, 5]) and gets clamped**, so:

1. **Keep choice questions to ≤10 options** (calibrated buckets: `choice:2`,
   `choice:3-5`, `choice:6-10`, `noul:2`, `score:3-5`). Above 10 options the
   package itself warns: *"Treat confidence from the affected entries as
   uncalibrated."* Probabilities are still usable; do not threshold
   confidence there.
2. **High-cardinality choice (more than ~10 options)? Shortlist first:**
   embed the state and each option, keep the top 9 (+ an explicit
   `no_match`), decide over those. The laya package ships the pieces
   (`laya.shortlist.predict_shortlist`, `embed_fn_from_agent`):

   ```python
   from laya import load
   from laya.shortlist import predict_shortlist, embed_fn_from_agent

   agent = load("convaiinnovations/laya")
   criteria = {**{name: desc for ...}, "no_match": "none of these fits"}
   result = predict_shortlist(agent, state,
                              {"pick": {"type": "choice", "instructions": "...",
                                        "criteria": criteria}},
                              embed_fn_from_agent(agent), k=9)   # 9+no_match=10 -> calibrated
   pick = result["answers"]["pick"]
   ```

   `embed_fn_from_agent` mean-pools laya's own encoder — convenient, but it
   is a decision encoder, not a bi-encoder. On menus where fine word-level
   matching matters (tool/probe routing), a dedicated embedding model
   shortlists measurably better.
3. **Confidence thresholds** (collapses the distribution into one number):
   **< 0.5** don't act — escalate or gather more state; **0.5–0.9** proceed
   with caution, flag for review; **> 0.9** act automatically. Scale with
   stakes, exactly as with Jev. If you only need the best option, take the
   argmax of `probabilities` instead.

## Context budget

The checkpoint trims to `max_len=512` tokens total; option descriptions share
a `head_max_len=192` budget. A question whose rendered options exceed the
head budget raises `ValueError: options exceed head_max_len` — shorten the
descriptions or shortlist. Keep states compact: put the decision-relevant
facts in, leave the kitchen sink out.

## Writing good questions

- **One narrow judgment per question.** Split independent factors into one
  question each; combine in code with your own weights.
- **Question ids are for your code** — write the complete question in
  `instructions`.
- **State:** string for simple cases; JSON with named fields for multi-part
  context; reference nested parts in `instructions` with backticked paths.
- **Choice:** add a `no_match` / "none of the above" option whenever the list
  may not cover the input.
- **Noul:** 0.5 means genuinely uncertain, not "medium". To measure a level,
  use `score`.
- **Score:** ordered list of concrete, self-standing level descriptions.

## The `laya` helper (bundled in this skill)

```bash
laya request.json          # body: {"state": ..., "questions": ...} ("model" injected if absent)
cat req.json | laya        # stdin works too
```

Resolves the interpreter that has `laya` installed (current Python first,
then `$LAYA_PYTHON`, then the usual candidates), warns on uncalibrated 11+
option choices, and prints the answers JSON. No key resolution — there is
no key. Exit 2 on a request it cannot run.

## Performance envelope (measured here)

- Decision latency: ~0.6–0.9s/call on Apple GPU including shortlist
  embeddings; the raw forward pass is tens of ms — the tail is state
  building and Python overhead.
- Cold load: ~17s from cache (843 MB fp16 into mps); ~11 min on a very
  throttled connection for the one-time download (use hf_transfer).
- Cost: $0, forever, offline. Context 512 tokens.
- Accuracy posture: calibrated confidence in the documented buckets; the
  chinook pilot (37-way probe routing) showed local Laya does NOT match
  frontier cloud Jev on fine trigger-word menus (8/18 vs 14/18) — keep
  decision questions well-scoped and small-optioned, and prefer a
  purpose-built selector for tool routing (see the neuralos skill).

## Troubleshooting

- `ModuleNotFoundError: laya` → wrong interpreter; see the multi-Python note
  above, or set `$LAYA_PYTHON` for the helper.
- `RuntimeWarning: ... invalid temperatures ... choice:11+ ... uncalibrated`
  (at load time) → fires once on every load because the SHIPPED config
  carries the invalid value; it only affects *your* questions that have 11+
  options. Keep ≤10 and ignore the warning.
- `options exceed head_max_len=192` → option descriptions too long; shorten
  or shortlist.
- Download stalls on a throttled CDN → `pip install hf_transfer` +
  `HF_HUB_ENABLE_HF_TRANSFER=1`, or parallel ranged `curl`.
- GPU memory errors → the package auto-falls-back to CPU; nothing to do.

## Reference

- Package: https://github.com/convaiinnovations/laya (Apache-2.0)
- Checkpoint: https://huggingface.co/convaiinnovations/laya
- Python API: `laya.load` / `Agent.system_one` / `laya.shortlist`
- Migration: this skill REPLACES the cloud `use-jev` skill (OpenRouter
  `~typesafe/jev-latest`). Matrix files written for Jev work unchanged;
  only the caller differs. Cloud Jev remains an option where frontier-scale
  decision quality justifies a network call — this machine's fleet default
  is Laya offline.