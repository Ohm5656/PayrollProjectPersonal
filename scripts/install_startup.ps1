param([string]$PythonPath = '', [string]$ProjectPath = (Split-Path -Parent $PSScriptRoot))
$ErrorActionPreference = 'Stop'
$taskName = 'NTP Payroll Assistant'
$project = (Resolve-Path -LiteralPath $ProjectPath).Path
if (-not (Test-Path -LiteralPath (Join-Path $project 'app\main.py'))) { throw 'Project entry point is missing' }
if (-not $PythonPath) {
    $venvPython = Join-Path $project '.venv\Scripts\pythonw.exe'
    if (Test-Path -LiteralPath $venvPython) { $PythonPath = $venvPython }
    else { $PythonPath = (Get-Command pythonw.exe -ErrorAction Stop).Source }
}
$python = (Resolve-Path -LiteralPath $PythonPath).Path
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $python -Argument '-X utf8 -m app.main --startup' -WorkingDirectory $project
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'NTP Payroll Assistant: copies-only user-session desktop app' -Force | Out-Null
Write-Host 'Installed per-user login task. It will start at the next login.'
