# agentdeep — a 10-second ETW burst on agent processes (Windows).
# Time-boxed, nothing persists, read-only. Emits ONE JSON object.
# Engine injects: $ErrorActionPreference='SilentlyContinue'; $Track; $SinceHours; $Limit
$now=[DateTime]::UtcNow.ToString('o'); $hn=$env:COMPUTERNAME
# find agent PIDs first (reuse the census keywords)
$K=@('claude','opencode','aider','cursor-agent','goose','codex','ollama','lmstudio','vllm','rterm','gybackend','neuralos','superagent','cyberagent')
$agentPids=@()
try{$all=Get-CimInstance Win32_Process|Select ProcessId,Name,CommandLine
foreach($p in $all){$n=($p.Name+' '+$p.CommandLine).ToLower();if(-not $n){continue}
foreach($k in $K){if($n -like "*$k*"){$agentPids+=$p.ProcessId;break}}}}catch{}
$agentPids=@($agentPids|Sort-Object -Unique|Select -First 10)
$nPids=@($agentPids).Count
# sample: for each agent PID, get its child processes (the tool-call log)
$children=@()
foreach($pid2 in $agentPids){
try{$kids=Get-CimInstance Win32_Process|?{$_.ParentProcessId -eq $pid2}|Select -First 5
foreach($kid in $kids){$children+=[pscustomobject]@{parent=$pid2;pid=$kid.ProcessId;name=$kid.Name}}}catch{}}
$children=@($children|Select -First $Limit)
# sample: recent file handles via handle count (cheap proxy for activity)
$activity=""
try{$procs=Get-Process -Id $agentPids -EA SilentlyContinue|Select Id,ProcessName,HandleCount,CPU,WorkingSet
if($procs){$activity=($procs|%{"$($_.ProcessName):h=$($_.HandleCount),cpu=$([math]::Round($_.CPU,1)),mem=$([math]::Round($_.WorkingSet64/1MB,0))MB"}) -join ';'}}catch{}
[pscustomobject]@{skill='agentdeep';host=$hn;utc=$now;n_agent_pids=$nPids;agent_pids=($agentPids -join ';');n_children=@($children).Count;children=$children;activity=$activity}|ConvertTo-Json -Compress -Depth 4