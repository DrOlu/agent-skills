---
name: rmagent-ao
description: >
  The Agent Observatory — find and trace every AI agent, agent harness and
  model server on a box, with zero install, from outside. The agent-plane
  sibling of rmagent-so. A four-probe census (process, network, filesystem,
  packages) discovers all agents including shadow ones the SDK vendors cannot
  see; per-agent questions pull config, models, recent activity from their own
  disk artifacts; local model servers (Ollama, LM Studio, vLLM) are queried
  through their own APIs. Works over SSH (Linux/macOS) and WinRM (Windows).
  Use when you need to know what agents are running on an estate, what they
  are calling, what changed, or to trace one agent's activity — the
  OpenLLMetry question answered by asking the box instead of embedding an SDK.
  Pull-based, capped, holes instead of dumps. Not a lake.
---

# rmagent-ao — The Agent Observatory

Find and trace every agent on a box, with zero install, from outside.

**The OpenLLMetry question — what did this LLM call do? — answered by asking
the box instead of embedding an SDK.** SDK-based tracing only sees apps that
opted in. This sees everything, including the shadow Ollama someone installed
last week and the script with a hardcoded key.

The agent-plane sibling of `rmagent-so`. Same constitution: pull-only,
allowlisted questions, capped answers, holes instead of dumps.

## Why agents are unusually observable from outside

A normal web app is a black box at the process boundary. An agent practically
announces itself:

- It calls a **small set of known endpoints** — api.anthropic.com,
  api.openai.com, openrouter, localhost:11434. Network attribution is trivial.
- It **spawns tools as child processes** — the process tree is the tool-call log.
- It **writes transcripts to disk** — Claude Code, OpenCode, Aider, Continue,
  Goose all persist sessions locally. The data is already there; reading it is
  a pull, not an instrument.
- It uses **env vars for keys** — presence of ANTHROPIC_API_KEY is a cheap,
  secret-safe signature.
- **Local model servers expose HTTP APIs** — Ollama /api/tags + /api/ps,
  LM Studio /v1/models, vLLM /v1/models. Already allowlisted-question-shaped.

## The questions

| Question | Returns | Must NOT return |
|---|---|---|
| `agents` | The census — all agent processes, harnesses, frameworks, model servers, endpoints, config paths, packages | secret values, full transcripts |
| `agentstate` | One agent's config, models, MCP servers, skills, env-var NAMES (never values), version | API keys, tokens |
| `agenttrace` | Recent activity from disk artifacts — sessions, tool calls, files touched, commands run, capped | full transcript dumps |
| `agentnet` | Endpoint attribution — which LLM APIs, at what rate/volume, per agent PID | packet captures |
| `agentmodels` | Local model servers queried directly — what's installed, what's running | model weights |
| `agentdrift` | Baseline + diff — new agents, new endpoints, new models, transcript anomalies | — |
| `agentdeep` | ETW burst on one PID (Windows) — 10s of syscall-level tracing, time-boxed, nothing persists | a persistent agent |

## The coverage tiers (stated honestly)

| Tier | Agents | Depth |
|---|---|---|
| **1 — Rich** | CLI agents with disk transcripts (Claude Code, OpenCode, Aider, Continue, Goose, RTerm) | full sessions, tool calls, commands |
| **2 — Good** | local model servers (Ollama, LM Studio, vLLM, llama.cpp) | models, running state, metrics via their APIs |
| **3 — Boundary** | any process calling a known LLM endpoint — LangChain/AutoGen/CrewAI apps, custom agents | process, endpoints, volume, children, files |
| **4 — Opaque** | no disk artifacts, unknown/proxied endpoints, no API | existence only — recorded as a HOLE, honestly |

**The genuine trade vs OpenLLMetry:** breadth + zero-install vs inside-depth.
Token counts, prompt text and tool arguments are only available when the agent
writes them to disk (Tier 1) or exposes an API (Tier 2). We get ~80% via
artifacts + boundary + local APIs, and the census finds 100% of what exists.

## The scripts

| Script | Role |
|---|---|
| `scripts/lib.py` | The engine — door-aware `ask()`: `door=ssh` → bash payloads over SSH, `door=winrm` → PowerShell payloads over pywinrm. Allowlisted, 32 KB cap, holes. |
| `scripts/questions/linux/*.sh` | Bash payloads for SSH witnesses (Linux/macOS) |
| `scripts/questions/windows/*.ps1` | PowerShell payloads for WinRM witnesses |
| `scripts/stc.py` | Security Trace Context — carries `agent=` alongside `principal=` |
| `scripts/hop_index.py` | Cross-case memory, keyed on (host, agent, session) |
| `scripts/otel_emit.py` | Optional OTel export — same opt-in as the Flight Recorder |

## Inventory

Same shape as the estate. Add the agent skills to a witness's list:

```yaml
witnesses:
  - id: mac
    door: ssh
    address: localhost
    user: olu
    skills: [agents, agenttrace, agentnet, agentmodels]
    track: [root]
  - id: ws1
    door: winrm
    address: 44.197.31.152
    skills: [agents, agentstate, agentnet, agentdrift]
    track: [Administrator, SYSTEM]
```

## Laya-assisted agent triage

Every discovered agent (or shadow agent) the census surfaces can be scored by a
fast, typed decision model (Laya, via the `use-laya` skill) before it reaches the
operator. One matrix lives in `decisions/`:

- `agent_triage.json` — per census row: is this a shadow or unmanaged agent?
  How risky is its configuration? Pull its per-agent questions, flag it, or
  record it?

```bash
scripts/laya_decide.py agent_triage --state-file agent.json
```

Policy: confidence below 0.5 is flagged ESCALATE — those rows go to the LLM or
the operator. Verdicts are advisory; the census itself and its capped pulls are
unchanged. The matrix is an allowlist — edit it deliberately, in the light.

## Needle tier 0 — offline extraction and drift

Alongside the Laya matrices, every skill in this family can call
**needle** — a 121M on-device model (Cactus Compute Needle, ~35 MB, no
network, no keys, ~100 MB RAM) installed once on the jump host, never on
the witnesses. It is the free tier of the judgment stack: needle extracts
and compares offline, Laya judges, the LLM reasons.

Two scripts ship in `scripts/`:

- `needle_extract.py` — typed field extraction from a witness fragment
  (`count`, `source_ip`, …). Rigid tokens (numbers, IPs) are reliable;
  semantic fields are not, so the wrapper validates what it can (`:ip`,
  `:int`) and blanks anything it cannot trust — never a guess.
  ```bash
  echo "<attest answer>" | scripts/needle_extract.py user count:int source_ip:ip --json
  ```
- `needle_drift.py` — baseline-drift detection via needle's 3072-dim
  embeddings: record what an answer normally looks like, score today's
  answer against it (similar / drifted / changed, thresholds calibrated
  empirically). Separates shape and topic, not field values — value drift
  stays the job of the field rules and correlate joins.
  ```bash
  echo "<routine answer>" | scripts/needle_drift.py record <host>-<question>
  echo "<today's answer>" | scripts/needle_drift.py score <host>-<question>
  ```

The engine runs in-process on the jump host (the wrapper finds a Python
with `cactus-needle` — set `NEEDLE_PYTHON` if it lives elsewhere). No port
is opened, nothing is installed on any witness, and the baselines are
kilobyte holes under `~/.rmagent/needle-drift/`, not a lake. On an
air-gapped estate this tier keeps working — and the judgment tier with it: Laya is offline too (pre-seed its HF-cache checkpoint on air-gapped hosts), so no matrix judgment waits for a connected session.

## Non-negotiables

- **Watch only.** No actuation. Never kill an agent process from here.
- **Secret values are never read.** Env var NAMES only, for the key-presence
  signal. No transcript content beyond capped excerpts.
- **Capped answers** (32 KB). Oversized pulls become holes.
- **Your estate only.**
- **A hole is an answer.** Tier 4 agents are recorded as holes, not guessed at.
- **WinRM payloads stay under the ~8191-char UTF-16LE budget** (same as so).
- **Never trust “no agents”** until `agents` census ran; unknown binary + unknown egress is Tier 4 (blind), not empty.

## Relationship to the other skills

| Skill | Plane |
|---|---|
| `rmagent-so` | The Security Observatory — identity-led witness questions |
| `rmagent-fr` | The Flight Recorder — ticket-led tracing |
| `rmagent-ao` | **This skill — the Agent Observatory, agent-led** |
| `rmagent-windows` | The complete Windows skill (so + fr) |
| `rmagent-redteam` | The drill |
| `rmagent-actuate` | Phase 1 response |
| `rmagent-linux` | The Linux/macOS sibling of rmagent-so |

## Honest limits

1. No inside-view of uninstrumented custom agents (Tier 3/4) — boundary only
2. macOS has no eBPF — process/files/network work; deep syscall tracing doesn't
3. Windows deep tier is an ETW burst, time-boxed, nothing persistent
4. The census is signature-based — a truly novel agent with an unknown endpoint
   and no disk artifacts is Tier 4 and shows up as a hole, which is the honest
   answer, not a false "no agents found"