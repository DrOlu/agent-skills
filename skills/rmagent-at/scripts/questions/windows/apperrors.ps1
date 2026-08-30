# apperrors — the error/warning question. Errors, exceptions, failed requests
# from the AppTrace ring. Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$etl="C:\etw\RMAgent-AppTrace.etl"
$errs=@(); $n=0; $nerr=0; $nwarn=0
try{
  if(Test-Path $etl){
    & "C:\Windows\System32\logman.exe" flush RMAgent-AppTrace 2>&1|Out-Null
    $evs=Get-WinEvent -Path $etl -Oldest -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}
    $n=@($evs).Count
    foreach($e in $evs){
      # Level: 2=Error, 3=Warning, 4=Information, 5=Verbose
      if($e.Level -eq 2){$nerr++}
      elseif($e.Level -eq 3){$nwarn++}
      if($e.Level -le 3){
        $m=$e.Message+''
        $errs+=[pscustomobject]@{
          t=$e.TimeCreated.ToString('o')
          provider=$e.ProviderId
          id=$e.Id
          level=$e.Level
          msg=$m.Substring(0,[Math]::Min(180,$m.Length))
        }
      }
    }
    $errs=@($errs|Select -First $Limit)
  }
}catch{}
[pscustomobject]@{skill='apperrors';host=$hn;utc=$now;window_h=$sh;n_scanned=$n;n_errors=$nerr;n_warnings=$nwarn;recent=$errs}|ConvertTo-Json -Compress -Depth 4