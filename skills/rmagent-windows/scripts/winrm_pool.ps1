<#
  Optional all-pwsh path. Use ONLY when every inventory door is winrm and you
  prefer PowerShell Invoke-Command over pywinrm. Reads credentials from env
  (RMAgent_<ID>_USER / RMAgent_<ID>_PASS), never from the inventory file.

  Max 3 runspaces — the walk budget, not the host count. attest only in Phase 0.

  pwsh -NoProfile -File scripts/winrm_pool.ps1 -Skill attest `
       -ComputerName '44.197.31.152','52.3.242.251' -Ids ws1,ws2 -MaxRunspaces 3
#>
[CmdletBinding()] param(
  [ValidateSet('attest','sketch','edges','explain')][string]$Skill = 'attest',
  [Parameter(Mandatory)][string[]]$ComputerName,
  [Parameter(Mandatory)][string[]]$Ids,
  [int]$MaxRunspaces = 3,
  [double]$SinceHours = 2,
  [int]$Limit = 50,
  [int]$TimeoutSec = 25
)
$ErrorActionPreference = 'SilentlyContinue'
$skillDir = Split-Path -Parent $PSScriptRoot
$payload  = Get-Content -Raw (Join-Path $skillDir "questions\windows\$Skill.ps1")
$preamble = "`$ErrorActionPreference='SilentlyContinue'; `$Track=@('Administrator','SYSTEM'); `$SinceHours=$SinceHours; `$Limit=$Limit"

$pool = [runspacefactory]::CreateRunspacePool(1, [Math]::Max(1,$MaxRunspaces))
$pool.Open()
$jobs = @()
for ($i = 0; $i -lt $ComputerName.Count; $i++) {
  $id = $Ids[$i]; $cn = $ComputerName[$i]
  $envUser = [Environment]::GetEnvironmentVariable("RMAgent_$($id.ToUpper())_USER")
  $envPass = [Environment]::GetEnvironmentVariable("RMAgent_$($id.ToUpper())_PASS")
  if (-not $envPass) { Write-Warning "$id : no RMAgent_$($id.ToUpper())_PASS env var — skip"; continue }
  $ps = [PowerShell]::Create().AddScript({
    param($cn,$user,$pass,$preamble,$body,$timeout)
    $secure = ConvertTo-SecureString -AsPlainText -Force $pass
    $cred = New-Object System.Management.Automation.PSCredential($user,$secure)
    $opts = New-PSSessionOption -OperationTimeout ($timeout*1000) -SkipCACheck -SkipCNCheck -OpenTimeout $timeout000
    Invoke-Command -ComputerName $cn -Credential $cred -Authentication Basic -SessionOption $opts -ScriptBlock ([scriptblock]::Create(($preamble + "`n" + $body)))
  }).AddArgument($cn).AddArgument($envUser).AddArgument($envPass).AddArgument($preamble).AddArgument($payload).AddArgument($TimeoutSec)
  $ps.RunspacePool = $pool
  $jobs += [pscustomobject]@{ Id = $id; PS = $ps; Handle = $ps.BeginInvoke() }
}

foreach ($j in $jobs) {
  try {
    $out = $j.PS.EndInvoke($j.Handle)
    if ($out) { $out | ForEach-Object { Write-Output "[$($j.Id)] $_" } }
    else      { Write-Output "[$($j.Id)] (no output — hole)" }
  } catch {
    Write-Output "[$($j.Id)] HOLE: $($_.Exception.Message)"
  } finally {
    $j.PS.Dispose()
  }
}
$pool.Close(); $pool.Dispose()
