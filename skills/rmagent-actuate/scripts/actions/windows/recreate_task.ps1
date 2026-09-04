# recreate_task — undo for delete_task (Rev 17, M3).
#
# delete_task snapshots the task's full XML into the journal (result_detail.
# task_xml) before deleting. This payload recreates that task from its XML.
# The engine passes $Target = the task NAME and (when the undo path knows it)
# $TaskXml = the journaled XML. If $TaskXml is empty, this reports what is
# needed so the operator can do it manually from the journal — never
# silently pretends to succeed.
$ErrorActionPreference = 'Stop'
try {
  if (-not $TaskXml -or $TaskXml.Trim().Length -eq 0) {
    [pscustomobject]@{ok=$false; action='recreate_task'; task=$Target;
                       error='no task XML provided — copy task_xml from the delete_task journal entry and pass it via -TaskXml'} | ConvertTo-Json -Compress
    return
  }
  Register-ScheduledTask -TaskName $Target -Xml $TaskXml -ErrorAction Stop | Out-Null
  $t = Get-ScheduledTask -TaskName $Target -ErrorAction SilentlyContinue
  [pscustomobject]@{ok=$true; action='recreate_task'; task=$Target;
                    status= if($t){'recreated'}else{'failed'} } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ok=$false; action='recreate_task'; task=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
