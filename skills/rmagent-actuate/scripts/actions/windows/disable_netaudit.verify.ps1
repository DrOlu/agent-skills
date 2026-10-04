# disable_netaudit.verify - confirm both subcategories show no Success.
$fpc='{0CCE9225-69AE-11D9-BED3-505054503030}'
$fppd='{0CCE9226-69AE-11D9-BED3-505054503030}'
$r1 = (auditpol /get /subcategory:$fpc /r | Out-String) -match 'Success'
$r2 = (auditpol /get /subcategory:$fppd /r | Out-String) -match 'Success'
if (-not ($r1 -or $r2)) { 'VERIFIED' } else { 'NOT_VERIFIED' }
