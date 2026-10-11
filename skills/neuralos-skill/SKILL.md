---
name: neuralos-skill
description: Run neuralOS by Neural AI (the on-device tool-calling foundation model, decoupled from Cactus Compute needle and now distributed independently as the `neuralos` package — 121M params, 2-bit, ~35 MB weights + engine, bundled into every install) for tool calling, structured extraction and text embeddings that runs entirely offline on CPU across macOS, Linux and Windows. Install is one line on every OS — `pip install neuralos` (PyPI, all platforms, engine + weights bundled, fully offline), `npm install neuralos`, or the curl / PowerShell one-liners from neuralos.ng. Use this skill whenever the user mentions neuralOS, needle, cactus-needle, .cact archives, on-device / offline / edge LLM tool calling, an agent that picks functions and fills arguments without a cloud API, or a tiny model on a server / phone / robot / Raspberry Pi. Also use it when wiring ANY agent harness (Claude Code, SuperAgent, Pi, OpenCode, cron, CI) to consume a neuralOS instance — the ask envelope, exit codes and refusal gate contract (GATE_VERSION 1) — or when an agent misbehaves (wrong tool, refused calls, "ungrounded" errors) or when wiring OS CLIs as LLM-callable tools.
---

# neuralOS — on-device tool calling

> **Branding scope (updated).** neuralOS is now a fully independent product
> and distribution: GitHub `DrOlu/neuralOS`, PyPI **`neuralos`**, npm
> **`neuralos`** (v3.9.6+ = this runtime), site **neuralos.ng**. The import
> package and binaries keep their upstream names — `import needle`,
> `needle3.cact`, CLI `needle` / `neural`. Upstream `cactus-needle` remains a
> separate project; neuralOS 3.0.3 ships upstream grounding fixes with the
> 3.0.2 engine bundled into every install (fully offline).

neuralOS is a foundation model built for tiny devices: a single 121M-parameter
"Simple Attention Network" quantised to 2-bit, shipped as one ~35 MB weights
file (`needle3.cact`) plus an engine library under 1 MB. It runs offline on a
CPU — roughly 100 MB of RAM, hundreds of tokens per second on a laptop — with
no API key, no GPU and no network. It does three things:

1. **Tool calls** — given your function schemas and a plain-English request, it
   picks the right function and fills every argument from what was said. Ask
   for two things and you get two calls in order; ask for something no tool
   covers and you get an empty list, not a guess.
2. **Structured extraction** — declare a shape, hand over messy text, get
   typed fields back; the decode grammar guarantees the output parses.
3. **Text embeddings** — a vector for a sentence (neuralOS 3 only).

For the companion skill that turns raw data sources into neuralOS
instances (profile any source → Pydantic models → generated menu, bridge and
agent), see `neuralos`.

Everything below was verified live against **neuralOS 3.0.3** (bundled 3.0.2 engine) (Python
API, CLI, and the standalone engine on macOS arm64, with source-level checks
of the Windows/Linux paths).

The model is tiny (121M params). It is reliable **when tools are designed for
it** — the rules in "Tool design" below are not optional polish, they are the
difference between a working agent and a flaky one.

## Pick a surface

| Your situation | Surface | Read |
|---|---|---|
| Python app/script; agent loop that **executes** the tools it calls | Python API — `import needle` | `references/python-api.md` |
| One-shot call generation from a terminal; deterministic output | `needle run` CLI (needs jax + a 242 MB checkpoint) | `references/cli.md` |
| No Python at runtime — servers, Windows services, edge devices, embedding in C | Standalone engine binary — `./needle --model needle3.cact` | `references/engine-binary.md` |
| **Windows hosts where PowerShell is the ONLY permitted runtime** (no Python, ever) | Engine selection + PowerShell execution loop — `needle.exe` / `neural.exe` | `references/windows-powershell.md` |
| You need a typed **judgment** (guardrail, triage, classify into ≤10 classes), offline — not a tool call | laya decision model — `pip install laya` | `references/decision-models.md` |
| Setting up neuralOS (± the laya decision seam) on a **completely new host** | Cold-start runbook: interpreter → runtime → smoke tests | `references/new-host-bootstrap.md` |
| The model picked the wrong tool / refused / looped / mangled args | Tool design rules (read this before debugging anything else) | `references/tool-design.md` |
| It errored or behaved oddly | Symptom table | `references/troubleshooting.md` |

## Install

```
# PyPI — first choice on all platforms (engine + weights bundled, offline)
pip install neuralos

# Node.js runtime (weights bundled; the old npm `neuralos` daemon -> rterm-backend)
npm install neuralos

# one-line bootstrappers (venv + checksums + PATH shim)
curl -fsSL https://neuralos.ng/install.sh | sh          # macOS / Linux
irm https://neuralos.ng/install.ps1 | iex               # Windows PowerShell
```

Bringing up a **brand-new host** end to end (interpreter → runtime →
engine binary → optional laya decision seam → readiness smoke tests)?
Follow the sequenced runbook: `references/new-host-bootstrap.md`.

- On **Windows**, prefer `py -m pip install neuralos`. The engine ships
  as a prebuilt wheel (`libneedle3.dll` (bundled in the wheel)) — no compiler needed.
- The `neuralos` wheels bundle the engine + weights — no first-use download.
  (The upstream `cactus-needle` package still downloads into
  `~/.cache/cactus-needle/v3/<engine-version>/`; set `NEEDLE3_LIB_PATH` to
  override the library location if you use it.)
- If the machine must never touch the network, pre-seed that cache from
  another box, or use the standalone engine bundle (below) which needs no
  Python at runtime.
- Telemetry is on by default. Disable before importing:
  `NEEDLE_TELEMETRY=0` and `DO_NOT_TRACK=1`.
- **Multi-Python gotcha:** on machines with several Pythons (Homebrew vs
  python.org vs system), the `needle` CLI lives in the interpreter's bin dir
  that `pip install`ed it. If `import needle` fails under `python3`, find the
  right interpreter (`ls */bin/needle`, `pip show neuralos`) — or see
  the re-exec pattern in `references/troubleshooting.md`.

## Quick start (Python API)

```python
import needle

@needle.tool
def get_weather(city: str) -> dict:
    """Get the current weather for a city."""
    return {"city": city, "temp_c": 27, "sky": "clear"}

agent = needle.Needle(tools=[get_weather])
response = agent.run("what's it like in Lagos right now?")
print(response["results"])   # [{'city': 'Lagos', 'temp_c': 27, 'sky': 'clear'}]
```

The decorator reads the signature for argument types and the docstring for
the tool description (an `Args:` section documents parameters). `run()` picks
the tool, executes it **in-process**, feeds the return value back to the
model, and returns the final response. Full API — including `Field`
constraints, extraction and embeddings — in `references/python-api.md`.

## Consume an instance from ANY agent harness (macOS / Linux / Windows)

A neuralOS instance is consumed through one universal, harness-agnostic
contract — no MCP, no SDK, no lock-in. From Claude Code, SuperAgent, Pi,
OpenCode, a cron job, CI, or a plain shell:

```bash
# the universal runner (this skill) — always-JSON, every OS:
python scripts/ask_instance.py /path/to/instance "which pages mention risk management"
```

**The contract** (stable — build integrations on it):

| Exit | Meaning | stdout |
|---|---|---|
| `0` | answered | the instance's JSON envelope (`refused: false`, `probe`, `results`, …) |
| `2` | refused / nothing produced | envelope with `refused: true`, `refusal_reason`, `gate_version: 1` |
| `3` | harness-level failure (no ask.py, bad menu shape, timeout, unparsable output) | `harness_error` envelope naming the cause |

stdout is **always exactly one JSON envelope** — never prose. stderr is for
humans. The interpreter for `ask.py` resolves `--python` → `NEURALOS_PYTHON`
→ the interpreter running the script (correct on Windows, where `python3`
often does not exist).

Parsers for common harness languages:

```python
# Python
import json, subprocess, sys
p = subprocess.run([sys.executable, "ask_instance.py", instance, q],
                   capture_output=True, text=True)
env = json.loads(p.stdout)          # ALWAYS parses
if p.returncode == 0:
    use(env["results"])
elif p.returncode == 2:
    tell_user(f"cannot answer: {env['refusal_reason']}")
else:
    raise RuntimeError(env["error"])    # harness error (exit 3)
```

```javascript
// Node.js
const { execFileSync } = require('child_process')
const out = execFileSync('python', ['ask_instance.py', instance, q],
                         { encoding: 'utf-8' })
const env = JSON.parse(out)          // ALWAYS parses
if (env.refused === true) console.log('refused:', env.refusal_reason)
else console.log(env.results)
```

```powershell
# Windows PowerShell
$out = python scripts\ask_instance.py C:\instances\reports "how many pages" | ConvertFrom-Json
if ($out.refused) { Write-Host "refused: $($out.refusal_reason)" }
else { $out.results }
```

The runner also **enforces the action-intent refusal gate itself, before
ask.py runs** — so gateless hand-authored instances (and any non-SuperAgent
consumer) still refuse "delete all the reports" instead of executing.
`needle_menu.json` may be a bare probe array, `{"menu": [...]}` or
`{"probes": [...]}`; anything else is a level-3 error.

Other surfaces, same instances: `serve.py` (HTTP `POST /ask`), `askd.py`
(resident daemon below), and `gen_openapi.py` (in the `neuralos` skill)
emits `openapi.json` + `mcp.json` for OpenAPI clients and MCP hosts.

## Refusal gate & ask envelope (GATE_VERSION 1)

Every ask ends in exactly one of two honest outcomes: a confident answer or
a refusal. The gate is a pure menu+question check (no probe, no model,
microseconds) with four refusal reasons: `action_intent` (imperative verb no
probe claims — enum values are data, not capabilities),
`no_probe_matches`, `dropped_filter:<qualifier>`, `low_coverage`. Refusals
exit 2 with `refused: true`, the named `refusal_reason`, `gate_version` and
`results: null`; every ask is audited to the instance's `ask_audit.jsonl`
with `candidates_retrieved` — the gap log that feeds menu extension.
Full rules, envelope schema, audit record shapes (including the
`"via": "superagent-ts"` marker on TS-gate refusals) and the black-box
conformance suite: `neuralos` skill → `references/refusal-gate.md`;
run conformance against any instance with:

```bash
python <neuralos skill>/scripts/gate_conformance.py --instance /path/to/instance --verbose
```

## Performance: resident daemon (amortize weights load)

Process-per-ask reloads the weights every time. For services, run the
resident daemon (`scripts/askd.py` in the `neuralos` skill): one process,
many asks, full pipeline (audit, cache, gating, fast path) behind
`POST /ask`. Pin the runtime (`neuralos==3.0.3`) in deployments and re-read
the contract above on any upgrade — the results/function_calls semantics are
version-specific.

## Selector & results contract (needle 3.0.3 — verified live)

Non-negotiable runtime facts. Code that ignores them mis-answers silently:

- **`function_calls` is ALWAYS `[]`** — even when a tool executed and
  `results` is correct. Route on `results`; never branch on `function_calls`.
- **`results` persists across `agent.run()` calls on the same agent object.**
  A question that produces no parsed call returns the PREVIOUS ask's data.
  Either one question per process, or an explicit empty-results guard that
  errors out (exit non-zero) instead of printing stale data.
- **Menus above ~12 tools defeat in-context selection.** Use a structured
  retrieval front-end — lexical top-K over triggers/name/description, with a
  deterministic fast path that executes the rank-1 probe directly when its
  enum-caged argument appears verbatim in the question. The `neuralos` skill
  generates this (`ask.py`) for every data-source instance; reuse that
  pattern.
- **Possessive phrasings never ground** ("Ireland's top customers") —
  normalize to "top customers in Ireland" before selection (derive the
  values from the menu's own enum cages).
- **Trigger bloat degrades selection globally** — adding dozens of literal
  strings to one probe measurably hurt unrelated picks in live testing.
  Prefer patterns; re-run the full selection suite after menu changes.
- **`tool_index_path` is accepted but the index may never be written** on
  3.0.3 — don't rely on `.tool_index.json` existing; verify or use retrieval.

## Tool design — the rules that make a 121M model reliable

These came from live failure modes, not style guides. Details and code
patterns in `references/tool-design.md`.

1. **Give every tool `triggers`.** `@needle.tool(triggers=["list databases",
   ...])`. Without them, tool selection is flaky — the model intermittently
   refuses a perfectly matching tool ("no connectivity or network tools
   available", often with high confidence).
2. **Never make secrets tool arguments.** neuralOS's strict grounding blocks
   arguments it cannot verify against the input (`ungrounded password`), and
   secrets should not travel through an LLM anyway. Bake credentials into
   constants; let the model pick *what* to do, not recite keys.
3. **Keep the result you return small.** `run()` feeds your tool's return
   value verbatim back to the model. A multi-kilobyte result makes a 121M
   model lose the thread and repeat unrelated calls until `max_steps`. Return
   a compact digest and keep the full payload in a variable the caller reads.
4. **Two asks per turn, maximum.** "Do X then Y" reliably yields two calls in
   order; a three-part compound drops the third. Split into follow-up
   questions.
5. **Judge success by `response["results"]`, not by the final turn.** After
   execution the final response has `function_calls: []` and
   `type: "respond"` — that is success, not refusal.
6. **Constrain arguments in the grammar, don't hope.** `Field`/`Annotated`
   with `ge/le`, `pattern`, `enum`, `const`, or `Literal` types make invalid
   values unrepresentable. The tiny model *will* otherwise fill `host='mysql'`
   from the word "MySQL" in your prompt.
7. **The Python engine injects a date fact** (`date: YYYY-MM-DD HH:MM`) into
   every prompt by default; the minutes drift between runs and can flip tool
   selection. For reproducibility pass a fixed `system=` and
   `auto_date=False`. The CLI and standalone engine don't inject dates.

## Standalone engine (no Python at runtime)

The raw-C engine binary runs the same `needle3.cact` weights with no JAX, no
Python — ideal for servers and Windows boxes:

```bash
# macOS / Linux — download a platform bundle and place the weights beside it
python scripts/bootstrap_engine.py            # auto-detects this platform
./macos-arm64/needle --model needle3.cact --tools tools.json \
    --prompt "give me revenue breakdown by country"
```

```powershell
# Windows
python scripts\bootstrap_engine.py --platform windows-x86_64
.\windows-x86_64\needle.exe --model needle3.cact --tools tools.json --prompt "..."
```

The binary is **call-selection only**: it emits the chosen call as JSON
(name, arguments, reasoning, confidence, throughput stats) and does **not**
execute anything — your code runs the tool. It is deterministic (greedy
decode), needs ~100 MB RAM, and can also serve HTTP (`--serve`, default port
8080: `POST /complete {"input": "..."}`, `POST /reset`). Platforms:
macos-arm64, linux-x86_64/arm64/armv7/riscv64/mipsel,
windows-x86_64/arm64, plus android, ios, tvos, watchos and wasm variants.
Full details in `references/engine-binary.md`.

## Bundled scripts

- `scripts/bootstrap_engine.py` — jax-free download of any platform's engine
  bundle + weights, prints the exact run command. Cross-platform.
- `scripts/export_tools.py` — dump the `@needle.tool` schemas from a Python
  module into `tools.json` for the engine binary or `needle run --tools`.
- `scripts/ask_instance.py` — the harness-agnostic runner: one question →
  one JSON envelope, exit 0 answered / 2 refused / 3 harness error, with the
  action-intent refusal gate enforced pre-execution. Works on every OS,
  from every harness.
- `tests/` — unit tests (stdlib `unittest`) for the exporter (import-safety
  failures raise a clear SystemExit; the full menu export round-trips
  through the real `@needle.tool` decorator when the engine is installed)
  and for the harness runner (envelope passthrough, exit-code contract,
  harness-error envelopes, menu shapes, the runner's own action gate
  including the capability carve-out and the enum-values-are-data rule,
  interpreter resolution). Run:
  `python -m unittest discover -s skills/neuralos-skill/tests`.


## Decision model for judgments (laya, offline)

neuralOS picks tools and writes their arguments — an **action model**. For
**judgment-shaped** work in the same app (guardrails, triage, severity
scoring, classify into ≤10 well-described classes) the fleet's offline
package of choice is **laya** (`convaiinnovations/laya`, Apache-2.0,
`pip install laya`, no cloud, no key, free per call): state + typed
choice/noul/score questions in, picks + probabilities + calibrated
confidence out. Keep it advisory and env-gated, keep choices ≤10 options
(above that laya's confidence is uncalibrated), and do NOT use it for
tool/probe selection — the measured verdict is that the 121M engine beats
the 421M decision model at selection (15/18 vs 8/18 on a 37-probe menu).
Full split, wiring pattern and rules: `references/decision-models.md`; the
`use-laya` skill is the API reference; the `neuralos` skill's
`references/decision-model-integration.md` carries the measured pilot.

## Troubleshooting quick table

| Symptom | Cause → fix |
|---|---|
| `ModuleNotFoundError: neuralOS` | Wrong interpreter → `references/troubleshooting.md` §1 |
| Result says `ungrounded password`/`ungrounded <arg>` | Grounding blocked a secret/fabricated value → §2 |
| Model fills nonsense (`host='mysql'`) | Unconstrained string arg → triggers + constraints → §3 |
| Same tool called repeatedly until max_steps | Tool result too large fed back → digest+stash → §4 |
| Third request of a compound ask never happens | 2-ask limit → split the ask → §5 |
| Refusal with high confidence, no call | Missing triggers / date-fact drift → §6 |
| `needle run`/`build` demand jax | Use the engine binary path instead → §7 |
| Garbled unicode in outputs | Charset on the wrapped CLI / corrupted source data → §8 |
| Nothing happens on macOS double-click | Window flashes closed — run from Terminal → §9 |

Expanded causes and fixes: `references/troubleshooting.md`.
