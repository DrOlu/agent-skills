# RMAgent Red-Team — quick start

Purple-team drill for `rmagent-windows`. Stages reversible LOTL artifacts on WS1/WS2, runs rmagent to score detection, Telegrams you the report, then cleans up.

## 1. Prerequisites

```bash
pip3 install pywinrm pyyaml
# rmagent-windows skill must work first (census passes on WS1/WS2)
# Telegram: telegram-bot-token + telegram-chat-id already in the secrets scrt store
# Windows creds: env RMAgent_WS1_PASS / RMAgent_WS2_PASS, or auto-loaded from scrt
```

## 2. Run the full drill

```bash
export SKILL_DIR=~/.claude/skills/rmagent-redteam
cp ~/.claude/skills/rmagent-windows/assets/inventory.example.yaml ./estate.yaml

python3 "$SKILL_DIR/scripts/redteam.py" run --inventory ./estate.yaml --confirm
```

You get a Telegram message with `Detected (N/6)` and each rmagent signal that fired.

## 3. Step by step

```bash
python3 redteam.py stage --inventory ./estate.yaml --confirm   # stage artifacts only
python3 redteam.py clean --inventory ./estate.yaml             # remove all RMAgentDrill_* artifacts
python3 redteam.py run    --inventory ./estate.yaml --confirm --keep  # run but don't clean
```

## The 6 staged signals

| Artifact | Event | rmagent signal |
|---|---|---|
| failed admin logons | 4625 | attest.admin_failed_60s |
| new local admin | 4720+4732 | explain.identity_changes |
| new SYSTEM task | 4698 | explain.task_events |
| new LocalSystem service | 7045 | explain.service_events |
| powershell spawns | 4688 | explain.proc_spawns (needs auditing on) |
| SYSTEM outbound conn | — | edges.conns / attest.system_remote_conns |

See `SKILL.md` for the full design and `SAFETY.md` for guardrails.
