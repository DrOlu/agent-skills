# apptrace — read the RMAgent-AppTrace ring buffer. Application-level events
# from .NET / HTTP.sys / IIS. Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$etl="C:\etw\RMAgent-AppTrace.etl"
$events=@(); $n=0
try{
  if(Test-Path $etl){
    # flush the live session to the file first so we read current events
    & "C:\Windows\System32\logman.exe" flush RMAgent-AppTrace 2>&1|Out-Null
    $evs=Get-WinEvent -Path $etl -Oldest -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}|Select -First $Limit
    $n=@($evs).Count
    foreach($e in $evs){
      $events+=[pscustomobject]@{
        t=$e.TimeCreated.ToString('o')
        provider=$e.ProviderId
        id=$e.Id
        level=$e.Level
        msg=($e.Message+'').Substring(0,[Math]::Min(160,($e.Message+'').Length))
      }
    }
  }
}catch{}
[pscustomobject]@{skill='apptrace';host=$hn;utc=$now;window_h=$sh;n_events=$n;events=$events}|ConvertTo-Json -Compress -Depth 4