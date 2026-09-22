---
name: neuralos-skill
description: Run neuralOS by Neural AI (the on-device tool-calling foundation model, formerly distributed as Cactus Compute needle — the two names refer to the same runtime; 121M params, 2-bit, ~35 MB weights + <1 MB engine) for tool calling, function calling, structured extraction and text embeddings that runs entirely offline on CPU across macOS, Linux and Windows. Includes a Windows/PowerShell-only variant (no Python at runtime; CLI answers to needle or neural, weights to needle3.cact or neuralOS.engine). Use this skill whenever the user mentions neuralOS, needle, cactus-needle, cactus compute, .cact archives, on-device / offline / local-first / edge LLM tool calling or function calling, an agent that picks functions and fills arguments without a cloud API, running a tiny model on a server / phone / robot / Raspberry Pi, PowerShell-only Windows boxes, or needs a zero-dependency engine binary that serves function calls over HTTP. Also use it when an agent misbehaves (wrong tool, refused calls, repeated calls, "ungrounded" errors), when wiring OS CLIs or subprocesses as LLM-callable tools, or when fine-tuning or exporting a .cact archive.
---

# neuralOS — on-device tool calling

> **Branding scope.** neuralOS is the product name (Neural AI). The runtime
> binaries and the Python package keep their upstream names — `needle`,
> `cactus-needle`, `needle3.cact` — and every command in this manual uses those
> real names so nothing here is aspirational. Visible name: neuralOS.
> Functional name: needle. On Windows-only / PowerShell-only hosts the CLI
> may be invoked as either `needle` or `neural` and the weights as either
> `needle3.cact` or `neuralOS.engine` — same runtime, both spellings work
> (see `references/windows-powershell.md`).


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

Everything below was verified live against **cactus-needle 3.0.2** (Python
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
| The model picked the wrong tool / refused / looped / mangled args | Tool design rules (read this before debugging anything else) | `references/tool-design.md` |
| It errored or behaved oddly | Symptom table | `references/troubleshooting.md` |

## Install

```
pip install cactus-needle          # Python 3.9+; macOS, Linux, Windows
```

- On **Windows**, prefer `py -m pip install cactus-needle`. The engine ships
  as a prebuilt wheel (`libneedle3.dll`) — no compiler needed.
- First use auto-downloads the engine + `needle3.cact` weights into
  `~/.cache/cactus-needle/v3/<engine-version>/` (~36 MB; on Windows:
  `%USERPROFILE%\.cache\cactus-needle\v3\<version>\`). Set
  `NEEDLE3_LIB_PATH` to override the library location.
- If the machine must never touch the network, pre-seed that cache from
  another box, or use the standalone engine bundle (below) which needs no
  Python at runtime.
- Telemetry is on by default. Disable before importing:
  `NEEDLE_TELEMETRY=0` and `DO_NOT_TRACK=1`.
- **Multi-Python gotcha:** on machines with several Pythons (Homebrew vs
  python.org vs system), the `needle` CLI lives in the interpreter's bin dir
  that `pip install`ed it. If `import needle` fails under `python3`, find the
  right interpreter (`ls */bin/needle`, `pip show cactus-needle`) — or see
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
- `tests/` — unit tests (stdlib `unittest`) for the exporter: import-safety failures
  raise a clear SystemExit, and the full menu export round-trips through the real
  `@needle.tool` decorator when cactus-needle is installed. Run:
  `python -m unittest discover -s skills/neuralos-skill/tests`.


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
