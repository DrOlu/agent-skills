# Recipes - durable neuralosd workflows on Restate

All recipes assume the service from `scripts/restate_neuralosd_service.py`
is registered (deployment `:9090`) and the instance door is at `NEURALOSD_URL`.

## 1. Single durable ask

```bash
curl -X POST localhost:8080/WemaAsk/ask -d '"how many open incidents"'
```

Retry-safe: if the machine dies mid-call, Restate re-invokes `ask` and the
journal prevents double side effects (asks are read-only anyway).

## 2. Nightly report (cron + email/chat delivery)

```bash
# crontab: 05:00 daily
0 5 * * * curl -s -X POST localhost:8080/WemaTriage/nightly_report \
          | mail -s "Wema BMC daily" ops@example.com
```

The handler journals the overview fetch; the report text is derived from
journaled data, so a crashed run resumes without re-querying BMC twice.

## 3. Date-range asks (after the incidents_in_last_days probe)

```bash
curl -X POST localhost:8080/WemaAsk/ask \
     -d '"how many incidents were submitted in the last 30 days"'
```

The caged integer arg maps to the probe's `days` parameter - the code gate
extracts and clamps it.

## 4. Approval-gated workflow (awakeables)

Sketch - pause until a human resolves a key:

```python
@triage.handler()
async def approved_restart(ctx, plan: str):
    ticket = await ctx.run("create_ticket", lambda: open_change_ticket(plan))
    key = f"approve-{ticket['id']}"
    await ctx.awakeable(key)  # durable pause - survives restarts
    # ... human POSTS the awakeable id resolution ... workflow resumes here
    return await ctx.run("apply", lambda: apply_plan(plan))
```

The awakeable id is returned to the approver (email/chat); resolution via
the Restate API resumes the handler exactly where it paused.

## 5. Multi-instance

One Restate service per instance, or one service with a caged instance
selector:

```python
@service.handler()
async def ask_any(ctx, instance: str, question: str):
    url = DOORS[instance]  # map instance name -> HTTP door
    return await ctx.run(f"ask:{instance}", lambda: ask_at(url, question))
```

## 6. Constrained model picks inside handlers (optional)

Pair with the `neuralos-ollama` skill: when the lexical floor is unsure,
run the constrained qwen3.5:9b pick inside `ctx.run` (Ollama format,
`think:false`, `none_of_these` -> logged refusal). The pick is journaled;
an Ollama restart mid-run replays it instead of re-asking the model.

## 7. Testing patterns

- Trap questions: assert `none_of_these` / refusal, never an answer
- Truth checks: compare handler output to a direct bridge/oracle count
- Kill test: stop the handler server mid-triage, restart it - the run must
  resume and complete (watch the journal in the UI)
