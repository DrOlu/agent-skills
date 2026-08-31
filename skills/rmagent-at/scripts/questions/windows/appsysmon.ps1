# appsysmon — Sysmon security telemetry, read from the log that is already
# running on the box. Read-only, capped. Emits ONE JSON object.
#
# WHY THIS EXISTS (distinct from the ETW ring sessions):
#   ProcTrace/NetTrace capture process + connection EVENTS from the kernel.
#   Sysmon adds the SECURITY CONTEXT the kernel providers do not emit:
#     Event 1  — image hashes (SHA256) + ProcessGuid: "did this binary ever
#                run here?" answerable without the file still being present
#     Event 3  — connections keyed by ProcessGuid, not PID (PIDs are reused)
#     Event 7  — image/DLL loads (injection, LOLBin abuse)
#     Event 10 — LSASS access (credential dumping)
#     Event 13 — registry value sets (persistence)
#
# If Sysmon is not installed, this reports sysmon='not-installed' and empty
# lists — a hole, not an error. The skill does not install anything.
#
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$log='Microsoft-Windows-Sysmon/Operational'

$svc=Get-Service Sysmon64,Sysmon -EA SilentlyContinue|Select -First 1
$sysmon=if($svc){"$($svc.Name)=$($svc.Status)"}else{'not-installed'}

$hashes=@(); $lsass=@(); $imgloads=@(); $regsets=@(); $guidconns=@()
$n=0
try{
  if($svc){
    # Event 1 — process create with hashes (the "was this binary ever here" answer)
    Get-WinEvent -FilterHashtable @{LogName=$log;Id=1;StartTime=$cutoff} -EA SilentlyContinue|
    Select -First $Limit|%{
      $x=[xml]$_.ToXml();$d=@{}
      foreach($i in $x.Event.EventData.Data){$d[$i.Name]=$i.'#text'}
      $hashes+=[pscustomobject]@{t=$_.TimeCreated.ToString('o');img=$d['Image'];
        sha256=($d['Hashes']+'') -replace '(?i).*SHA256=([0-9A-Fa-f]+).*','$1';guid=$d['ProcessGuid']}
    }
    # Event 10 — LSASS access (credential dumping)
    Get-WinEvent -FilterHashtable @{LogName=$log;Id=10;StartTime=$cutoff} -EA SilentlyContinue|
    Select -First $Limit|%{
      $x=[xml]$_.ToXml();$d=@{}
      foreach($i in $x.Event.EventData.Data){$d[$i.Name]=$i.'#text'}
      $lsass+=[pscustomobject]@{t=$_.TimeCreated.ToString('o');src=$d['SourceImage'];
        tgt=$d['TargetImage'];granted=$d['GrantedAccess']}
    }
    # Event 7 — image loads (DLL injection / LOLBin)
    Get-WinEvent -FilterHashtable @{LogName=$log;Id=7;StartTime=$cutoff} -EA SilentlyContinue|
    Select -First $Limit|%{
      $x=[xml]$_.ToXml();$d=@{}
      foreach($i in $x.Event.EventData.Data){$d[$i.Name]=$i.'#text'}
      $imgloads+=[pscustomobject]@{t=$_.TimeCreated.ToString('o');img=$d['ImageLoaded'];
        proc=$d['Image']}
    }
    # Event 13 — registry value set (persistence)
    Get-WinEvent -FilterHashtable @{LogName=$log;Id=13;StartTime=$cutoff} -EA SilentlyContinue|
    Select -First $Limit|%{
      $x=[xml]$_.ToXml();$d=@{}
      foreach($i in $x.Event.EventData.Data){$d[$i.Name]=$i.'#text'}
      $regsets+=[pscustomobject]@{t=$_.TimeCreated.ToString('o');tgt=$d['TargetObject'];
        proc=$d['Image']}
    }
    # Event 3 — network connections keyed by ProcessGuid (not reused PIDs)
    Get-WinEvent -FilterHashtable @{LogName=$log;Id=3;StartTime=$cutoff} -EA SilentlyContinue|
    Select -First $Limit|%{
      $x=[xml]$_.ToXml();$d=@{}
      foreach($i in $x.Event.EventData.Data){$d[$i.Name]=$i.'#text'}
      $guidconns+=[pscustomobject]@{t=$_.TimeCreated.ToString('o');guid=$d['ProcessGuid'];
        img=$d['Image'];dst=$d['DestinationIp'];dport=$d['DestinationPort']}
    }
    $n=@($hashes).Count+@($lsass).Count+@($imgloads).Count+@($regsets).Count+@($guidconns).Count
  }
}catch{}
[pscustomobject]@{skill='appsysmon';host=$hn;utc=$now;window_h=$sh;sysmon=$sysmon;n_events=$n;
  proc_hashes=@($hashes);lsass_access=@($lsass);image_loads=@($imgloads);
  registry_sets=@($regsets);guid_conns=@($guidconns)}|ConvertTo-Json -Compress -Depth 4