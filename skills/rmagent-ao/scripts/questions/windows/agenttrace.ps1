# agenttrace — recent agent activity on Windows from disk artifacts.
# Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$sh=${SinceHours:2}; $cutoff=(Get-Date).AddHours(-[double]$sh)
$sessions=@(); $files=@()
# Claude Code sessions
try{$cc=Get-ChildItem "$env:USERPROFILE\.claude\projects" -Recurse -Filter *.jsonl -EA SilentlyContinue|?{$_.LastWriteTime -gt $cutoff}|Select -First $Limit
if($cc){$sessions+="claude-code: $(@($cc).Count) session file(s)"; $files+=@($cc|%{$_.FullName.Substring(0,[Math]::Min(80,$_.FullName.Length))}|Select -First 3)}}catch{}
# OpenCode
foreach($d in @("$env:USERPROFILE\.opencode","$env:USERPROFILE\.local\share\opencode")){
try{$oc=Get-ChildItem $d -Recurse -File -EA SilentlyContinue|?{$_.LastWriteTime -gt $cutoff}|Select -First $Limit
if($oc){$sessions+="opencode: $(@($oc).Count) file(s)"}}catch{}}
# Aider history
foreach($f in @("$env:USERPROFILE\.aider.chat.history.md","$env:USERPROFILE\.aider.input.history")){
try{if((Test-Path $f) -and ((Get-Item $f).LastWriteTime -gt $cutoff)){$sessions+="aider: history active"}}catch{}}
# Ollama logs
try{$ol=Get-ChildItem "$env:LOCALAPPDATA\Ollama\server\logs" -File -EA SilentlyContinue|?{$_.LastWriteTime -gt $cutoff}|Select -First 3
if($ol){$sessions+="ollama: logs active"}}catch{}
[pscustomobject]@{skill='agenttrace';host=$hn;utc=$now;window_h=$sh;sessions=($sessions -join '|');files=(($files|Select -First 5) -join ';')}|ConvertTo-Json -Compress