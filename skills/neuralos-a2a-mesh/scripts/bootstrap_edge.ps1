# bootstrap_edge.ps1 - install neuralOS engine + ReactorPro gateway + butler on
# Windows (NSSM, or sc.exe fallback) and wire them to survive reboot.
# Usage:  pwsh -File scripts\bootstrap_edge.ps1
$ErrorActionPreference = "Stop"

$missing = @()
function Need($name, $why) { if (-not (Get-Item "env:$name" -ErrorAction SilentlyContinue)) { $script:missing += "$name ($why)" } }
Need NATS_URL "central NATS endpoint, e.g. tls://hub.example:4222"
Need GATEWAY_MESH_ID "this edge's id, e.g. reactorpro/nairobi-01"
Need NEEDLE_ENGINE_DIR "folder holding needle.exe/neural.exe + weights"
Need LIVEAGENT_GATEWAY_TOKEN "gateway bearer token"
if ($missing.Count) { Write-Host "MISSING:"; $missing | ForEach-Object { Write-Host "  $_" }; Write-Host "`nAsk the operator (references/parameters.md)."; exit 2 }

$root       = if ($env:EDGE_ROOT) { $env:EDGE_ROOT } else { "C:\neuralos-edge" }
$butlerDir  = Join-Path $root "butler"
$logDir     = Join-Path $root "logs"
$gatewayExe = if ($env:GATEWAY_BIN) { $env:GATEWAY_BIN } else { Join-Path $root "gateway.exe" }
$python     = if ($env:BUTLER_PYTHON) { $env:BUTLER_PYTHON } else { "C:\Python314\python.exe" }
$skill      = if ($env:BUTLER_SKILL) { $env:BUTLER_SKILL } else { "butler.query" }
$name       = ($env:GATEWAY_MESH_ID -split '/')[-1]

New-Item -ItemType Directory -Force -Path $butlerDir, $logDir | Out-Null
Write-Host "== layout ==" -ForegroundColor Cyan
Write-Host "  root=$root  id=$($env:GATEWAY_MESH_ID)"

Write-Host "== 1. engine ==" -ForegroundColor Cyan
$bin = @("needle.exe","neural.exe") | ForEach-Object { Join-Path $env:NEEDLE_ENGINE_DIR $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
$w   = @("needle3.cact","neuralOS.engine")     | ForEach-Object { Join-Path $env:NEEDLE_ENGINE_DIR $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $bin -or -not $w) {
  Write-Host "  no engine bundle in $env:NEEDLE_ENGINE_DIR - installing via pip" -ForegroundColor Yellow
  & $python -m pip install --quiet neuralos
  if (-not (Test-Path $env:NEEDLE_ENGINE_DIR)) { New-Item -ItemType Directory -Force -Path $env:NEEDLE_ENGINE_DIR | Out-Null }
  Write-Host "  NOTE: pip bundles the engine library; for the raw binary unzip"
  Write-Host "        https://neuralos.ng/download/neuralOS.zip into $env:NEEDLE_ENGINE_DIR"
} else { Write-Host "  engine: $bin + $w" }

Write-Host "== 2. gateway binary ==" -ForegroundColor Cyan
if (Test-Path $gatewayExe) { Write-Host "  gateway: $gatewayExe" }
else { Write-Host "  gateway.exe not found - install reactorpro-gateway v1.7.5+ at $gatewayExe (or set GATEWAY_BIN)" -ForegroundColor Yellow }

Write-Host "== 3. butler harness ==" -ForegroundColor Cyan
$sb = if ($env:SKILL_BASE) { $env:SKILL_BASE } else { Split-Path (Split-Path $PSCommandPath) }
$tpl = Join-Path $sb "scripts\butler_template.py"
if (Test-Path $tpl) { Copy-Item $tpl (Join-Path $butlerDir "butler.py") -Force; Write-Host "  harness -> $butlerDir\butler.py" }
if (-not (Test-Path (Join-Path $butlerDir "needle_menu.json"))) {
  "[]" | Set-Content (Join-Path $butlerDir "needle_menu.json")
  Write-Host "  placeholder menu written - replace with the real probe menu" -ForegroundColor Yellow
}

Write-Host "== 4. NSSM services ==" -ForegroundColor Cyan
$nssm = "nssm"
if (-not (Get-Command $nssm -ErrorAction SilentlyContinue)) { $nssm = "C:\ProgramData\chocolatey\bin\nssm.exe" }
if (Test-Path $nssm) {
  & $nssm install ReactorProGateway $gatewayExe | Out-Null
  & $nssm set ReactorProGateway AppEnvironmentExtra `
      "LIVEAGENT_GATEWAY_MESH_ID=$($env:GATEWAY_MESH_ID)" `
      "LIVEAGENT_GATEWAY_MESH_URL=$($env:NATS_URL)" `
      "LIVEAGENT_GATEWAY_MESH_VERIFY_MODE=require" `
      "LIVEAGENT_GATEWAY_MESH_TRUST_ON_FIRST_USE=false" `
      "LIVEAGENT_GATEWAY_MESH_TRUSTED_PEERS=$($env:MESH_TRUSTED_PEERS)" `
      "LIVEAGENT_GATEWAY_TOKEN=$($env:LIVEAGENT_GATEWAY_TOKEN)" `
      "NEEDLE_ENGINE_DIR=$($env:NEEDLE_ENGINE_DIR)" | Out-Null
  & $nssm set ReactorProGateway AppStdout (Join-Path $logDir "gateway.log") | Out-Null
  & $nssm set ReactorProGateway AppStderr (Join-Path $logDir "gateway.err") | Out-Null
  & $nssm set ReactorProGateway Start SERVICE_AUTO_START | Out-Null

  & $nssm install "NeuralosButler-$name" $python (Join-Path $butlerDir "butler.py") | Out-Null
  & $nssm set "NeuralosButler-$name" AppDirectory $butlerDir | Out-Null
  & $nssm set "NeuralosButler-$name" AppEnvironmentExtra `
      "NEEDLE_ENGINE_DIR=$($env:NEEDLE_ENGINE_DIR)" "BUTLER_SKILL=$skill" | Out-Null
  & $nssm set "NeuralosButler-$name" AppStdout (Join-Path $logDir "butler.log") | Out-Null
  & $nssm set "NeuralosButler-$name" AppStderr (Join-Path $logDir "butler.err") | Out-Null
  & $nssm set "NeuralosButler-$name" Start SERVICE_AUTO_START | Out-Null

  Restart-Service ReactorProGateway -ErrorAction SilentlyContinue
  Write-Host "  services installed: ReactorProGateway, NeuralosButler-$name"
} else {
  Write-Host "  nssm not found. Equivalent sc.exe commands:" -ForegroundColor Yellow
  Write-Host "    sc.exe create ReactorProGateway binPath= `"$gatewayExe`" start= auto"
  Write-Host "    sc.exe create NeuralosButler-$name binPath= `"$python $butlerDir\butler.py`" start= auto"
  Write-Host "  (sc.exe cannot set env vars - use a wrapper .cmd that sets them first)"
}

Write-Host "`n== next ==" -ForegroundColor Cyan
Write-Host "  1) exchange fingerprints out of band; set MESH_TRUSTED_PEERS everywhere"
Write-Host "  2) pwsh -File scripts\doctor.ps1"
Write-Host "  3) pwsh -File scripts\dispatch.ps1 -Target reactorpro\<peer> -Butler reactorpro\<peer>-butler -Skill butler.query -Question `"never-seen question`""