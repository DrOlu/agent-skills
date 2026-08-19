# explain.ps1 — what changed THIS WINDOW for Administrator/SYSTEM, in this floor's words.
# Time-boxed, capped. Never a full ring/tenant export. Engine caps to 32 KB downstream.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
# Compact form keeps the base64-encoded WinRM command under the ~8191-char cmdline cap.
#
# REV 2 (2026-08-19) — lateral-movement + persistence additions:
#   4648/4672 added to the identity-changes section (explicit creds, special privs)
#   5861 WMI event subscriptions — the classic fileless persistence mechanism
#        (ATT&CK T1546.003). Log: Microsoft-Windows-WMI-Activity/Operational.
#        Fields follow the 5860 layout: Namespace, NotificationQuery, UserName.
function MT($e){ foreach($v in $e.Properties.Value){ if($Track -contains $v){return $true} }; return $false }
function E($ids,$log){
  try{ @(Get-WinEvent -FilterHashtable @{LogName=$log;Id=$ids;StartTime=$since} |
        Select-Object -First $Limit |
        ForEach-Object{ [pscustomobject]@{ t=$_.TimeCreated.ToString('o'); id=$_.Id; m=($_.Message -split "`n")[0] } }) }
  catch{ @() }
}
$since = (Get-Date).AddHours(-$SinceHours)

# identity/group changes: admin add/remove, user create/enable/pwd-reset/change,
# PLUS 4648 (explicit credentials — lateral movement) and 4672 (special privileges)
$idch  = E @(4720,4722,4724,4732,4733,4738,4648,4672) 'Security'
# service installs + state changes (privileged surface)
$svc   = E @(7045,7036) 'System'
# scheduled task create + update
$tsk   = E @(4698,4702) 'Security'
# WMI event subscriptions (fileless persistence — T1546.003)
$wmi   = E @(5861) 'Microsoft-Windows-WMI-Activity/Operational'
# process spawns by Administrator/SYSTEM (4688): 4688 field idx 1=SubjectUserName, 5=NewProcessName
$psp = @()
try{ $psp = @(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4688;StartTime=$since} |
              Where-Object{ MT $_ } | Select-Object -First $Limit |
              ForEach-Object{ [pscustomobject]@{ t=$_.TimeCreated.ToString('o'); u=$_.Properties[1].Value; p=$_.Properties[5].Value } }) }catch{}

[pscustomobject]@{
  skill           = 'explain'
  host            = $env:COMPUTERNAME
  utc             = [DateTime]::UtcNow.ToString('o')
  since           = $since.ToString('o')
  window_hours    = $SinceHours
  track           = $Track
  identity_changes= @($idch)
  service_events  = @($svc)
  task_events     = @($tsk)
  wmi_subscriptions = @($wmi)
  proc_spawns     = @($psp)
} | ConvertTo-Json -Compress -Depth 4
