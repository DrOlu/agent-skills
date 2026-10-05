# ringhealth — AutoLogger sessions Running? Circular? FROZEN-at-cap? oldest write?
# MOP created the sessions; this question is Phase 0 (read-only).
#
# REV 19 (freeze detection, live-verified on WS2 2026-10-04):
#   A bincirc session that fills its segment FROZE IN PLACE instead of wrapping
#   (file mtime stuck, logman still reports Running — a zombie; ProcTrace died
#   outright). 'Running' alone is therefore NOT proof of live capture. This
#   payload now also reports:
#     - the REAL segment file (glob <name>_*.etl, newest) — the old 'File Name:'
#       grep returned the base path (no segment suffix), so bytes was always 0;
#     - cap_mb from 'Segment Max Size:' and frozen=true when bytes >= 98% cap;
#     - stale=true when the newest segment's mtime is >30 min old (idle OR
#       frozen — a warning, not a verdict);
#     - buffers_lost from logman.
#   frozen-at-cap counts toward blind_count: a zombie ring is witness_blind.
$now=[DateTime]::UtcNow
$names=@('RMAgent-AppTrace','RMAgent-NetTrace','RMAgent-ProcTrace')
$rows=@()
$blind=0; $frozenCount=0
foreach($n in $names){
  $st='missing'; $circ='unknown'; $bytes=0; $running=$false
  $file=''; $capMb=0; $frozen=$false; $frozenReason=''; $stale=$false; $ageMin=$null; $lost=$null; $written=$null
  try{
    $q = logman query $n 2>$null | Out-String -Width 400
    if($q -match 'Running'){ $st='Running'; $running=$true }
    elseif($q -match 'Stopped'){ $st='Stopped' }
    if($q -match 'Circular'){ $circ='On' }
    if($q -match '(?i)Segment Max Size:\s+(\d+)\s*MB'){ $capMb=[int]$Matches[1] }
    elseif($q -match '(?i)Maximum Size:\s+(\d+)\s*MB'){ $capMb=[int]$Matches[1] }
    if($q -match '(?i)Buffers Lost:\s+(\d+)'){ $lost=[int]$Matches[1] }
    if($q -match '(?i)Buffers Written:\s+(\d+)'){ $written=[int]$Matches[1] }
    # REAL segment file: logman reports the base path ('File Name:' or
    # 'Output Location:'); bincirc writes <base>_NNNNNN.etl segments.
    $base=''
    if($q -match '(?i)(?:File Name|Output Location):\s+(\S+)'){ $base=$Matches[1] }
    $dir=Split-Path $base -Parent; $leaf=[IO.Path]::GetFileNameWithoutExtension($base)
    $segs=@()
    if($dir -and $leaf){ $segs=@(Get-ChildItem (Join-Path $dir ($leaf+'_*.etl')) -EA SilentlyContinue | Sort-Object LastWriteTime -Descending) }
    if($segs.Count -gt 0){
      $newest=$segs[0]; $file=$newest.FullName; $bytes=$newest.Length
      $ageMin=[math]::Round((New-TimeSpan -Start $newest.LastWriteTime.ToUniversalTime() -End $now).TotalMinutes,1)
      if($ageMin -gt 30){ $stale=$true }
    } elseif($base -and (Test-Path $base)){
      $file=$base; $bytes=(Get-Item $base).Length
      $ageMin=[math]::Round((New-TimeSpan -Start (Get-Item $base).LastWriteTime.ToUniversalTime() -End $now).TotalMinutes,1)
      if($ageMin -gt 30){ $stale=$true }
    }
    # freeze verdict: Running + segment at >=98% of cap = the live-verified
    # bincirc freeze (file stops accepting, session keeps saying Running).
    if($running -and $file -and $capMb -gt 0 -and $bytes -ge ($capMb*1MB*0.98)){
      $frozen=$true; $frozenReason='at-cap: bincirc segment filled and froze (WS2 2026-10-04); logman still reports Running'
    }
  }catch{ $st='error' }
  if(-not $running){ $blind++ }
  elseif($frozen){ $blind++; $frozenCount++ }
  $rows += [pscustomobject]@{session=$n; status=$st; circular=$circ; bytes=$bytes
    file=$file; cap_mb=$capMb; mtime_age_min=$ageMin; stale=$stale
    frozen=$frozen; frozen_reason=$frozenReason; buffers_lost=$lost; buffers_written=$written}
}
[pscustomobject]@{
  skill='ringhealth'; host=$env:COMPUTERNAME; utc=$now.ToString('o')
  sessions=$rows; blind_count=$blind; frozen_count=$frozenCount
  blind_check=$(if($blind -eq 0){'ok'}else{'BLIND'})
  note='Stopped OR frozen-at-cap AutoLogger is witness_blind for the app plane - not a quiet box. stale mtime alone means idle OR frozen: disambiguate with a pull.'
}|ConvertTo-Json -Compress -Depth 5
