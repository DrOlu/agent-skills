# dispatch.ps1 - call a remote butler through the signed skillproxy lane.
# Windows PowerShell. Measures wall time.
# Usage: pwsh -File scripts\dispatch.ps1 -Target reactorpro\peer-01 `
#          -Butler reactorpro\peer-01-butler -Skill butler.query `
#          -Question "which customer spent the most?" [-TimeoutMs 120000]
param(
  [Parameter(Mandatory=$true)][string]$Target,
  [Parameter(Mandatory=$true)][string]$Butler,
  [Parameter(Mandatory=$true)][string]$Skill,
  [Parameter(Mandatory=$true)][string]$Question,
  [int]$TimeoutMs = 120000
)
$ErrorActionPreference = "Stop"
if (-not $env:LIVEAGENT_GATEWAY_TOKEN) { throw "set LIVEAGENT_GATEWAY_TOKEN" }
$gw = if ($env:GATEWAY_URL) { $env:GATEWAY_URL } else { "http://127.0.0.1:3000" }

$body = @{
  target    = $Target
  skill     = "skillproxy"
  timeoutMs = $TimeoutMs
  input     = @{ target = $Butler; skill = $Skill; args = @{ question = $Question } }
} | ConvertTo-Json -Depth 6

$t0 = Get-Date
try {
  $resp = Invoke-RestMethod -Method Post -Uri "$gw/api/mesh/dispatch" `
            -Headers @{ Authorization = "Bearer $env:LIVEAGENT_GATEWAY_TOKEN" } `
            -ContentType "application/json" -Body $body `
            -TimeoutSec ([int]($TimeoutMs/1000) + 10)
} catch {
  Write-Host "DISPATCH FAILED: $($_.Exception.Message)" -ForegroundColor Red
  Write-Host "run doctor.ps1 - the failure is usually transport or trust, not the engine."
  exit 1
}
$wall = [math]::Round(((Get-Date) - $t0).TotalSeconds, 2)
$reply = $resp.payload.output.reply
if ($reply.ok) {
  Write-Host "OK  grounded=$($reply.grounding)  engine_elapsed=$($reply.elapsed_s)s  wall=${wall}s" -ForegroundColor Green
  Write-Host $reply.result
} else {
  Write-Host "HOLE/FAIL  wall=${wall}s" -ForegroundColor Yellow
  $reply | ConvertTo-Json -Depth 4
  exit 1
}