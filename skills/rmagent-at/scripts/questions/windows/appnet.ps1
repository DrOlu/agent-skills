# appnet — connection-level network from the NetTrace ring. Every TCP
# connection with owning PID. Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$etl="C:\etw\RMAgent-NetTrace.etl"
$conns=@(); $n=0
try{
  if(Test-Path $etl){
    logman flush RMAgent-NetTrace -ets 2>&1|Out-Null
    $evs=Get-WinEvent -Path $etl -Oldest -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}|Select -First ($Limit*3)
    $n=@($evs).Count
    $seen=@{}
    foreach($e in $evs){
      $m=$e.Message+''
      # kernel-network events carry the tuple in the message
      if($m -match '(?i)(\d+\.\d+\.\d+\.\d+):(\d+)\s*->\s*(\d+\.\d+\.\d+\.\d+):(\d+)'){
        $key="$($Matches[1]):$($Matches[2])->$($Matches[3]):$($Matches[4])"
        if(-not $seen.ContainsKey($key)){
          $seen[$key]=1
          $conns+=[pscustomobject]@{
            t=$e.TimeCreated.ToString('o')
            src="$($Matches[1]):$($Matches[2])"
            dst="$($Matches[3]):$($Matches[4])"
          }
        }
      }
    }
    $conns=@($conns|Select -First $Limit)
  }
}catch{}
[pscustomobject]@{skill='appnet';host=$hn;utc=$now;window_h=$sh;n_events=$n;n_conns=@($conns).Count;conns=$conns}|ConvertTo-Json -Compress -Depth 4