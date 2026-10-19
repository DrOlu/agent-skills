<#
.SYNOPSIS
  Plasma node bootstrap: fetch latest release, verify SHA256, install.
  Run ON the Windows node in an elevated PowerShell.

.PARAMETER GithubToken
  PAT with repo read access (repo is private). Also accepts
  $env:PLASMA_GITHUB_TOKEN.

.PARAMETER Version
  Release tag (default: latest).

.EXAMPLE
  .\bootstrap-node.ps1 -GithubToken ghp_xxx
  .\bootstrap-node.ps1 -GithubToken ghp_xxx -Version v0.11.1
#>
param(
    [Parameter(Mandatory)] [string] $GithubToken,
    [string] $Version = "latest",
    [string] $WorkDir = "C:\ProgramData\PlasmaSetup"
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Set-Location $WorkDir

$headers = @{ Authorization = "Bearer $GithubToken"; Accept = 'application/vnd.github+json' }
$octet   = @{ Authorization = "Bearer $GithubToken"; Accept = 'application/octet-stream' }

$tag  = if ($Version -eq "latest") { "latest" } else { $Version }
$rel  = Invoke-RestMethod -Uri "https://api.github.com/repos/DrOlu/plasma/releases/tags/$tag" `
        -Headers $headers -TimeoutSec 30

$exeAsset  = $rel.assets | Where-Object name -like 'plasma-*.exe' | Select-Object -First 1
$sumsAsset = $rel.assets | Where-Object name -eq 'SHA256SUMS'      | Select-Object -First 1
if (-not $exeAsset) { throw "no plasma exe asset in release $($rel.tag_name)" }

Invoke-WebRequest -UseBasicParsing -Uri $exeAsset.url  -Headers $octet `
  -OutFile $exeAsset.name -TimeoutSec 600
Invoke-WebRequest -UseBasicParsing -Uri $sumsAsset.url -Headers $octet `
  -OutFile SHA256SUMS -TimeoutSec 60

$expected = ((Get-Content SHA256SUMS -TotalCount 1) -split '\s+')[0]
$actual   = (Get-FileHash $exeAsset.name -Algorithm SHA256).Hash.ToLower()
if ($expected -ne $actual) { throw "SHA256 mismatch: $expected != $actual" }
"verified: $($exeAsset.name) ($expected)"

$p = Start-Process -FilePath ".\$($exeAsset.name)" -ArgumentList 'install' -Wait -PassThru `
     -NoNewWindow -RedirectStandardOutput install-out.json -RedirectStandardError install-err.txt
"install_exit=$($p.ExitCode)"
Get-Content install-out.json

if ($p.ExitCode -eq 0) {
    & ".\$($exeAsset.name)" --version
    & ".\$($exeAsset.name)" health | Select-String '"status"' | Select-Object -First 1
}
