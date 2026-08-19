# RMAgent for Windows — quick start

Pull-based witness habit for a two-box Windows estate (WS1 `44.197.31.152`, WS2 `52.3.242.251`), tracking **Administrator** and **SYSTEM**. Four allowlisted questions over WinRM. No log lake. Keep the EDR.

## 1. Install

The jump host runs on **macOS, Linux, or Windows** — `pywinrm` connects to the Windows targets from any of them. PowerShell 7 (`pwsh`) is only needed for the optional `winrm_pool.ps1` RunspacePool path.

```bash
pip3 install pywinrm pyyaml
export SKILL_DIR=~/.claude/skills/rmagent-windows
# non-macOS jump host: provide the scrt master password via env or file
#   export SCRT_PASS=...      OR   echo '...' > ~/.scrt_pass  (chmod 600)
```

## 2. Open WinRM on each Windows box (once)

RDP in, admin PowerShell. NTLM (default) works on AWS Windows with no extra config:

```powershell
Enable-PSRemoting -Force
Set-Service WinRM -StartupType Automatic; Start-Service WinRM
New-NetFirewallRule -Name WinRM-5985-JumpHost -Direction Inbound -Protocol TCP -LocalPort 5985 -Action Allow
```

Only if you set `transport: basic` in the inventory, also run:

```powershell
Set-Item WSMan:\localhost\Service\Auth\Basic -Value $true
Set-Item WSMan:\localhost\Service\AllowUnencrypted -Value $true
```

## 3. Credentials (env)

```bash
export RMAgent_WS1_USER=Administrator
export RMAgent_WS1_PASS='...'
export RMAgent_WS2_USER=Administrator
export RMAgent_WS2_PASS='...'
```

## 4. Inventory

```bash
cp "$SKILL_DIR/assets/inventory.example.yaml" ./estate.yaml
```

## 5. Knock (Census)

```bash
python3 "$SKILL_DIR/scripts/census.py" --inventory ./estate.yaml
```

You should see something like:

```
[census 2026-08-19T...] 2 witnesses
  ok   ws1      alive=True admin_fail_60s=0 admin_ok_5m=0 local_admins=2 sys_conns=4
  ok   ws2      alive=True admin_fail_60s=0 admin_ok_5m=0 local_admins=2 sys_conns=1
```

## 6. Walk Administrator/SYSTEM (Hunter)

```bash
CASE=$(python3 "$SKILL_DIR/scripts/case.py" open --title "admin walk" --principal Administrator)
python3 "$SKILL_DIR/scripts/hunt.py" --inventory ./estate.yaml --since 2h --case-dir "$CASE"
cat "$CASE/CASE.md"
```

## What you CANNOT do

- No `actuate` (isolate/disable/revoke) — `ask()` refuses it. Watch is not actuate.
- No copying `Security.evtx` or full log dumps. Answers are capped at 32 KB.
- No tight-retrying a silent host. Write the hole. Two misses = Critical.
- No boxes you don't administer. NIBSS / a partner / a phone = hole, not a witness.

See `SKILL.md` for the full design, `SAFETY.md` for guardrails, and `examples/` for a live lab and a full walk.
