# appnet — connection-level network. Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
#
# REV 18 (H2 + honest source selection): the answer prefers the NetTrace ETW
# ring (Kernel-Network EID 10/16, structured payload), and FALLS BACK to
# Sysmon Event 3 when the ring is empty. Found live on WS1 (2026-09-04): the
# kernel-network AutoLogger records nothing on Server 2022 (a documented
# kernel-trace-flag limitation — the provider config is verified correct:
# Level 255, all keywords, session Running/Circular) while Sysmon EID 3 is
# already capturing every connection with process attribution on this estate.
# The fallback is the same pull, same box, better source. If BOTH are empty
# the answer says so honestly (sources: []).
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$cutoff=(Get-Date).AddHours(-[double]$SinceHours)
$conns=@(); $n=0; $pf=0; $source='none'
try{
  # ---- 1. the NetTrace ring (preferred: kernel-level, includes non-Sysmon)
  $etl=(Get-ChildItem "C:\etw\RMAgent-NetTrace*.etl" -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select -First 1).FullName
  if($etl -and (Test-Path $etl)){
    $evs=Get-WinEvent -Path $etl -Oldest -MaxEvents ($Limit*10) -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}|Select -First ($Limit*3)
    $n=@($evs).Count
    $seen=@{}
    foreach($e in $evs){
      if($e.Id -eq 0 -or -not $e.Properties.Count){ continue }  # empty preallocation events
      $p=@($e.Properties|ForEach-Object{$_.Value})
      $src=''; $dst=''
      if($p.Count -ge 6){
        $src="{0}:{1}" -f $p[4],$p[5]
        $dst="{0}:{1}" -f $p[2],$p[3]
      }
      if(-not $src){
        $m=''
        try{$m=($_.FormatDescription()+'')}catch{}
        if($m -match '(?i)(\d+\.\d+\.\d+\.\d+):(\d+)\s*->\s*(\d+\.\d+\.\d+\.\d+):(\d+)'){
          $src="$($Matches[1]):$($Matches[2])"; $dst="$($Matches[3]):$($Matches[4])"
        }
      }
      if(-not $src){$pf++; continue}
      $key="$src>$dst"
      if(-not $seen.ContainsKey($key)){
        $seen[$key]=1
        $conns+=[pscustomobject]@{t=$e.TimeCreated.ToString('o');src=$src;dst=$dst;
          pid=if($p.Count){$p[0]}else{$null}}
      }
    }
    if(@($conns).Count){ $source='nettrace-ring' }
  }
  # ---- 2. fallback: Sysmon EID 3 (running on this estate; has process names)
  if(-not @($conns).Count){
    $log='Microsoft-Windows-Sysmon/Operational'
    $evs=Get-WinEvent -FilterHashtable @{LogName=$log;Id=3;StartTime=$cutoff} -MaxEvents ($Limit*3) -EA SilentlyContinue
    if($evs){
      $source='sysmon'
      foreach($e in @($evs)|Select -First $Limit){
        $x=[xml]$e.ToXml();$d=@{}
        foreach($i in $x.Event.EventData.Data){$d[$i.Name]=[string]$i.'#text'}
        if($d['DestinationIp']){
          $conns+=[pscustomobject]@{t=$e.TimeCreated.ToString('o');
            src='-';dst="{0}:{1}" -f $d['DestinationIp'],$d['DestinationPort'];
            pid=$d['ProcessId'];proc=$d['Image'];guid=$d['ProcessGuid']}
        }
      }
    }
  }
}catch{}
[pscustomobject]@{skill='appnet';host=$hn;utc=$now;window_h=$SinceHours;n_events=$n;parse_failures=$pf;
  source=$source;n_conns=@($conns).Count;conns=@($conns)}|ConvertTo-Json -Compress -Depth 4
