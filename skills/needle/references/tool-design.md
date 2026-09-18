# Tool design for Needle

The model is 121M parameters. It beats models 10× its size on mobile tool
calls **when the tools are designed for it** — the grammar does the heavy
lifting, not the model's world knowledge. Every rule below came from a live
failure mode.

## Table of contents

1. One tool per action, named as users say it
2. Triggers are mandatory
3. Constrain everything you can
4. Secrets never ride in arguments
5. Keep results small — digest + stash
6. Compound asks: two max
7. Wrapping OS CLIs as tools (subprocess pattern)
8. Grounding — what the model may put in an argument

## 1. One tool per action, named as users say it

- Split "manage the database" into `list_databases`, `describe_schema`,
  `top_customers`. If a user could ask for it in one sentence, it is one tool.
- The function name and docstring first line should read like the request:
  `chinook_top_customers` — "List the top-spending Chinook customers by
  revenue."
- Document parameters in an `Args:` section; the schema carries those
  descriptions to the model.
- Don't overload with optional flags that change the action. Two focused
  tools select more reliably than one polymorphic one.

## 2. Triggers are mandatory

```python
@needle.tool(triggers=["revenue by country", "revenue breakdown",
                       "by country", "sales by country"])
```

Without triggers, selection is flaky: the model intermittently refuses a
perfectly matching tool — observed reasoning: "No connectivity or network
tools available", confidence 0.98 — or drifts as the auto-injected date fact
changes between runs. Triggers pin the request vocabulary to the tool.
Include the noun phrases a user would actually type, including casual ones.

Keep trigger sets disjoint between tools: "revenue" alone on two tools will
steer the model wrong; "total revenue" vs "revenue by employee" will not.

## 3. Constrain everything you can

The decode grammar enforces constraints, so an invalid value cannot be
emitted at all — this is the reliable way to control a small model:

```python
from typing import Annotated, Literal

def query_range(unit: Literal["hour", "day", "week"],
                count: Annotated[int, needle.Field(ge=1, le=52)] = 1) -> dict:
```

Use `enum`/`Literal` for closed vocabularies, `pattern` for identifier-ish
strings (`^[A-Za-z0-9_$]+$` for a database name), `ge/le` for numeric ranges,
`format="date"` for dates. Leave truly free text (a search phrase)
unconstrained — that is what the model is good at.

## 4. Secrets never ride in arguments

Observed live: a tool taking `password: str` gets **refused** by strict
grounding — the result comes back `{"error": "ungrounded password"}` and the
model may then flail. This is a feature, not a bug: an LLM should not carry
credentials it cannot verify. Bake them as constants next to the tool:

```python
DB_PASSWORD = "..."          # module constant, env var, or keychain

@needle.tool(triggers=["list databases"])
def list_databases() -> dict:      # no credential arguments
    ...
```

The model's job is choosing *what* to do, not reciting keys. The same logic
applies to hosts, ports and usernames when they are fixed infrastructure:
bake them, and keep as arguments only what varies per request.

## 5. Keep results small — digest + stash

`run()` feeds your tool's return value verbatim back into the model's prompt.
A multi-kilobyte result (a full schema dump, a 100-row table) overloads the
121M context: the model loses the thread and repeats unrelated calls until
`max_steps`. Observed with a 4 KB schema: six redundant `SHOW DATABASES`
executions in one run.

Pattern — digest to the model, stash for the caller:

```python
_SCHEMA_DETAILS = {}   # full payload for the calling script

@needle.tool(triggers=["schema", "table structure"])
def describe_schema(database: str) -> dict:
    tables = {}  # ... run the query, build full {table: [columns]}
    _SCHEMA_DETAILS[database] = tables
    # model sees only the shape of the answer:
    return {"database": database, "table_count": len(tables),
            "tables": list(tables)}
```

Rule of thumb: keep the returned JSON under ~1–2 KB. Rows, long strings and
nested detail go to the stash; counts, names and summaries go to the model.

## 6. Compound asks: two max

"Get me total revenue, then best performing employees" → two calls, both
correct, in order. Adding "and then top 10 customers" to the same sentence →
the third call is silently dropped. Ask for two things per turn at most;
drive the third with a follow-up turn (`agent.run(...)` again — create a
fresh `Needle` or `reset()` between unrelated questions). In `--prompt` /
CLI mode, one query is one selection pass — issue separate calls per intent.

## 7. Wrapping OS CLIs as tools (subprocess pattern)

Tools are ordinary Python — wrap any local CLI. The pattern that worked for
`mysql` generalises to `kubectl`, `git`, `dig`, anything:

```python
import os, subprocess

@needle.tool(triggers=["list databases"])
def list_databases() -> dict:
    proc = subprocess.run(
        ["mysql", "--host", HOST, "--port", str(PORT),
         "--batch", "--skip-column-names", "--execute", "SHOW DATABASES;"],
        capture_output=True, text=True,           # parse TSV output
        encoding="utf-8", errors="replace",       # never crash on odd bytes
        timeout=30,
        env=dict(os.environ, MYSQL_PWD=PASSWORD), # secret via env, not argv
    )
    if proc.returncode != 0:
        return {"error": proc.stderr.strip()}     # agent loop sees the failure
    rows = [l.strip() for l in proc.stdout.splitlines() if l.strip()]
    return {"databases": rows}
```

Why each piece is there:

- **Secrets via env** (`MYSQL_PWD`, `PGPASSWORD`, …) keep them out of `ps`
  and out of the model's arguments (§4).
- **`--batch`/`--skip-column-names`** (or the CLI's machine-readable flag)
  gives parseable output instead of screen tables.
- **`encoding="utf-8", errors="replace"`** — subprocess `text=True` decodes
  with the locale and raises on invalid bytes; always set both.
- **Interpolate nothing unvalidated.** If a model-filled argument reaches a
  command line or SQL, constrain it (§3: `pattern` for identifiers) and
  re-validate inside the tool before use.
- **Return `{"error": ...}` instead of raising** — `run()` catches
  exceptions too, but a structured error lets the model read the failure and
  try a corrected call on the next turn.
- Some CLIs need flags to behave (mysql: `--protocol=TCP` so `-P` applies
  with `-h localhost`; `--default-character-set=utf8mb4` for unicode). Read
  the wrapped CLI's docs, not just the happy path.

## 8. Grounding — what the model may put in an argument

- Numeric values must be written in the request text. `port=3306` is fine
  when the user said "port 3306"; it is flagged `ungrounded` when the model
  invented it. Give such arguments defaults or write the numbers into the
  prompt.
- Dates must not contradict years present in the input; relative phrasing
  ("tomorrow") is licensed against the system date.
- Engine-flagged fabricated values and negated requests become
  `{"error": "ungrounded ..."}` results instead of executing.
- With nothing to call, the model returns an empty `function_calls` list
  rather than a guess — surface that as "no tool covers this", and either
  add a tool or change the request.

## 9. Many tools?

Up to roughly a handful of tools, pass them all. Beyond that, build a tool
index — the engine binary's `--tool-index` and the Python API's
`tool_index_path` embed the tool set once and retrieve the relevant subset
per request. Selection accuracy on 6 tools with disjoint triggers was
flawless in testing; do not assume the same at 60 without an index.
