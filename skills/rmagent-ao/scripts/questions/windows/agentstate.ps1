# agentstate — one agent's config on Windows: version, models, env-var NAMES.
# Read-only. Env var VALUES are never read — names only, for key-presence.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
# env var NAMES that signal agent presence (never values)
$ENVN=@('ANTHROPIC_API_KEY','OPENAI_API_KEY','OPENROUTER_API_KEY','GROQ_API_KEY',
'MISTRAL_API_KEY','DEEPSEEK_API_KEY','TOGETHER_API_KEY','XAI_API_KEY','GOOGLE_API_KEY',
'CLAUDE_CODE','CLAUDE','OPENCODE','AIDER','CURSOR','GOOSE','OLLAMA_HOST','LMSTUDIO',
'AGENT_SETTINGS','RTERM_SECRETS_MASTER_KEY')
$found=@();foreach($n in $ENVN){if([Environment]::GetEnvironmentVariable($n)){ $found+=$n }}
# claude config
$cc='';if(Test-Path "$env:USERPROFILE\.claude.json"){$cj=Get-Content "$env:USERPROFILE\.claude.json" -Raw|ConvertFrom-Json -EA SilentlyContinue
if($cj){$cc="hasOAuth=$([bool]$cj.oauthAccount); primaryModel=$($cj.primaryModel); mcpServers=$(@($cj.mcpServers.PSObject.Properties.Name) -join ',')"}}
# opencode config
$oc='';foreach($p in @("$env:USERPROFILE\.opencode.json","$env:USERPROFILE\.config\opencode\opencode.json")){
if(Test-Path $p){$oc="config at $p"; break}}
# versions
$ver=@()
try{$v=claude --version 2>$null;if($v){$ver+="claude=$v"}}catch{}
try{$v=opencode --version 2>$null;if($v){$ver+="opencode=$v"}}catch{}
try{$v=ollama --version 2>$null;if($v){$ver+="ollama=$v"}}catch{}
[pscustomobject]@{skill='agentstate';host=$hn;utc=$now;env_names=($found -join ';');claude_config=$cc;opencode_config=$oc;versions=(($ver|Select -First 8) -join ';')}|ConvertTo-Json -Compress -Depth 3