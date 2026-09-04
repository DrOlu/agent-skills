# appslow — the slow-request question. Finds requests/operations over a
# threshold in the AppTrace ring, slowest-first. Read-only, capped.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
# REV 18 (H2): durations come from the structured payload where they exist
# (HTTP.sys conn/req events carry elapsed fields), with the message regex as
# a FALLBACK for manifest-registered providers — not the only path. Every
# answer carries parse_failures so "N events, 0 parsed" is a hole.
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=$SinceHours; $cutoff=(Get-Date).AddHours(-[double]$sh)
# bincirc names the file <name>_000001.etl — glob for the current segment
$etl=(Get-ChildItem "C:\etw\RMAgent-AppTrace*.etl" -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select -First 1).FullName
$slow=@(); $n=0; $pf=0
try{
  if(Test-Path $etl){
    $evs=Get-WinEvent -Path $etl -Oldest -MaxEvents ($Limit*10) -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}
    $n=@($evs).Count
    foreach($e in $evs){
      $ms=0; $desc=''
      # 1) structured: any numeric property in a plausible ms range on a
      #    duration-carrying EID (HTTP.sys 45/46/47 request-conn events)
      $p=@($e.Properties|ForEach-Object{$_.Value})
      if($e.Id -in @(45,46,47) -and $p.Count){
        foreach($v in $p){ if($v -is [int64] -or $v -is [int32]){ $iv=[int]$v; if($iv -ge 500 -and $iv -le 3600000){ $ms=$iv; break } } }
      }
      # 2) fallback: duration-like text in a manifest-rendered message
      if(-not $ms){
        $m=''
        try{$m=($e.FormatDescription()+'')}catch{}
        if($m -match '(?i)(duration|elapsed|time taken|milliseconds|ms)\D*(\d{3,})'){
          $ms=[int]$Matches[2]
        }
      }
      if($ms -ge 500){
        if(-not $desc){ try{$desc=($e.FormatDescription()+'')}catch{} }
        if(-not $desc -and $p.Count){$desc=($p|Select -First 3) -join ' | '}
        if(-not $desc){$pf++}
        $slow+=[pscustomobject]@{
          t=$e.TimeCreated.ToString('o')
          provider=$e.ProviderId
          id=$e.Id
          ms=$ms
          msg=($desc+'').Substring(0,[Math]::Min($MsgCap,($desc+'').Length))
        }
      }
    }
    $slow=@($slow|Sort-Object ms -Descending|select -First $Limit)
  }
}catch{}
[pscustomobject]@{skill='appslow';host=$hn;utc=$now;window_h=$sh;n_scanned=$n;parse_failures=$pf;n_slow=@($slow).Count;slowest=@($slow)}|ConvertTo-Json -Compress -Depth 4
