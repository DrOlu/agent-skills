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

## Non-negotiables

- **Watch only.** No actuation. Never kill an agent process from here.
- **Secret values are never read.** Env var NAMES only, for the key-presence
  signal. No transcript content beyond capped excerpts.
- **Capped answers** (32 KB). Oversized pulls become holes.
- **Your estate only.**
- **A hole is an answer.** Tier 4 agents are recorded as holes, not guessed at.

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