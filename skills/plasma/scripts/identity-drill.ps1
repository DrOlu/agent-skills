<#
.SYNOPSIS
  Plasma detection drill: trip the tap (base64 + DNS rules), pull WHIDS,
  push the drill domain as an IOC, restart WHIDS, re-drill for an alert.
  Benign and reversible — everything is prefixed plasma-drill / example.top.

.PARAMETER PlasmaExe
  Path to the plasma exe on the node.

.EXAMPLE
  .\identity-drill.ps1 -PlasmaExe C:\ProgramData\PlasmaSetup\plasma-0.11.1-windows-x64.exe
#>
param(
    [Parameter(Mandatory)] [string] $PlasmaExe,
    [string] $Events = 'C:\ProgramData\Plasma\data\events.jsonl',
    [string] $WhidsRoot = 'C:\Program Files\Whids'
)

$ErrorActionPreference = 'Continue'
$domain = 'plasma-drill.example.top'

# 1. tap window (60s) with auto-collect
$p = Start-Process -FilePath $PlasmaExe -ArgumentList `
    'tap','run','--providers','powershell,wmi,dns','--for','60s',
    '--out-dir','C:\ProgramData\Plasma\tap','--events',$Events `
    -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 10

# 2. trip the PowerShell base64 rule (4104 scriptblock)
powershell -NoProfile -Command '$d=[Convert]::FromBase64String(''aGVsbG8gcGxhc21h''); [Text.Encoding]::UTF8.GetString($d)'

# 3. trip the DNS rule
Resolve-DnsName -Name $domain -Type A -ErrorAction SilentlyContinue | Out-Null

Wait-Process -Id $p.Id -Timeout 120 -ErrorAction SilentlyContinue
"tap_exit=$($p.ExitCode)"

# 4. collect + pull + push the domain into WHIDS
& $PlasmaExe whids pull --root $WhidsRoot --out $Events | Select-String '"written"|"alerts"'
& $PlasmaExe whids push --root $WhidsRoot --events $Events --min-confidence 3 `
    --apply --reason 'plasma drill' | Select-String '"ok"|"indicators"|"error"'

# 5. restart WHIDS to load the rule, re-drill for the alert
Restart-Service Whids -ErrorAction SilentlyContinue
Start-Sleep -Seconds 20
Resolve-DnsName -Name $domain -Type A -ErrorAction SilentlyContinue | Out-Null
Start-Sleep -Seconds 15

& $PlasmaExe whids pull --root $WhidsRoot --out $Events | Select-String '"written"|"alerts"'
"whids_svc=$((Get-Service Whids -ErrorAction SilentlyContinue).Status)"
"alert_files=$((Get-ChildItem "$WhidsRoot\Logs\Alerts" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count)"
"store_rows=$((Get-Content $Events | Measure-Object -Line).Lines)"

# 6. what the brain sees
& $PlasmaExe ask --prompt "critical alerts" --events $Events
