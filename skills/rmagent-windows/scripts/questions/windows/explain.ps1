# explain.ps1 — what changed THIS WINDOW for Administrator/SYSTEM, in this floor's words.
# Time-boxed, capped. Never a full ring/tenant export. Engine caps to 32 KB downstream.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
# Compact form keeps the base64-encoded WinRM command under the ~8191-char cmdline cap.
function MT($e){ foreach($v in $e.Properties.Value){ if($Track -contains $v){return $true} }; return $false }
function E($ids,$log){
  try{ @(Get-WinEvent -FilterHashtable @{LogName=$log;Id=$ids;StartTime=$since} |
        Select-Object -First $Limit |
        ForEach-Object{ [pscustomobject]@{ t=$_.TimeCreated.ToString('o'); id=$_.Id; m=($_.Message -split "`n")[0] } }) }
  catch{ @() }
}
$since = (Get-Date).AddHours(-$SinceHours)

# identity/group changes: admin add/remove, user create/enable/pwd-reset/change
$idch  = E @(4720,4722,4724,4732,4733,4738) 'Security'
# service installs + state changes (privileged surface)
$svc   = E @(7045,7036) 'System'
# scheduled task create + update
$tsk   = E @(4698,4702) 'Security'
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
  proc_spawns     = @($psp)
} | ConvertTo-Json -Compress -Depth 4
