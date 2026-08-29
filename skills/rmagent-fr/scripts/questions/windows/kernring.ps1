# kernring — kernel process events via a SHORT-LIVED ETW TRACE SESSION (burst on demand).
#
# ARCHITECTURE NOTE (live-validated 2026-08-22): the kernel analytic CHANNELS alone
# produce zero events — the channel is the destination, but a TRACE SESSION is the
# producer. Real-time kernel capture requires a running consumer (that is what Sysmon
# is). This payload uses the burst pattern instead: start a trace, wait $SinceHours
# worth of capture is NOT possible — so it captures a SHORT WINDOW (seconds) and
# returns what the kernel saw DURING that window.
#
# USE CASE: during an active hunt, when you need high-fidelity kernel-level process
# data on one box for a short window. NOT a continuous ring — Sysmon is the ring.
#
# Also reports sysmon_status (the tripwire: if Sysmon is down, this is your fallback
# for a live look, not for history).
#
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$sysmon='unknown'
try{$svc=Get-Service Sysmon64,Sysmon -ErrorAction SilentlyContinue|Select-Object -First 1; if($svc){$sysmon="$($svc.Name)=$($svc.Status)"}else{$sysmon='not-installed'}}catch{}

# Burst: 10-second trace of kernel process events
$etl="$env:TEMP\rmagent_kernel_burst.etl"
$procs=@()
try{
  # clean any stale session
  logman stop RMAgentKB -ets 2>&1|Out-Null
  Remove-Item $etl -Force -ErrorAction SilentlyContinue
  # start the burst
  logman create trace RMAgentKB -p Microsoft-Windows-Kernel-Process -o $etl -ets 2>&1|Out-Null
  Start-Sleep -Seconds 10
  logman stop RMAgentKB -ets 2>&1|Out-Null
  # read what we captured
  if(Test-Path $etl){
    $evts=Get-WinEvent -Path $etl -Oldest -ErrorAction SilentlyContinue|Select-Object -First $Limit
    foreach($e in $evts){
      $x=[xml]$e.ToXml()
      $ns=New-Object System.Xml.XmlNamespaceManager($x.NameTable)
      $ns.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event')
      $pid2=$x.SelectSingleNode("//e:Data[@Name='ProcessID']",$ns)
      $img=$x.SelectSingleNode("//e:Data[@Name='ImageName']",$ns)
      $cmd=$x.SelectSingleNode("//e:Data[@Name='CommandLine']",$ns)
      if($e.Id -in @(1,2,3)){
        $procs+=[pscustomobject]@{
          t=$e.TimeCreated.ToString('o');eid=$e.Id
          pid=if($pid2){$pid2.'#text'}else{$null}
          img=if($img){$img.'#text'}else{$null}
          cmd=if($cmd){$cmd.'#text'}else{$null}
        }
      }
    }
  }
}catch{}
finally{
  logman stop RMAgentKB -ets 2>&1|Out-Null
  Remove-Item $etl -Force -ErrorAction SilentlyContinue
}

[pscustomobject]@{
  skill='kernring'
  host=$env:COMPUTERNAME
  utc=[DateTime]::UtcNow.ToString('o')
  track=$Track
  sysmon_status=$sysmon
  burst_seconds=10
  procs=@($procs)
  note='burst capture — 10s window, not a ring. Sysmon is the ring.'
}|ConvertTo-Json -Compress -Depth 4
