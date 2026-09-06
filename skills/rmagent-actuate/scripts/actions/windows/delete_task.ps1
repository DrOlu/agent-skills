# delete_task - delete a scheduled task, snapshotting its full XML to output first.
# The XML is captured in the journal's result_detail so the task can be
# recreated (undo: recreate_task, Rev 17 M3).
# Engine injects $Target (task name).
# REV 17 (C4): Stop + observe.
$ErrorActionPreference = 'Stop'
try {
  $t = Get-ScheduledTask -TaskName $Target -ErrorAction SilentlyContinue
  if (-not $t) {
    [pscustomobject]@{ action='delete_task'; task=$Target; status='not-found' } | ConvertTo-Json -Compress
  } else {
    $xml = Export-ScheduledTask -TaskName $Target -ErrorAction Stop
    Unregister-ScheduledTask -TaskName $Target -Confirm:$false -ErrorAction Stop
    $gone = -not (Get-ScheduledTask -TaskName $Target -ErrorAction SilentlyContinue)
    [pscustomobject]@{ action='delete_task'; task=$Target; status= if($gone){'deleted'}else{'failed'}; task_xml=$xml } | ConvertTo-Json -Compress -Depth 3
  }
} catch {
  [pscustomobject]@{ok=$false; action='delete_task'; task=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
