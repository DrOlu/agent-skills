---
name: extend-rmagent-so
description: >
  Automatically extend the rmagent-so neuralOS estate instance by reading
  menu_gaps.jsonl (the fuzzy-guess gate log), classifying each gap,
  applying Type A trigger fixes (script), building Type B probes (bridge +
  menu, over rmagent state that already exists), re-exporting
  needle_menu.json, verifying selection + truth, and restarting the
  observatory app on :8892. Run on-demand ("extend the rmagent menu") or
  after soaks. WATCH-ONLY: new probes must never wrap actuate or anything
  outside engine.ALLOWED.
---

# extend-rmagent-so — Auto-extend the Security Observatory menu

The self-improvement loop for instance #10. The deterministic half
(`gap_extend.py`) runs hourly via launchd and handles Type A trigger
additions automatically. This skill is the JUDGMENT half: review what the
script did, build Type B probes, verify, and ship — without weakening a
single rmagent rule.

## When to use

- After gated questions accumulate in `menu_gaps.jsonl`
- When asked: "extend the rmagent menu", "process the observatory gaps",
  "extend rmagent-so"
- After a soak or demo reveals phrasings the menu can't anchor

## Paths

```
INSTANCE_DIR  = ~/neuralos-instances/rmagent-so
INSTANCE_PY   = $INSTANCE_DIR/instance.py
BRIDGE_PY     = $INSTANCE_DIR/bridge.py
MENU_JSON     = $INSTANCE_DIR/needle_menu.json
GAP_LOG       = $INSTANCE_DIR/menu_gaps.jsonl
TYPE_B_LOG    = $INSTANCE_DIR/menu_gaps_type_b.jsonl
STATE         = ~/.rmagent/            (cases/, silent.json, canary_state.json,
                                        needle-drift/, actuate-journal.jsonl)
ESTATE        = /Users/olu/estate.yaml (override: RMAgent_ESTATE env)
ENGINE        = ~/.agents/skills/rmagent-so/scripts  (lib.py; engine via
               ~/.agents/skills/rmagent-core/scripts/loader.py)
EXPORT        = ~/.claude/skills/chinook-app-blueprint/scripts/export_menu.py
VERIFY_TRUTH  = ~/.claude/skills/chinook-app-blueprint/scripts/verify_truth.py
VERIFY_SELECT = ~/.claude/skills/chinook-app-blueprint/scripts/verify_selection.py
GAP_EXTEND    = ~/.claude/skills/chinook-app-blueprint/scripts/gap_extend.py
PYTHON        = /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
SERVICE       = ng.neuralos.rmagentso  (port 8892, launchd KeepAlive)
```

## The constitution (read first — nothing below overrides it)

1. **WATCH ONLY.** No probe may wrap actuate, systemctl, usermod, firewall
   edits — or anything outside `engine.ALLOWED` (19 named questions). The
   bridge refuses non-allowlisted asks before a packet is sent; keep it so.
2. **Credentials** come from env / `~/.rmagent/creds.json` / the scrt
   store — never baked into bridge.py, never in the inventory, never in
   this skill.
3. **Capped answers, errors as data, holes are answers.** A new probe
   returns `{"error": ...}` rather than guessing; ROW_CAP holds.
4. **Prefer FAST over LIVE.** A new probe should expose data that ALREADY
   exists in `~/.rmagent` state (case answers, silent ledger, canary
   state, drift baselines) before it proposes a live door pull. Live
   probes are slow and knock on real boxes.

## The algorithm

### Step 1 — Read the gap log

`cat $GAP_LOG` — JSON lines with `question`, `guessed_tool`,
`confidence`. Dedupe by question (keep newest). Empty → report and stop.
Also check `$TYPE_B_LOG` for anything queued by earlier runs.

### Step 2 — Run the deterministic classifier (or review its output)

```bash
$PYTHON $GAP_EXTEND --instance-dir $INSTANCE_DIR --dry-run
```

- **Type C** (pre-routed families, <3 words, no guess, false gaps) → skip.
- **Type A** (≥2 content-word overlap with the guessed probe's triggers) →
  the hourly learner usually already applied these; verify idempotence.
  The trigger content-word ledger lives in the instance.py docstring —
  keep it accurate when you add triggers.
- **Type B** → the real work. Apply with `--restart` after verification:

```bash
$PYTHON $GAP_EXTEND --instance-dir $INSTANCE_DIR \
    --restart "launchctl kickstart -k gui/$(id -u)/$SERVICE"
```

### Step 3 — Design the Type B probe (the judgment call)

Study `bridge.py` first. Every probe follows the house shape: reads state
through the helpers (`_answers()`, `_silent()`, `_correlation()`,
`_drift_keys()`, `_witness()`, `_j()`), returns `_meta(rows, extras)` or
`_err(message)`, caps at ROW_CAP, rides validation counters.

Before writing anything, ask in order:

1. **Does the data already exist in state?** Check
   `~/.rmagent/cases/answers/*.json` keys (witness__skill), CASE.md,
   correlation.json findings, silent.json, canary_state.json,
   needle-drift baselines. Most good probes are views over these.
2. **Is it a comparison or aggregate of existing probes?** Follow
   `so_compare_health` (double live attest + verdicts).
3. **Only then** consider a new live pull — and prefer reusing
   `bridge.so_ask_live` / `so_attest_live` instead of new transport code.

Precedents to copy:
- `so_logons` — a view over cached edges answers + greedy-grounding
  recovery (multi-word witness args degrade to estate-wide)
- `so_changes` — boot-time comparison + needle-drift scoring via the
  `needle_drift.py` CLI (subprocess, score key with the answer JSON on
  stdin)
- `so_compare_health` — double `so_attest_live` + verdicts

### Step 4 — Probe hygiene (non-negotiable)

- Triggers: 3–8 lowercase phrases, token-disjoint against the LEDGER in
  instance.py's docstring. Update the ledger.
- NEVER-docstring: positive statement + explicit rivals ("NEVER for the
  question log (that is ask_log)").
- Arguments: prefer `str` with bridge-side validation over giant Literal
  enums — a 19-member Literal exceeded the engine's call token budget
  ("tool call truncated"). Enums ≤ 8.
- Grounding recovery: strip/handle greedy args (whole sentences stuffed
  into a parameter — degrade to estate-wide like `so_logons`; swap
  obviously exchanged args like `so_ask_live`).
- High-confidence wrong probes are the #1 threat: a 0.98 fuzzy guess
  passes the gate. If the soak shows a family being stolen by the
  so_witness_detail magnet, give the family its own probe — that is the
  cure, not more gate tuning.
- Record-ask quirk: `engine.record_ask` writes the answer file EVEN ON A
  HOLE — never let a battery/hole flow overwrite a good cached answer
  (battery.py already guards this; keep the guard).

### Step 5 — Export, verify, restart

```bash
$PYTHON $EXPORT $INSTANCE_DIR
$PYTHON $VERIFY_TRUTH  --instance-dir $INSTANCE_DIR --cases $INSTANCE_DIR/truth_cases.jsonl
$PYTHON $VERIFY_SELECT --instance-dir $INSTANCE_DIR --cases $INSTANCE_DIR/selection_cases.jsonl
```

- Add at least one truth case per new probe (stable paths only) and one
  selection case per trigger family (canonical + adversarial).
- LIVE probes: selection tests are route-only (no network). Smoke a real
  ask once, manually — a silent host must return a hole, not an error page.
- Restart and verify:

```bash
launchctl kickstart -k gui/$(id -u)/$SERVICE && sleep 12
curl -s localhost:8892/menu          # probe count must match the export
```

### Step 6 — Archive + report

```bash
mv $GAP_LOG $GAP_LOG.$(date +%Y%m%dT%H%M%S).done
mv $TYPE_B_LOG $TYPE_B_LOG.$(date +%Y%m%dT%H%M%S).done   # if non-empty
```

Report: gaps in / Type A applied / Type B built (name + one-line purpose)
/ verification numbers / new probe count / anything left gated as
by-design (out-of-domain fuel stays in the log on purpose).

## Domain facts (current menu = 15 probes)

- Estate: ws1 (endpoint) + ws2 (data), PSRP doors, canaries
  `honeyadmin`/`svcbackup2`, tracked `Administrator`/`SYSTEM`
- Two tiers: FAST (overview, witnesses, detail, findings, ask log, logons,
  holes, canaries, drift, attackmap, allowlist, changes) and LIVE
  (ask_live, attest_live, compare_health)
- Known holes: attackmap (pypsrp stream_error — rmagent-core fix needed)
  and deepwindow (ETW payload empty post-boot); a fresh boot + 2 h window
  legitimately shows 0 tracked logons
- Known gaps handled: kerberoasting/DC questions → so_allowlist (krb is
  DC-only, not advertised); "flying blind" → so_holes; "lateral movement"
  → so_findings; "how about ws2" → so_witness_detail trigger (Type A,
  applied autonomously by the learner)

## Example run

```
$ extend-rmagent-so

menu_gaps.jsonl: 3 unique gaps
  A: "show me the boxes"      -> so_witnesses  (applied by learner already — verified)
  B: "show open ports"        -> no state source; edges.conns only has tracked
                                 outbound — queued as Type B, needs a hunt first
  C: "hello"                  -> skip
Built: none this run (Type B queued)
TRUTH 25/25 · SELECTION 17/17 · menu 15 probes · service restarted
```

## Safety rules (the short list)

- Never remove triggers; never modify existing bridge functions — add.
- Never touch CONF_GATE, the gate's two-signal rule, or `_trigger_hit`.
- Never add a probe outside the watch-only constitution.
- Never put credentials in bridge.py, instance.py, or this skill.
- Test state-reading code against the LIVE `~/.rmagent` state before
  shipping — the shapes drift (Rev 17–21).
- Archive everything; the `*.done` files are the loop's audit trail.
