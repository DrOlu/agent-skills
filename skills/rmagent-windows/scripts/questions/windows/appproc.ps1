# appproc — process/thread activity from the ProcTrace ring. Read-only, capped.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
# REV 18 (H2+HONEST LIMIT): parse the STRUCTURED payload by PROPERTY NAME (the
# XML carries names even when Message is null). SHAPE FOUND LIVE on WS1
# (2026-09-04): the Kernel-Process AutoLogger ring carries thread-start (EID 3:
# ProcessID/ThreadID/StackBase/Win32StartAddr...) and thread-stop events — NOT
# process-start-with-commandline, and NO image paths. Those live in Sysmon
# Event 1, which appsysmon reads. Stated plainly: use appsysmon for "what
# binary with what cmdline"; use appproc for ring-level thread/process volume.
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$cutoff=(Get-Date).AddHours(-[double]$SinceHours)
$etl=(Get-ChildItem "C:\etw\RMAgent-ProcTrace*.etl" -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select -First 1).FullName
$procs=@(); $n=0; $pf=0
try{
  if($etl -and (Test-Path $etl)){
    $evs=Get-WinEvent -Path $etl -Oldest -MaxEvents ($Limit*10) -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}|Select -First ($Limit*2)
    $n=@($evs).Count
    foreach($e in $evs){
      $d=@{}
      try{$x=[xml]$e.ToXml();foreach($i in $x.Event.EventData.Data){$d[$i.Name]=[string]$i.'#text'}}catch{}
      $pid2=$d['ProcessID']; $tid=$d['ThreadID']
      if(-not $d.Count){$pf++; continue}
      $op = 'thread-start'
      if($d.ContainsKey('Win32StartAddr')){
        $op = 'thread-start'
      } elseif($d.ContainsKey('ExitCode')){
        $op = 'thread-stop'
      } elseif($d.ContainsKey('ImageFileName') -or $d.ContainsKey('ImageName')){
        $op = 'process'
      }
      $procs+=[pscustomobject]@{
        t=$e.TimeCreated.ToString('o'); id=$e.Id; op=$op
        pid=$pid2; tid=$tid
        start_addr=$d['Win32StartAddr']
        img=$d['ImageFileName']
      }
    }
    $procs=@($procs|Select -First $Limit)
  } elseif(-not $etl){ $pf++ }
}catch{}
[pscustomobject]@{skill='appproc';host=$hn;utc=$now;window_h=$SinceHours;n_events=$n;parse_failures=$pf;n_procs=@($procs).Count;procs=@($procs)}|ConvertTo-Json -Compress -Depth 4
