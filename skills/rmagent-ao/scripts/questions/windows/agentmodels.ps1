# agentmodels — query local model servers on Windows through their own APIs.
# Ollama /api/tags + /api/ps, LM Studio /v1/models, vLLM /v1/models.
# Read-only GETs, capped. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
$ollamaInstalled=""; $ollamaRunning=""
try{$r=Invoke-RestMethod -Uri 'http://localhost:11434/api/tags' -TimeoutSec 3 -EA SilentlyContinue
if($r -and $r.models){$ollamaInstalled=($r.models|%{$_.name}) -join ';'}
$r2=Invoke-RestMethod -Uri 'http://localhost:11434/api/ps' -TimeoutSec 3 -EA SilentlyContinue
if($r2 -and $r2.models){$ollamaRunning=($r2.models|%{$_.name}) -join ';'}}catch{}
$lmstudio=""
try{$r=Invoke-RestMethod -Uri 'http://localhost:1234/v1/models' -TimeoutSec 3 -EA SilentlyContinue
if($r -and $r.data){$lmstudio=($r.data|%{$_.id}) -join ';'}}catch{}
$vllm=""
try{$r=Invoke-RestMethod -Uri 'http://localhost:8000/v1/models' -TimeoutSec 3 -EA SilentlyContinue
if($r -and $r.data){$vllm=($r.data|%{$_.id}) -join ';'}}catch{}
$other=""
foreach($p in @(8080,5000,9997)){
try{$r=Invoke-RestMethod -Uri "http://localhost:$p/v1/models" -TimeoutSec 2 -EA SilentlyContinue
if($r -and $r.data){$other+="port-$p-openai-compatible;"}}catch{}}
[pscustomobject]@{skill='agentmodels';host=$hn;utc=$now;ollama_installed=$ollamaInstalled;ollama_running=$ollamaRunning;lmstudio=$lmstudio;vllm=$vllm;other=$other}|ConvertTo-Json -Compress