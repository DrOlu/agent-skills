# apperrors — the error/warning question. Errors, exceptions, failed requests
# from the AppTrace ring. Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
# REV 18 (H2): Level is structured (never null) so this question was the one
# that always worked — but its msg text came from a null-prone Message. Now
# uses FormatDescription with a Properties fallback and carries parse_failures.
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=$SinceHours; $cutoff=(Get-Date).AddHours(-[double]$sh)
# bincirc names the file <name>_000001.etl — glob for the current segment
$etl=(Get-ChildItem "C:\etw\RMAgent-AppTrace*.etl" -EA SilentlyContinue | Sort-Object LastWriteTime -Descending | Select -First 1).FullName
$errs=@(); $n=0; $nerr=0; $nwarn=0; $pf=0
try{
  if(Test-Path $etl){
    $evs=Get-WinEvent -Path $etl -Oldest -MaxEvents ($Limit*10) -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}
    $n=@($evs).Count
    foreach($e in $evs){
      # Level: 2=Error, 3=Warning, 4=Information, 5=Verbose
      if($e.Level -eq 2){$nerr++}
      elseif($e.Level -eq 3){$nwarn++}
      if($e.Level -le 3){
        $m=''
        try{$m=($e.FormatDescription()+'')}catch{}
        if(-not $m){
          $p=@($e.Properties|ForEach-Object{$_.Value})
          if($p.Count){$m=($p|Select -First 3) -join ' | '}else{$pf++}
        }
        $errs+=[pscustomobject]@{
          t=$e.TimeCreated.ToString('o')
          provider=$e.ProviderId
          id=$e.Id
          level=$e.Level
          msg=($m+'').Substring(0,[Math]::Min($MsgCap,($m+'').Length))
        }
      }
    }
    $errs=@($errs|select -First $Limit)
  }
}catch{}
[pscustomobject]@{skill='apperrors';host=$hn;utc=$now;window_h=$sh;n_scanned=$n;parse_failures=$pf;n_errors=$nerr;n_warnings=$nwarn;recent=@($errs)}|ConvertTo-Json -Compress -Depth 4
