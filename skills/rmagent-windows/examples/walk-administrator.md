# Walk — Administrator/SYSTEM across WS1 and WS2

> This is Hunter, serial, depth-capped. You walk the tracked principals
> (Administrator, SYSTEM) across both boxes, write hops + holes to a one-page
> case, and hand off any app/work id to reliability. No `Security.evtx` leaves
> the boxes. No `actuate`.

## Preconditions

- Lab A passed: attest works on both boxes, a silent box becomes a hole.
- `estate.yaml` lists WS1 (plane: endpoint) and WS2 (plane: data), `track: [Administrator, SYSTEM]`.
- Credentials in env (`RMAgent_WS1_PASS`, `RMAgent_WS2_PASS`).
- EDR still on, drawing.

## 1. Open a case

```bash
export SKILL_DIR=~/.claude/skills/rmagent-windows
CASE=$(python3 "$SKILL_DIR/scripts/case.py" open --title "admin walk 2026-08-19" \
         --principal Administrator --slug admin-walk-0819)
echo "$CASE"   # ./cases/admin-walk-0819
```

## 2. Walk — edges then explain, box by box

```bash
python3 "$SKILL_DIR/scripts/hunt.py" \
  --inventory ./estate.yaml --since 2h --case-dir "$CASE"
```

Hunter is serial. For each box it asks `edges` (who did Administrator/SYSTEM
touch since 2 h ago), and only opens `explain` (what changed) where `edges`
returned smoke. Output is something like:

```
[hunt] tracking ['Administrator', 'SYSTEM'] across 2 witnesses, since 2h
  ws1   edges: 3 tracked logons, 2 outbound conns
  ws1   explain: groups=0 svc=1 tasks=0 procs=14
  ws2   edges: 1 tracked logons, 0 outbound conns
  ws2   explain: groups=0 svc=0 tasks=0 procs=5

[case] ./cases/admin-walk-0819/CASE.md  (4 hops)
```

A silent box would appear as:

```
  ws2   edges: HOLE — unreachable: <err>  (one ask, no retry)
```

## 3. Read the one-page case

```bash
cat "$CASE/CASE.md"
```

```
# admin walk 2026-08-19

Track: ['Administrator', 'SYSTEM']
Window: 2h

## Hops
- 01 ws1 · edges → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'edges', 'logons': 3, 'conns': 2, ...}
- 02 ws1 · explain → {'plane': 'endpoint', 'witness': 'ws1', 'skill': 'explain', 'group_changes': 0, ...}
- 03 ws2 · edges → {...}
- 04 ws2 · explain → {...}

## Holes
(none — every door answered)
```

The case folder holds:

```
cases/admin-walk-0819/
  case.json      # meta: title, principal, opened, phase=0, actuate=false
  CASE.md        # the readable one-pager above
  path.json      # the hop list (the security trace)
  holes.jsonl    # one line per silent/stripped/empty door
  asks.jsonl     # every door-opening (a stolen jump host is itself a case)
```

## 4. What to look at (the reading)

- **`edges.logons`** — recent Administrator/SYSTEM logons with **source IP and
  LogonId**. A source IP you do not expect (a city, a jump host that should not
  be there) is the smoke. The LogonId is the join across hosts — same id on WS1
  and WS2 = same session walked.
- **`edges.conns`** — outbound connections owned by Administrator/SYSTEM
  processes. A first-time destination is a hop to follow.
- **`explain.group_changes` (4732)** — someone added to the local Administrators
  group. This is the "spare key under the mat" from the Ada story.
- **`explain.service_events` (7045)** — a new service running as LocalSystem.
  A classic living-off-the-land foothold.
- **`explain.proc_spawns` (4688)** — what Administrator/SYSTEM ran in the window.
  Look for `powershell.exe`, `net.exe`, `wmic.exe`, `nltest.exe` — tools an
  attacker uses to walk the next room.

## 5. Hand off (optional)

If a hop is an application / API call with a work id (the Ada `PAY-4419`),
hand that id to the `flight-recorder` skill (`pathfinder.py`). Security asks
"who walked?"; reliability asks "why was this slow?" — same id, two walks.

## 6. Close

```bash
python3 "$SKILL_DIR/scripts/case.py" close "$CASE"
```

## Success / failure

- **Success** — you can say the walk in one breath: "Administrator signed into
  WS1 from `<src>`, ran X, then reached WS2; one new local admin on WS2." Two
  boxes, four hops, kilobytes. `Security.evtx` still on the boxes. EDR drawing.
- **Failure** — you exported `Security.evtx`, invented a hop where a box was
  silent, pooled Hunter, or called `actuate`.

## Refuses to honour (the guardrails, baked into `lib.py`)

- `ask(row, "actuate")` → refused.
- `ask(row, "dump")` → `skill not allowlisted`.
- An answer over 32 KB → clipped to a hole, not stored.
- A box you do not administer → not on the map. Write the hole, do not invent a
  witness.
