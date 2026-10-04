# deepwindow — 60 seconds of kernel truth, on demand. No agent. No lake.
#
# The honest answer to real-time: during an active hunt, open a short-lived ETW
# trace on the suspect box, capture process/network/image-load events at full
# fidelity, stop the trace, read it back. The trace only exists while you are
# actively investigating. Nothing persists.
#
# REV 5 (2026-09-27): the kernel provider ONLY attaches to the "NT Kernel
# Logger" session — a named session (RMAgentDW) fails with "the session name
# provided is invalid" (verified live on ws2; this was the long-standing
# 'ETW payload empty' hole). Also: Get-WinEvent cannot decode kernel ETL
# (EID 0, empty messages) — read back with tracerpt, whose XML carries the
# classic MOF field names (ImageName, daddr, dport). Flags 0x10005 =
# process | image load | network tcpip.
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$ErrorActionPreference='SilentlyContinue'
$etl="$env:TEMP\rm_dw.etl"; $tx="$env:TEMP\rm_dw.xml"

# If another NT Kernel Logger session is live, it is someone else's trace —
# do not kill it; return an honest hole instead.
$running = (& logman query "NT Kernel Logger" 2>&1 | Out-String)
if ($LASTEXITCODE -eq 0) {
  [pscustomobject]@{skill='deepwindow';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');status='busy';error='NT Kernel Logger already in use by another session'}|ConvertTo-Json -Compress
  exit
}

# Start the kernel trace (process + image + network events)
$start = (& logman start "NT Kernel Logger" -ets -o $etl -p "Windows Kernel Trace" 0x10005 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0) {
  [pscustomobject]@{skill='deepwindow';host=$env:COMPUTERNAME;utc=[DateTime]::UtcNow.ToString('o');status='failed-to-start';error=$start.Trim()}|ConvertTo-Json -Compress
  exit
}

# Capture window — the caller controls duration via $Limit seconds (default 60)
$dur = if ($Limit -and $Limit -gt 0) { $Limit } else { 60 }
Start-Sleep -Seconds $dur

# Stop the trace
& logman stop "NT Kernel Logger" -ets 2>&1 | Out-Null

# Read it back via tracerpt (kernel events decode only there)
$procs=@(); $images=@(); $nets=@(); $parsed=0
if (Test-Path $etl) {
  & tracerpt $etl -o $tx -of XML -y 2>$null | Out-Null
  if (Test-Path $tx) {
    try {
      [xml]$doc = Get-Content $tx -Raw
      # tracerpt XML carries a default namespace - match local names only.
      # Modern kernel decode (Server 2022): process events carry ImageFileName
      # + CommandLine + ParentId + UserSID; image loads carry FileName +
      # ProcessName. Kernel TCP events do not decode on this platform - nets
      # stays empty and status says so honestly.
      $evs = @($doc.SelectNodes('//*[local-name()="Event"]') | Select-Object -First 5000)
      foreach ($e in $evs) {
        $t = ''
        $tc = $e.SelectSingleNode("./*[local-name()='System']/*[local-name()='TimeCreated']")
        if ($tc) { $t = $tc.GetAttribute('SystemTime') }
        function DN($e,$n){ $o=$e.SelectSingleNode("./*[local-name()='EventData']/*[local-name()='Data' and @Name='$n']"); if($o){$o.InnerText.Trim()}else{$null} }
        $ifn = DN $e 'ImageFileName'
        $fn   = DN $e 'FileName'
        $pid2 = DN $e 'ProcessId'
        if ($ifn) {
          $parsed++
          if ($procs.Count -lt $Limit) {
            $procs += [pscustomobject]@{t=$t; img=$ifn; pid=$pid2; cmd=(DN $e 'CommandLine'); parent=(DN $e 'ParentId'); sid=(DN $e 'UserSID')}
          }
        } elseif ($fn) {
          $parsed++
          if ($images.Count -lt $Limit) {
            $images += [pscustomobject]@{t=$t; file=$fn; proc=(DN $e 'ProcessName'); pid=$pid2}
          }
        }
      }
    } catch {}
  }
  Remove-Item $etl -Force 2>$null
  Remove-Item $tx -Force 2>$null
}

[pscustomobject]@{
  skill='deepwindow'
  host=$env:COMPUTERNAME
  utc=[DateTime]::UtcNow.ToString('o')
  duration_s=$dur
  status= if($procs.Count -gt 0 -or $images.Count -gt 0){'completed'}else{'completed-empty'}
  rows_seen=$parsed
  procs=@($procs)
  images=@($images)
  nets=@($nets)
  nets_note='kernel TCP events do not decode on this platform (Server 2022 + NT Kernel Logger); network truth comes from 5156/netedges'
}|ConvertTo-Json -Compress -Depth 4
