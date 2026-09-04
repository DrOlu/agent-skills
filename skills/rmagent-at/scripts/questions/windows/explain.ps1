# explain.ps1 — what changed THIS WINDOW for Administrator/SYSTEM. Capped. No lake.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
# REV 3: 4688 split into all-spawns + LOLBin spawns w/ CommandLine; +1102 audit-cleared
# and +4699 task-deleted anti-forensics tripwires; 5861 WMI subs (T1546.003) kept.
function MT($e){ foreach($v in $e.Properties.Value){ if($Track -contains $v){return $true} }; return $false }
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
function E($ids,$log){
  try{ @(Get-WinEvent -FilterHashtable @{LogName=$log;Id=$ids;StartTime=$since} -MaxEvents $Max|Select-Object -First $Limit|
        ForEach-Object{ $msg=($_.Message -split "`n")[0]; if($msg.Length -gt 80){$msg=$msg.Substring(0,80)}; [pscustomobject]@{ t=$_.TimeCreated.ToString('o'); id=$_.Id; m=$msg } }) }
  catch{ @() }
}
$since=(Get-Date).AddHours(-$SinceHours)
$Max=[int]$Limit*20
$idch=E @(4720,4722,4724,4732,4733,4738,4648,4672) 'Security'
$svc =E @(7045,7036) 'System'
$tsk =E @(4698,4702,4699) 'Security'
$wmi =E @(5861) 'Microsoft-Windows-WMI-Activity/Operational'
$clr =E @(1102) 'Security'
$idch=@($idch|Select-Object -First 20);$svc=@($svc|Select-Object -First 15);$tsk=@($tsk|Select-Object -First 15)
$psp=@()
try{ $psp=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4688;StartTime=$since} -MaxEvents $Max|Where-Object{MT $_}|Select-Object -First 20|ForEach-Object{ [pscustomobject]@{t=$_.TimeCreated.ToString('o');u=$_.Properties[1].Value;p=$_.Properties[5].Value} }) }catch{}
$LOL='powershell|pwsh|cmd\.exe|wscript|cscript|mshta|rundll32|regsvr32|certutil|bitsadmin|msiexec|schtasks|wmic|net\.exe|net1|psexec|wsmprovhost|curl|tar|atbroker|bash|cmstp|diskshadow|dnscmd|forfiles|gpscript|hh|ieexec|infdefaultinstall|installutil|mavinject|msbuild|msdt|netsh|odbcconf|pcalua|pcwrun|presentationhost|rasautou|regasm|regsvcs|runonce|runscripthelper|scriptrunner|tttracer|verclsid|wab|xwizard|appvlp|bginfo|cdb|csi|devtoolslauncher|dnx|dotnet|dxcap|mftrace|msdeploy|msxsl|rcsi|sqlps|squirrel|vsjitdebugger|wsl'
$lol=@()
try{ $lol=@(Get-WinEvent -FilterHashtable @{LogName='Security';Id=4688;StartTime=$since} -MaxEvents $Max|Where-Object{MT $_ -and $_.Properties[5].Value -match $LOL}|Select-Object -First 20|ForEach-Object{ $cl=(F $_ 'CommandLine'); if($cl -and $cl.Length -gt 200){$cl=$cl.Substring(0,200)}; [pscustomobject]@{t=$_.TimeCreated.ToString('o');u=$_.Properties[1].Value;p=$_.Properties[5].Value;c=$cl} }) }catch{}
[pscustomobject]@{skill='explain';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o');window_hours=$SinceHours;track=$Track;identity_changes=@($idch);service_events=@($svc);task_events=@($tsk);wmi_subscriptions=@($wmi);audit_cleared=@($clr);proc_spawns=@($psp);lolbin_spawns=@($lol)}|ConvertTo-Json -Compress -Depth 4
