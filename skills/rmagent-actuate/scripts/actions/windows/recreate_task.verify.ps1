# verify: recreate_task — the task must exist again.
if (Get-ScheduledTask -TaskName $Target -ErrorAction SilentlyContinue) { 'VERIFIED' } else { 'NOT_VERIFIED' }
