# agentnet — endpoint attribution on Windows. Which LLM APIs, by which PID.
# Read-only, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$E=@('api.anthropic.com','api.openai.com','openrouter.ai','api.groq.com','api.mistral.ai','api.deepseek.com','api.x.ai','api.moonshot.ai','api.z.ai')
$PORTS=@(11434,1234,8000,8080,17888)
$hits=@()
try{$cn=Get-NetTCPConnection -EA SilentlyContinue|?{$_.State -eq 'Established'}|Select -First 150
foreach($c in $cn){$ep="$($c.RemoteAddress):$($c.RemotePort)"
foreach($e in $E){if($ep -like "*$e*"){$hits+=[pscustomobject]@{endpoint=$e;pid=$c.OwningProcess;state=$c.State};break}}
if(-not $hit -and ($PORTS -contains $c.RemotePort) -and ($c.RemoteAddress -in @('127.0.0.1','::1'))){$hits+=[pscustomobject]@{endpoint="local:$($c.RemotePort)";pid=$c.OwningProcess;state=$c.State}}}}catch{}
$hits=@($hits|Select -First $Limit)
# DNS: query the DNS client cache for known endpoints
$dns=""
try{$dcs=Get-DnsClientCache -EA SilentlyContinue|?{$_.Entry -match 'anthropic|openai|openrouter|groq|mistral|deepseek|moonshot'}|Select -First 10
if($dcs){$dns=($dcs|%{$_.Entry}) -join ';'}}catch{}
[pscustomobject]@{skill='agentnet';host=$hn;utc=$now;n_hits=@($hits).Count;hits=$hits;dns_cache=$dns}|ConvertTo-Json -Compress -Depth 4