# doctor.ps1 - environment + connectivity diagnostic for a neuralOS A2A edge.
# Windows PowerShell. Prints PASS/FAIL per layer.
# Usage:  pwsh -File scripts\doctor.ps1
$ErrorActionPreference = "Continue"

$script:PASS = 0; $script:FAIL = 0
function Ok($m)   { Write-Host "  PASS  $m" -ForegroundColor Green; $script:PASS++ }
function Bad($m)  { Write-Host "  FAIL  $m" -ForegroundColor Red;   $script:FAIL++ }
function Warn($m) { Write-Host "  WARN  $m" -ForegroundColor Yellow }
function Sec($m)  { Write-Host "`n== $m ==" -ForegroundColor Cyan }

Sec "1. Host"
Ok "os: $([System.Environment]::OSVersion.VersionString)"
Ok "host: $env:COMPUTERNAME"
$py = "C:\Python314\python.exe"
if (Test-Path $py) { Ok "python: $py" } else { Warn "python not at $py - set BUTLER_PYTHON" }
try { w32tm /resync | Out-Null; Ok "time sync" } catch { Warn "w32tm resync failed (check the clock)" }

Sec "2. Engine (neuralOS / needle)"
$dir = $env:NEEDLE_ENGINE_DIR
if ($dir -and (Test-Path $dir)) {
  Ok "NEEDLE_ENGINE_DIR=$dir"
  $bin = @("needle.exe","neural.exe","needle","neural") | ForEach-Object { Join-Path $dir $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
  $w   = @("needle3.cact","neuralOS.engine")           | ForEach-Object { Join-Path $dir $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($bin) { Ok "engine binary: $bin" } else { Bad "no engine binary in $dir" }
  if ($w)   { Ok "weights: $w ($([math]::Round((Get-Item $w).Length/1MB,1)) MB)" } else { Bad "no weights in $dir" }
} else { Bad "NEEDLE_ENGINE_DIR unset or missing (never hardcode the engine path)" }

Sec "3. Menu"
$menu = if ($env:BUTLER_MENU) { $env:BUTLER_MENU } else { Join-Path (Get-Location) "needle_menu.json" }
if (Test-Path $menu) {
  $j = Get-Content $menu -Raw | ConvertFrom-Json
  $tools = if ($j -is [array]) { $j } else { $j.tools }
  Ok "menu: $menu ($($tools.Count) probes)"
  $missing = ($tools | Where-Object { -not $_.triggers }).Count
  if ($missing -eq 0) { Ok "every probe has triggers" } else { Bad "$missing probe(s) missing triggers" }
} else { Bad "no needle_menu.json (set BUTLER_MENU)" }

Sec "4. Central NATS"
if (-not $env:NATS_URL) { Bad "NATS_URL unset (ask the operator)" }
else {
  Ok "NATS_URL=$($env:NATS_URL)"
  $hp = ($env:NATS_URL -replace '^[a-z]+://','' -split '/')[0]
  $h = $hp.Split(':')[0]; $p = if ($hp.Contains(':')) { [int]$hp.Split(':')[1] } else { 4222 }
  if (Test-NetConnection -ComputerName $h -Port $p -InformationLevel Quiet) { Ok "tcp reachable $h`:$p" }
  else { Bad "cannot reach $h`:$p (firewall/DNS?)" }
  if ($env:NATS_MON) {
    try {
      $v = Invoke-RestMethod "$($env:NATS_MON)/varz"
      Ok "monitoring $($env:NATS_MON) (server $($v.version))"
      $jz = Invoke-RestMethod "$($env:NATS_MON)/jsz"
      if ($jz.api.errors -eq 0) { Ok "JetStream api.errors=0" } else { Warn "JetStream api.errors=$($jz.api.errors)" }
    } catch { Warn "monitoring $($env:NATS_MON) not answering" }
  } else { Warn "NATS_MON unset" }
}

Sec "5. Gateway + trust"
try { Invoke-WebRequest "http://127.0.0.1:3000/healthz" -TimeoutSec 5 | Out-Null; Ok "gateway :3000 healthz" }
catch { Bad "gateway not answering on :3000" }
if ($env:LIVEAGENT_GATEWAY_TOKEN) {
  try {
    $st = Invoke-RestMethod -Headers @{ Authorization = "Bearer $($env:LIVEAGENT_GATEWAY_TOKEN)" } `
                            "http://127.0.0.1:3000/api/mesh/status" -TimeoutSec 5
    if ($st.connected) { Ok "mesh connected" } else { Bad "mesh not connected" }
    Write-Host "  INFO  id=$($st.agentId)  fp=$($st.fingerprint)"
  } catch { Bad "mesh status call failed" }
} else { Warn "LIVEAGENT_GATEWAY_TOKEN unset" }
if ($env:MESH_TRUSTED_PEERS) { Ok "peer pins configured" } else { Bad "MESH_TRUSTED_PEERS unset (invoke will 3004)" }
if ($env:GATEWAY_MESH_ID) { Ok "mesh id: $($env:GATEWAY_MESH_ID)" } else { Bad "GATEWAY_MESH_ID unset" }

Sec "RESULT"
Write-Host "  $script:PASS passed, $script:FAIL failed"
if ($script:FAIL -eq 0) { Write-Host "  ALL GOOD - run dispatch.ps1 for an end-to-end proof" -ForegroundColor Green; exit 0 }
else { Write-Host "  fix the FAIL lines above (see references/troubleshooting.md)" -ForegroundColor Red; exit 1 }