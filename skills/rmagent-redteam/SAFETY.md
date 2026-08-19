# SAFETY — read before you stage

This drill writes real artifacts to real Windows servers. The guardrails below are non-negotiable.

## It is a drill, not an attack

- Every artifact is prefixed `RMAgentDrill_` (`RMAgentDrill_Test` user, `RMAgentDrill_Task` task, `RMAgentDrillSvc` service).
- Payloads are benign: `Test-NetConnection 1.1.1.1:80` and `echo ... > C:\Windows\Temp\rmagent_drill.txt`.
- No exfiltration. No persistence beyond the drill. No destructive action.
- `clean.ps1` removes every `RMAgentDrill_*` artifact and is **idempotent** — run it freely.

## Authorised estate only

- Targets must be in `estate.yaml` — WS1/WS2 or boxes the operator **administers**.
- Never run against a partner box, NIBSS, a production-critical system, or anything outside your authority without explicit written consent.
- `--confirm` is required for `stage` and `run`. No silent staging.

## Reversibility

- `clean` mode removes everything. Default `run` cleans automatically after scoring.
- `--keep` leaves artifacts for inspection — clean afterwards with `redteam.py clean`.
- Never leave `RMAgentDrill_*` artifacts on a box you've handed back.

## Telegram

- Sends detection **summaries** only — counts, signal names, case name.
- Never sends credentials, Event Log contents, or full case data.
- If `telegram-bot-token` / `telegram-chat-id` are absent, the run proceeds without alerts (it prints to stdout instead). It does not fail.

## Don't surprise your SOC

- Defender/CrowdStrike will likely alert on a new LocalSystem service + SYSTEM task. Coordinate timing if your SOC is staffed, or run off-hours.
- The drill's "failed Administrator logon" events are real 4625s. Your SIEM will see them.
