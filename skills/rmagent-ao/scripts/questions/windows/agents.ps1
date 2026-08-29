# agents — the agent census on Windows. Four probes fused. Read-only, capped.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$K=@('claude','opencode','aider','continue','cursor','goose','codex','copilot','cline','roo','windsurf','zed','amp','kilo','crush','gemini','gpt','ollama','lmstudio','llama','vllm','jan','autogen','crewai','langchain','llamaindex','agentgpt','superagent','cyberagent','rterm','gybackend','neuralos')
$E=@('api.anthropic.com','api.openai.com','openrouter.ai','api.groq.com','api.mistral.ai','api.deepseek.com','api.x.ai','11434','1234','8000','8080','17888')
$D=@('.claude','.continue','.aider','.codex','.cursor','.gemini','.opencode','.ollama','.lmstudio','.goose','.claude.json','.agents')
# 1. PROCESS
$pr=@()
try{$all=Get-CimInstance Win32_Process|Select ProcessId,ParentProcessId,Name,CommandLine
foreach($p in $all){$n=($p.Name+'').ToLower();if(-not $n){continue}
foreach($k in $K){if($n -like "*$k*"){$cl=($p.CommandLine+'')
$pr+=[pscustomobject]@{name=$k;pid=$p.ProcessId;ppid=$p.ParentProcessId;comm=$p.Name;args=$cl.Substring(0,[Math]::Min(80,$cl.Length))};break}}}}catch{}
$pr=@($pr|Select -First $Limit)
# 2. NETWORK
$ec=@()
try{$cn=Get-NetTCPConnection -EA SilentlyContinue|?{$_.State -eq 'Established'}|Select -First 150
foreach($c in $cn){$ep="$($c.RemoteAddress):$($c.RemotePort)"
foreach($e in $E){if($ep -like "*$e*"){$ec+=[pscustomobject]@{endpoint=$e;pid=$c.OwningProcess};break}}}}catch{}
$ec=@($ec|Select -First $Limit)
# 3. FILES
$pt=@();foreach($d in $D){if(Test-Path (Join-Path $env:USERPROFILE $d)){$pt+=$d}}
# 4. PACKAGES
$pk=@()
try{$pk+=@(pip list 2>$null|Select-String 'langchain|autogen|crewai|openai|anthropic|litellm'|Select -First 8|%{$_.Line})}catch{}
try{$pk+=@(npm ls -g --depth=0 2>$null|Select-String 'claude|opencode|anthropic'|Select -First 5|%{$_.Line})}catch{}
[pscustomobject]@{skill='agents';host=$hn;utc=$now;n_procs=@($pr).Count;n_endpoints=@($ec).Count;n_paths=@($pt).Count;n_pkgs=@($pk).Count;procs=$pr;endpoint_conns=$ec;paths=($pt -join ';');pkgs=(($pk|Select -First 12) -join ';')}|ConvertTo-Json -Compress -Depth 4