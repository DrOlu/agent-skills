# agents — the agent census on Windows. Four probes fused. Read-only, capped.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
# NOTE: keywords must be specific enough to avoid FPs. Removed "roo" (matches
# root paths), "gpt"/"jan"/"llama"/"continue"/"amp" (too generic). See the
# linux payload for the full rationale.
$K=@('claude','opencode','aider','cursor-agent','goose','codex','copilot','cline','windsurf','kilocode','crush','gemini-cli','ollama','lmstudio','llamafile','vllm','sglang','anythingllm','open-webui','gpt4all','koboldcpp','autogen','crewai','langchain','llamaindex','agentgpt','superagent','cyberagent','rterm','gybackend','neuralos')
# NOTE: ports must match EXACTLY at end-of-string (:8000$ not :18000).
$E=@('api.anthropic.com','api.openai.com','openrouter.ai','api.groq.com','api.mistral.ai','api.deepseek.com','api.x.ai')
$PORTS=@(11434,1234,8000,8080,17888)
$D=@('.claude','.continue','.aider','.codex','.cursor','.gemini','.opencode','.ollama','.lmstudio','.goose','.claude.json','.agents')
# 1. PROCESS
$pr=@()
try{$all=Get-CimInstance Win32_Process|Select ProcessId,ParentProcessId,Name,CommandLine
foreach($p in $all){$n=($p.Name+'').ToLower();if(-not $n){continue}
foreach($k in $K){if($n -like "*$k*"){$cl=($p.CommandLine+'')
$pr+=[pscustomobject]@{name=$k;pid=$p.ProcessId;ppid=$p.ParentProcessId;comm=$p.Name;args=$cl.Substring(0,[Math]::Min(80,$cl.Length))};break}}}}catch{}
$pr=@($pr|Select -First $Limit)
# 2. NETWORK — host endpoints by substring, ports by EXACT remote port
$ec=@()
try{$cn=Get-NetTCPConnection -EA SilentlyContinue|?{$_.State -eq 'Established'}|Select -First 150
foreach($c in $cn){$ep="$($c.RemoteAddress):$($c.RemotePort)"
$hit=$null
foreach($e in $E){if($ep -like "*$e*"){$hit=$e;break}}
if(-not $hit -and ($PORTS -contains $c.RemotePort) -and ($c.RemoteAddress -in @('127.0.0.1','::1','localhost'))){$hit="local:$($c.RemotePort)"}
if($hit){$ec+=[pscustomobject]@{endpoint=$hit;pid=$c.OwningProcess}}}}catch{}
$ec=@($ec|Select -First $Limit)
# 3. FILES
$pt=@();foreach($d in $D){if(Test-Path (Join-Path $env:USERPROFILE $d)){$pt+=$d}}
# 4. PACKAGES
$pk=@()
try{$pk+=@(pip list 2>$null|Select-String 'langchain|autogen|crewai|openai|anthropic|litellm'|Select -First 8|%{$_.Line})}catch{}
try{$pk+=@(npm ls -g --depth=0 2>$null|Select-String 'claude|opencode|anthropic'|Select -First 5|%{$_.Line})}catch{}
[pscustomobject]@{skill='agents';host=$hn;utc=$now;n_procs=@($pr).Count;n_endpoints=@($ec).Count;n_paths=@($pt).Count;n_pkgs=@($pk).Count;procs=$pr;endpoint_conns=$ec;paths=($pt -join ';');pkgs=(($pk|Select -First 12) -join ';')}|ConvertTo-Json -Compress -Depth 4