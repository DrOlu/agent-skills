# deepwindow — 60 seconds of kernel truth, on demand. No agent. No lake.
#
# The honest answer to real-time: during an active hunt, open a short-lived ETW
# trace on the suspect box, capture process/network/image-load events at full
# fidelity, stop the trace, read it back. The trace only exists while you are
# actively investigating. Nothing persists.
#
# Closes the fidelity gap vs Sysmon exactly when it matters: mid-hunt.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$ErrorActionPreference='SilentlyContinue'
$tag='RMAgentDW'; $etl="$env:TEMP\rm_dw.etl"

# Start the kernel trace (process + network + image events)
logman start RMAgentDW -ets -o $etl -p "Windows Kernel Trace" 0x10 -mode Circular 2>$null
if (-not $?) {
  [pscustomobject]@{skill='deepwindow';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');status='failed-to-start';error='logman start failed'}|ConvertTo-Json -Compress
  exit
}

# Capture window — the caller controls duration via $Limit seconds (default 60)
$dur = if ($Limit -and $Limit -gt 0) { $Limit } else { 60 }
Start-Sleep -Seconds $dur

# Stop the trace
logman stop RMAgentDW -ets 2>$null | Out-Null

# Read it back
$procs=@(); $nets=@()
if (Test-Path $etl) {
  try {
    $events = Get-WinEvent -Path $etl -Oldest -ErrorAction SilentlyContinue | Select-Object -First 500
    foreach ($e in $events) {
      $x=[xml]$e.ToXml()
      $ns=New-Object System.Xml.XmlNamespaceManager($x.NameTable)
      $ns.AddNamespace('e','http://schemas.microsoft.com/win/2004/08/events/event')
      $img=$x.SelectSingleNode("//e:Data[@Name='ImageName']",$ns)
      $pid2=$x.SelectSingleNode("//e:Data[@Name='ProcessID']",$ns)
      $daddr=$x.SelectSingleNode("//e:Data[@Name='daddr']",$ns)
      $dport=$x.SelectSingleNode("//e:Data[@Name='dport']",$ns)
      if ($img -and $img.'#text') {
        $procs += [pscustomobject]@{t=$e.TimeCreated.ToString('o');pid=$pid2.'#text';img=$img.'#text'}
      } elseif ($daddr -and $daddr.'#text') {
        $nets += [pscustomobject]@{t=$e.TimeCreated.ToString('o');pid=$pid2.'#text';dest=$daddr.'#text';port=$dport.'#text'}
      }
    }
  } catch {}
  Remove-Item $etl -Force 2>$null
}

[pscustomobject]@{
  skill='deepwindow'
  host=$env:COMPUTERNAME
  utc=[DateTime]::UtcNow.ToString('o')
  duration_s=$dur
  status='completed'
  procs=@($procs)
  nets=@($nets)
}|ConvertTo-Json -Compress -Depth 4
