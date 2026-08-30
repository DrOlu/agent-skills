# agentdrift — the agent census digest for the drift baseline (Windows).
# Compact, stable keys for diffing. The Python drift driver stores the baseline.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$K=@('claude','opencode','aider','cursor-agent','goose','codex','copilot','cline','windsurf','kilocode','crush','gemini-cli','ollama','lmstudio','llamafile','vllm','sglang','anythingllm','open-webui','gpt4all','koboldcpp','autogen','crewai','langchain','llamaindex','agentgpt','superagent','cyberagent','rterm','gybackend','neuralos')
$E=@('api.anthropic.com','api.openai.com','openrouter.ai','api.groq.com','api.mistral.ai','api.deepseek.com','api.x.ai')
$PORTS=@(11434,1234,8000,8080,17888)
$D=@('.claude','.continue','.aider','.codex','.cursor','.gemini','.opencode','.ollama','.lmstudio','.goose','.claude.json','.agents')
$kw="";try{$all=Get-CimInstance Win32_Process|Select Name,CommandLine
foreach($p in $all){$n=($p.Name+' '+$p.CommandLine).ToLower();if(-not $n){continue}
foreach($k in $K){if($n -like "*$k*"){$kw+="$k;";break}}}}catch{}
$ep="";try{$cn=Get-NetTCPConnection -EA SilentlyContinue|?{$_.State -eq 'Established'}|Select -First 150
foreach($c in $cn){$x="$($c.RemoteAddress):$($c.RemotePort)"
foreach($e in $E){if($x -like "*$e*"){$ep+="$e;";break}}
if($PORTS -contains $c.RemotePort -and $c.RemoteAddress -in @('127.0.0.1','::1')){$ep+="local:$($c.RemotePort);"}}}catch{}
$paths="";foreach($d in $D){if(Test-Path (Join-Path $env:USERPROFILE $d)){$paths+="$d;"}}
# dedupe the keyword hits
$kw=($kw -split ';'|Sort-Object -Unique|?{$_}) -join ';'
$ep=($ep -split ';'|Sort-Object -Unique|?{$_}) -join ';'
[pscustomobject]@{skill='agentdrift';host=$hn;utc=$now;kw_hits=$kw;ep_hits=$ep;paths=$paths}|ConvertTo-Json -Compress