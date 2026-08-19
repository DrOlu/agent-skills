# delete_task — delete a scheduled task, snapshotting its full XML to output first.
# The XML is captured in the journal's result_detail so the task can be recreated.
# Engine injects $Target (task name).
$t = Get-ScheduledTask -TaskName $Target -ErrorAction SilentlyContinue
if (-not $t) {
  [pscustomobject]@{ action='delete_task'; task=$Target; status='not-found' } | ConvertTo-Json -Compress
} else {
  $xml = Export-ScheduledTask -TaskName $Target -ErrorAction SilentlyContinue
  Unregister-ScheduledTask -TaskName $Target -Confirm:$false -ErrorAction SilentlyContinue
  $gone = -not (Get-ScheduledTask -TaskName $Target -ErrorAction SilentlyContinue)
  [pscustomobject]@{ action='delete_task'; task=$Target; status= if($gone){'deleted'}else{'failed' }; task_xml=$xml } | ConvertTo-Json -Compress -Depth 3
}
