# appproc — process lifecycle from the ProcTrace ring. Create/exit with full
# command line. Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$etl="C:\etw\RMAgent-ProcTrace.etl"
$procs=@(); $n=0
try{
  if(Test-Path $etl){
    & "C:\Windows\System32\logman.exe" flush RMAgent-ProcTrace 2>&1|Out-Null
    $evs=Get-WinEvent -Path $etl -Oldest -EA SilentlyContinue|?{$_.TimeCreated -gt $cutoff}|Select -First ($Limit*2)
    $n=@($evs).Count
    foreach($e in $evs){
      $m=$e.Message+''
      # kernel-process events: "Process X started/ended with command line Y"
      if($m -match '(?i)(started|created|exited|ended)'){
        $procs+=[pscustomobject]@{
          t=$e.TimeCreated.ToString('o')
          id=$e.Id
          op=if($m -match '(?i)start|create'){'start'}else{'end'}
          msg=$m.Substring(0,[Math]::Min(160,$m.Length))
        }
      }
    }
    $procs=@($procs|Select -First $Limit)
  }
}catch{}
[pscustomobject]@{skill='appproc';host=$hn;utc=$now;window_h=$sh;n_events=$n;n_procs=@($procs).Count;procs=$procs}|ConvertTo-Json -Compress -Depth 4