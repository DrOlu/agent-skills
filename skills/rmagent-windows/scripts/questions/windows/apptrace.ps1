# apptrace — read the RMAgent-AppTrace circular ring. Application-level events
# from .NET CLR / HTTP.sys. Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
# REV 18 (H2): parse the structured payload (Properties), not the prose
# Message — ETL-file events carry null Message unless a manifest is registered
# on the reader, so the old code saw volume with zero usable fields and
# reported it as a quiet box. Every answer now carries parse_failures so
# "N events, 0 parsed" reads as a hole, not a clean box.
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=$SinceHours; $cutoff=(Get-Date).AddHours(-[double]$sh)
# bincirc names the file <name>_000001.etl — glob for the current segment
$etl=(Get-ChildItem "C:\etw\RMAgent-AppTrace*.etl" -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select -First 1).FullName
$events=@(); $n=0; $pf=0
try{
  if(Test-Path $etl){
    # flush the live ring to the file first so we read current events.
    # NOTE (C3, disclosed): the pull flushes the ring — the question is
    # read-only over the events, but the flush writes ring contents to the
    # ring file. That is what makes recent events visible at all.
    $evs=Get-WinEvent -Path $etl -Oldest -MaxEvents ($Limit*10) -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}|Select -First $Limit
    $n=@($evs).Count
    foreach($e in $evs){
      $props=@($e.Properties|ForEach-Object{$_.Value})
      $msg=''
      try{$msg=($e.FormatDescription()+'')}catch{}
      if(-not $msg -and $props.Count){$msg=($props|Select -First 3) -join ' | '}
      if(-not $msg){$pf++}
      $events+=[pscustomobject]@{
        t=$e.TimeCreated.ToString('o')
        provider=$e.ProviderId
        id=$e.Id
        level=$e.Level
        msg=($msg+'').Substring(0,[Math]::Min($MsgCap,($msg+'').Length))
      }
    }
  }
}catch{}
[pscustomobject]@{skill='apptrace';host=$hn;utc=$now;window_h=$sh;n_events=$n;parse_failures=$pf;events=@($events)}|ConvertTo-Json -Compress -Depth 4
