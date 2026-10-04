# disable_audit.verify - confirm Directory Service Changes auditing is off.
$rep = (auditpol /get /subcategory:'{0CCE923F-69AE-11D9-BED3-505054503030}' /r) | Out-String
if ($rep -notmatch 'Success') { 'VERIFIED' } else { 'NOT_VERIFIED' }
