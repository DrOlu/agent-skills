# taskaudit — non-Microsoft scheduled tasks with dangling-target detection.
# Read-only, capped. ONE JSON. Formalizes the 2026-09-28 finding of the
# ConfigurationChangeMonitor task whose C:\Windows\Temp script was deleted:
# every task's action targets are existence-checked; a task pointing at a
# missing file is flagged dangling (inert persistence residue).
# Engine injects: $ErrorActionPreference; $Track; $SinceHours; $Limit
$ErrorActionPreference='SilentlyContinue'
$rows = @()
$tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object { $_.TaskPath -notlike '\Microsoft*' } |
  Select-Object -First $Limit)
foreach ($t in $tasks) {
  $act = @($t.Actions | Select-Object -First 2 | ForEach-Object {
    $s = "$($_.Execute) $($_.Arguments)"
    $s.Substring(0, [Math]::Min(120, $s.Length))
  })
  $missing = @()
  foreach ($a in $t.Actions) {
    if ($a.Execute) {
      $exe = $a.Execute.Trim('"')
      if ($exe -match '^[A-Za-z]:\\' -and -not (Test-Path $exe)) { $missing += $exe }
    }
    if ($a.Arguments -match '([A-Za-z]:\\[^\s"]+\.(ps1|bat|cmd|exe))') {
      $f = $Matches[1].Trim('"')
      if (-not (Test-Path $f)) { $missing += $f }
    }
  }
  $i = Get-ScheduledTaskInfo -TaskName $t.TaskName -TaskPath $t.TaskPath -ErrorAction SilentlyContinue
  $rows += [pscustomobject]@{
    task="$($t.TaskPath)$($t.TaskName)"; state=[string]$t.State
    user=$t.Principal.UserId; actions=$act
    last_run= if($i -and $i.LastRunTime){$i.LastRunTime.ToString('s')}else{''}
    last_result= if($i){$i.LastTaskResult}else{$null}
    dangling=($missing.Count -gt 0); missing_targets=@($missing | Select-Object -First 3)
  }
}
[pscustomobject]@{
  skill='taskaudit'; host=$env:COMPUTERNAME; utc=[DateTime]::UtcNow.ToString('o')
  scanned=@($tasks).Count; dangling_count=@($rows | Where-Object {$_.dangling}).Count
  rows=@($rows)
}|ConvertTo-Json -Compress -Depth 5
