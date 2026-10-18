$ErrorActionPreference = 'Stop'
$taskName = 'NTP Payroll Assistant'
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($task) { Unregister-ScheduledTask -TaskName $taskName -Confirm:$false }
Write-Host 'Removed login task. Running applications and Excel workbooks were left open.'
