# delete_task.verify — confirm the task is gone. Engine injects $Target.
if (-not (Get-ScheduledTask -TaskName $Target -ErrorAction SilentlyContinue)) { 'VERIFIED' } else { 'NOT_VERIFIED' }
