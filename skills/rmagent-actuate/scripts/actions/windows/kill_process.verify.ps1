# kill_process.verify — confirm the PID is gone. Engine injects $Target.
if (-not (Get-CimInstance Win32_Process -Filter "ProcessId=$Target" -ErrorAction SilentlyContinue)) { 'VERIFIED' } else { 'NOT_VERIFIED' }
