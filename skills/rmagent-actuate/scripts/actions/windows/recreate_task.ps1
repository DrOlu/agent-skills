# recreate_task — undo for delete_task (Rev 17, M3; Rev 20 target contract).
#
# delete_task snapshots the task's full XML into the journal (result_detail.
# task_xml) before deleting. This payload recreates that task from its XML.
#
# REV 20: the engine's undo path now passes $Target as a JSON document
# {"task": "<name>", "xml": "<full task xml>"} when the XML is available
# (plain task name still accepted for backwards compatibility). If the XML
# is missing this reports what is needed — it never silently pretends
# to succeed.
$ErrorActionPreference = 'Stop'
try {
  $taskName = $Target
  $taskXml = ''
  if ($Target -and $Target.Trim().StartsWith('{')) {
    $doc = $Target | ConvertFrom-Json
    $taskName = [string]$doc.task
    $taskXml = [string]$doc.xml
  }
  if (-not $taskXml -or $taskXml.Trim().Length -eq 0) {
    [pscustomobject]@{ok=$false; action='recreate_task'; task=$taskName;
                       error='no task XML provided — copy task_xml from the delete_task journal entry'} | ConvertTo-Json -Compress
    return
  }
  Register-ScheduledTask -TaskName $taskName -Xml $taskXml -ErrorAction Stop | Out-Null
  $t = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
  [pscustomobject]@{ok=$true; action='recreate_task'; task=$taskName;
                    status= if($t){'recreated'}else{'failed'} } | ConvertTo-Json -Compress
} catch {
  [pscustomobject]@{ok=$false; action='recreate_task'; task=$Target; error="$($_.Exception.Message)"} | ConvertTo-Json -Compress
}
