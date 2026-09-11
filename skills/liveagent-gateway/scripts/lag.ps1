# lag.ps1 - LiveAgent Gateway HTTP CLI for Windows PowerShell
#
#   $env:LAG_GW    = "http://localhost:3000"
#   $env:LAG_TOKEN = "<gateway token>"
#   $env:LAG_AGENT = "agent-<uuid>"
#
#   .\lag.ps1 health
#   .\lag.ps1 agents
#   .\lag.ps1 issue-token -Agent "agent-<uuid>" -Name "office-pc"
#   .\lag.ps1 upload .\report.pdf
#
# Commands: health status agents issue-token rename-agent delete-agent upload share help
[CmdletBinding()]
param(
  [Parameter(Position = 0)][string]$Command = "help",
  [Parameter(Position = 1, ValueFromRemainingArguments = $true)][string[]]$Rest = @(),
  [string]$Gw    = $env:LAG_GW,
  [string]$Token = $env:LAG_TOKEN,
  [string]$Agent = $env:LAG_AGENT,
  [string]$Name  = ""
)

$ErrorActionPreference = "Stop"
if (-not $Gw) { $Gw = "http://localhost:3000" }
$Gw = $Gw.TrimEnd('/')
$AMP = [char]38

function Show-Usage {
  Write-Output "LiveAgent Gateway HTTP CLI (PowerShell)"
  Write-Output ""
  Write-Output "  .\lag.ps1 <command> [-Name N] [-Agent ID] [-Gw URL] [-Token T]"
  Write-Output ""
  Write-Output "Commands"
  Write-Output "  health                        Liveness check (no auth needed)"
  Write-Output "  status                        Agent online states + protocol usage"
  Write-Output "  agents [page] [size] [state]  Agent directory (state: all|online|offline)"
  Write-Output "  issue-token                   Issue or rotate the credential for -Agent"
  Write-Output "  rename-agent                  Set or clear the display name (-Name)"
  Write-Output "  delete-agent                  Delete the record, credential and live session"
  Write-Output "  upload <path> [path...]       Upload readable files"
  Write-Output "  share <share-token>           Resolve a public history share"
  Write-Output "  help                          This text"
  Write-Output ""
  Write-Output "Environment: LAG_GW  LAG_TOKEN  LAG_AGENT"
  Write-Output "WARNING: issue-token (rotation) and delete-agent disconnect that agent immediately."
}

function Get-Headers { @{ Authorization = "Bearer $Token" } }

function Require-Token {
  if (-not $Token) { throw "set LAG_TOKEN or pass -Token" }
}

function Require-Agent {
  if (-not $Agent) { throw "set LAG_AGENT or pass -Agent" }
}

switch ($Command.ToLower()) {
  "health" {
    (Invoke-RestMethod -Uri "$Gw/healthz" -TimeoutSec 15) | ConvertTo-Json -Depth 6
  }

  "status" {
    Require-Token
    (Invoke-RestMethod -Uri "$Gw/api/status" -Headers (Get-Headers) -TimeoutSec 30) |
      ConvertTo-Json -Depth 8
  }

  "agents" {
    Require-Token
    $page = if ($Rest.Count -ge 1) { $Rest[0] } else { 1 }
    $size = if ($Rest.Count -ge 2) { $Rest[1] } else { 50 }
    $st   = if ($Rest.Count -ge 3) { $Rest[2] } else { "all" }
    $qs = "page=" + $page + $AMP + "page_size=" + $size + $AMP + "status=" + $st
    $r = Invoke-RestMethod -Uri "$Gw/api/agents?$qs" -Headers (Get-Headers) -TimeoutSec 30
    Write-Output "total=$($r.total) page=$($r.page) size=$($r.page_size) has_more=$($r.has_more)"
    foreach ($a in $r.agents) {
      $nm = if ($a.name) { $a.name } else { "(none)" }
      Write-Output "  $($a.agent_id)  online=$($a.online)  name=$nm"
    }
  }

  "issue-token" {
    Require-Token; Require-Agent
    Write-Warning "Rotation immediately disconnects agent $Agent."
    $body = if ($Name) { @{ name = $Name } | ConvertTo-Json } else { "{}" }
    Invoke-RestMethod -Uri "$Gw/api/agents/$Agent/token" -Method Post `
      -Headers (Get-Headers) -ContentType "application/json" -Body $body -TimeoutSec 30 |
      ConvertTo-Json -Depth 6
  }

  "rename-agent" {
    Require-Token; Require-Agent
    $body = @{ name = $Name } | ConvertTo-Json
    Invoke-RestMethod -Uri "$Gw/api/agents/$Agent" -Method Patch `
      -Headers (Get-Headers) -ContentType "application/json" -Body $body -TimeoutSec 30 |
      ConvertTo-Json -Depth 6
  }

  "delete-agent" {
    Require-Token; Require-Agent
    Write-Warning "Deletes the record, revokes the credential and drops the live session."
    Invoke-RestMethod -Uri "$Gw/api/agents/$Agent" -Method Delete `
      -Headers (Get-Headers) -TimeoutSec 30 | ConvertTo-Json -Depth 6
  }

  "upload" {
    Require-Token
    if ($Rest.Count -lt 1) { throw "upload needs at least one file path" }
    foreach ($p in $Rest) {
      if (-not (Test-Path $p)) { throw "no such file: $p" }
      $form = @{ files = Get-Item $p; agent_id = $Agent }
      Invoke-RestMethod -Uri "$Gw/api/files/import" -Method Post `
        -Headers (Get-Headers) -Form $form -TimeoutSec 120 | ConvertTo-Json -Depth 6
    }
  }

  "share" {
    if ($Rest.Count -lt 1) { throw "share needs a share token" }
    try {
      Invoke-RestMethod -Uri "$Gw/api/public/history-shares/$($Rest[0])" -TimeoutSec 30 |
        ConvertTo-Json -Depth 8
    } catch {
      Write-Output "HTTP $($_.Exception.Response.StatusCode.value__)"
      Write-Output $_.ErrorDetails.Message
    }
  }

  { $_ -in "help", "-h", "--help", "" } { Show-Usage }

  default {
    Write-Warning "unknown command: $Command"
    Show-Usage
  }
}
