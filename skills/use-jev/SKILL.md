---
name: use-jev
description: >
  Call Jev — TypeSafe's System One decision model — through OpenRouter for fast,
  typed, probabilistic decisions. Use whenever code or a task needs a quick
  semantic judgment instead of generated text: classify, route, triage, score
  severity, verify a claim, guardrail a prompt, yes/no detection, pick the best
  option, or rank candidates. Returns structured answers with calibrated
  probabilities and confidence in ~1s at ~$0.04/MTok input (output free).
  NOT for generation, summarization, or multi-step reasoning — use an LLM for those.
---

# Jev — typed decisions via OpenRouter

Jev is TypeSafe AI's System One model. It is **not an LLM**: it takes a *state*
(text or JSON) plus typed *questions*, and returns *typed answers with
probabilities* — no strings, no parsing, cannot hallucinate, cannot return a
value outside your defined options.

Think of it as a frontier-intelligence function call:
`unstructured state in → typed probabilistic decisions out`.

Live-verified on OpenRouter (Sept 2026): **~1.1s round trip, $0.000016 per
typical call.** Output tokens are free; input is $0.042/MTok. Context 32k.

## When to use / not use

**Use Jev for** — a judgment a knowledgeable person makes in a few seconds given
the right context:

- Classify / route: "Which team handles this ticket?", "Which agent should take this task?"
- Detect: "Does this message request a refund?", "Is this prompt a jailbreak attempt?"
- Score on a rubric: "How severe is this incident?", "How frustrated is this customer?"
- Verify / judge: "Does this passage support the claim?", "Is this tool call unsafe?"
- Guardrail LLMs: score prompts, reasoning traces, or outputs before acting on them.

**Do NOT use Jev for** — generation, summarization, rewriting, drafting,
open-ended extraction, or anything needing extended reasoning. Those are LLM
tasks; coercing Jev into them fails because it does not generate text.

## The endpoint (OpenRouter, not chat/completions)

Jev is a *decisions model* on OpenRouter. The normal `/chat/completions` endpoint
**rejects it**. Use the decisions endpoint:

```
POST https://openrouter.ai/api/alpha/decisions
Authorization: Bearer $OPENROUTER_API_KEY
Content-Type: application/json
```

Model slug: `~typesafe/jev-latest` (the `~` prefix is required; always redirects
to the newest Jev). The request body is the TypeSafe-native shape:
`{"model", "state", "questions"}`.

## The `jev` helper (bundled in this skill)

```bash
jev request.json          # file containing {state, questions} — model injected if absent
cat req.json | jev        # stdin works too
```

The script resolves the key from `$OPENROUTER_API_KEY`, falling back to the
local scrt vault (`openrouter-api-key`), and prints the JSON response. Use it
for one-off judgments from the shell; write direct `curl`/SDK calls only when
embedding Jev in real code.

## Three question primitives

All three can be mixed in ONE call — every question sees the same state, is
evaluated independently and in parallel, and adding questions barely changes
latency.

| Type | Answers | Returns |
|------|---------|---------|
| `noul` | Is this true? | `noul` 0–1 (probability of yes) |
| `choice` | Which option? | `choice`, `probabilities` (full distribution), `confidence` |
| `score` | Which level? | `score` (position, may fall between levels), `legend`, `probabilities`, `confidence` |

### Request → response (live-verified example)

```json
{
  "model": "~typesafe/jev-latest",
  "state": "Hi, I've been trying to connect my Stripe account for 3 days and it keeps failing. I'm losing sales. Please help ASAP.",
  "questions": {
    "is_urgent": { "type": "noul", "instructions": "Does this message convey urgency or time-sensitivity?" },
    "department": {
      "type": "choice",
      "instructions": "Which team should handle this?",
      "criteria": {
        "billing": "Payment or subscription issues",
        "technical": "Bugs or integration problems",
        "sales": "Pricing or account questions"
      }
    },
    "frustration": {
      "type": "score",
      "instructions": "How frustrated is the customer?",
      "criteria": ["Calm, just stating facts", "Frustrated but civil", "Very angry, strong language"]
    }
  }
}
```

Response (one answer per question, keyed by your ids):

```json
{
  "model": "typesafe/jev-1.13-20260917",
  "answers": {
    "is_urgent": { "type": "noul", "noul": 0.98 },
    "department": { "type": "choice", "choice": "billing", "probabilities": { "sales": 0, "technical": 0.28, "billing": 0.72 }, "confidence": 0.57 },
    "frustration": { "type": "score", "score": 1, "legend": { "0": "Calm...", "1": "Frustrated...", "2": "Very angry..." }, "probabilities": { "0": 0, "1": 1, "2": 0 }, "confidence": 1 }
  },
  "usage": { "input_tokens": 377, "output_tokens": 57, "cost": 0.000015834 },
  "id": "gen-dec-...", "provider": "TypeSafe"
}
```

## Writing good questions

- **One narrow judgment per question.** If it weighs several independent
  factors, split it into one question per factor and combine the answers in
  code with your own weights. Change a coefficient, not a prompt.
- **Question ids are for your code** — the model never sees them. Write the
  complete question in `instructions`, even when the id seems obvious.
- **State**: string for simple cases; JSON with named fields for multi-part
  context (conversations, records, policies). Reference nested parts in
  `instructions` with backticked paths: `ticket.messages[0].text`.
- **Choice**: map of option → description. Add an `other` / "none of the above"
  option when the list may not cover every input. Up to 255 options
  (above that, score candidates first, then choose).
- **Noul** = probability of yes. 0.5 means genuinely uncertain — it is NOT
  "medium". If you want to measure a level, use `score` with defined levels.
- **Score**: ordered list of concrete, self-standing level descriptions
  (at least two). `score` may fall between levels; `legend` echoes them by index.

## Using confidence

`confidence` (0–1) collapses the probability distribution into one thresholdable
number. Solid defaults:

- **< 0.5** — don't act. Escalate to a human, ask for more info, or fall back.
- **0.5 – 0.9** — proceed with caution: confirm, flag for review, or gather more state.
- **> 0.9** — act automatically.

Scale thresholds with stakes: showing the wrong screen is recoverable; executing
a transfer is not — gate high-stakes actions higher. If you only need the *best
option*, take the argmax of `probabilities` instead of thresholding confidence.

## Troubleshooting

- `~typesafe/jev-latest is a decisions model and cannot be used with the
  chat/completions endpoint` → you used `/api/v1/chat/completions`; call
  `/api/alpha/decisions` instead.
- `is not a valid model ID` → missing the `~` prefix, or the slug is stale; use
  `~typesafe/jev-latest`.
- A large Zod-style `invalid_union` error → malformed question (e.g. missing
  `instructions`); read the `path` fields to find the offending question.
- 401 → key not resolved; check `OPENROUTER_API_KEY` or the scrt vault.
- Cheapest debugging: add more questions to the SAME call rather than sending
  more calls — state is tokenized once.

## Reference

- TypeSafe docs (source of truth): https://docs.typesafe.ai — API at
  https://docs.typesafe.ai/api, primitives at https://docs.typesafe.ai/primitives
- OpenRouter model page: https://openrouter.ai/~typesafe/jev-latest
- Native TypeSafe API (same body, different auth):
  `POST https://api.typesafe.ai/v1/systemone` with `TYPESAFE_API_KEY`
