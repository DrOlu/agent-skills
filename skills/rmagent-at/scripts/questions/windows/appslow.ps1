# appslow — the slow-request question. Finds requests/operations that took
# longer than a threshold in the AppTrace ring, with the top offenders.
# Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$etl="C:\etw\RMAgent-AppTrace.etl"
$slow=@(); $n=0
try{
  if(Test-Path $etl){
    & "C:\Windows\System32\logman.exe" flush RMAgent-AppTrace 2>&1|Out-Null
    $evs=Get-WinEvent -Path $etl -Oldest -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}
    $n=@($evs).Count
    # look for duration-like fields in the message (HTTP.sys, .NET timing)
    foreach($e in $evs){
      $m=$e.Message+''
      # HTTP.sys / IIS put elapsed time in the message; .NET EventSource often
      # has a field. Match common duration patterns.
      if($m -match '(?i)(duration|elapsed|time taken|milliseconds|ms)\D*(\d{3,})'){
        $ms=[int]$Matches[2]
        if($ms -ge 500){
          $slow+=[pscustomobject]@{
            t=$e.TimeCreated.ToString('o')
            provider=$e.ProviderId
            id=$e.Id
            ms=$ms
            msg=$m.Substring(0,[Math]::Min(140,$m.Length))
          }
        }
      }
    }
    $slow=@($slow|Sort-Object ms -Descending|Select -First $Limit)
  }
}catch{}
[pscustomobject]@{skill='appslow';host=$hn;utc=$now;window_h=$sh;n_scanned=$n;n_slow=@($slow).Count;slowest=$slow}|ConvertTo-Json -Compress -Depth 4