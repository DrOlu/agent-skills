# kernring — process + network events from the BUILT-IN kernel analytic channels.
# The NO-SYSMON FALLBACK: attackers delete Sysmon (Stop-Service Sysmon64) to blind
# the primary ring. These channels are built into Windows with no service to stop.
# FIDELITY GAP vs netedges: no process name on net events (PID only), no command
# lines, no hashes, and the ring is SHORT (minutes, not days). Degraded mode, not
# a replacement. Prerequisite (setup D3): wevtutil sl .../Analytic /e:true on both.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
function F($e,$n){$x=[xml]$e.ToXml();$m=New-Object System.Xml.XmlNamespaceManager($x.NameTable);$m.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event');$o=$x.SelectSingleNode("//e:Data[@Name='$n']",$m);if($o){$o.'#text'}}
$since=(Get-Date).AddHours(-$SinceHours)
$procs=@()
try{$procs=@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Kernel-Process/Analytic';StartTime=$since} -ErrorAction SilentlyContinue|Select-Object -First $Limit|Where-Object{$_.Id -in @(1,2,3)}|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');eid=$_.Id;pid=(F $_ 'ProcessID');img=(F $_ 'ImageName');ppid=(F $_ 'ParentProcessID');cmd=(F $_ 'CommandLine')}
})}catch{}
$nets=@()
try{$nets=@(Get-WinEvent -FilterHashtable @{LogName='Microsoft-Windows-Kernel-Network/Analytic';StartTime=$since} -ErrorAction SilentlyContinue|Select-Object -First $Limit|ForEach-Object{
 [pscustomobject]@{t=$_.TimeCreated.ToString('o');eid=$_.Id;pid=(F $_ 'PID');dest=(F $_ 'daddr');port=(F $_ 'dport')}
})}catch{}
$sysmon='unknown'
try{$svc=Get-Service Sysmon64,Sysmon -ErrorAction SilentlyContinue|Select-Object -First 1; if($svc){$sysmon="$($svc.Name)=$($svc.Status)"}else{$sysmon='not-installed'}}catch{}
[pscustomobject]@{skill='kernring';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');since=$since.ToString('o');track=$Track;sysmon_status=$sysmon;procs=@($procs);nets=@($nets)}|ConvertTo-Json -Compress -Depth 4
