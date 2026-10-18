"""Current-user Windows Task Scheduler integration for tray-first startup.

The service never installs a task on construction.  The Settings dialog calls
``install`` or ``repair`` only after an explicit user action, and tests inject
an in-memory scheduler rather than touching Windows Task Scheduler.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import base64
import json
import os
from pathlib import Path
import subprocess

from app.safety import ROOT


class StartupState(StrEnum):
    VALID = 'VALID'
    NOT_INSTALLED = 'NOT_INSTALLED'
    NEEDS_REPAIR = 'NEEDS_REPAIR'
    INVALID_LAUNCH = 'INVALID_LAUNCH'
    UNAVAILABLE = 'UNAVAILABLE'
    ERROR = 'ERROR'


class StartupError(RuntimeError):
    pass


class StartupUnavailable(StartupError):
    pass


@dataclass(frozen=True)
class StartupDefinition:
    task_name: str
    executable: str
    arguments: str
    working_directory: str


@dataclass(frozen=True)
class StartupStatus:
    state: StartupState
    message: str
    expected: StartupDefinition | None = None
    actual: dict | None = None
    mismatches: tuple[str, ...] = ()

    @property
    def enabled(self):
        return self.state == StartupState.VALID

    @property
    def installed(self):
        return self.state in {StartupState.VALID, StartupState.NEEDS_REPAIR}


@dataclass(frozen=True)
class StartupResult:
    success: bool
    status: StartupStatus
    changed: bool = False


class PowerShellTaskScheduler:
    """Small, argument-safe adapter around Windows ScheduledTasks cmdlets."""
    def _invoke(self, script):
        encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                 '-EncodedCommand', encoded],
                capture_output=True, text=True, encoding='utf-8', errors='replace', check=False,
            )
        except OSError as exc:
            raise StartupUnavailable('Windows Task Scheduler is unavailable') from exc
        if result.returncode:
            detail = (result.stderr or result.stdout or 'Task Scheduler command failed').strip()
            raise StartupError(detail)
        return result.stdout.strip()

    @staticmethod
    def _payload(value):
        return base64.b64encode(json.dumps(value, ensure_ascii=False).encode('utf-8')).decode('ascii')

    def query(self, task_name):
        name = self._payload({'task_name': task_name})
        output = self._invoke(f"""
$value = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{name}')) | ConvertFrom-Json
$task = Get-ScheduledTask -TaskName $value.task_name -ErrorAction SilentlyContinue
if ($null -eq $task) {{ exit 0 }}
$action = @($task.Actions)[0]
$hasLogon = @($task.Triggers | Where-Object {{ $_.CimClass.CimClassName -match 'Logon' }}).Count -gt 0
[pscustomobject]@{{
 task_name=[string]$task.TaskName; executable=[string]$action.Execute; arguments=[string]$action.Arguments;
 working_directory=[string]$action.WorkingDirectory; enabled=($task.Settings.Enabled -ne $false);
 logon=$hasLogon; user_id=[string]$task.Principal.UserId; logon_type=[string]$task.Principal.LogonType;
 run_level=[string]$task.Principal.RunLevel
}} | ConvertTo-Json -Compress
""")
        return json.loads(output) if output else None

    def install(self, definition):
        payload = self._payload(definition.__dict__)
        self._invoke(f"""
$value = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}')) | ConvertFrom-Json
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction -Execute $value.executable -Argument $value.arguments -WorkingDirectory $value.working_directory
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero)
Register-ScheduledTask -TaskName $value.task_name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'NTP Payroll Assistant: copies-only user-session desktop app' -Force | Out-Null
""")

    def remove(self, task_name):
        payload = self._payload({'task_name': task_name})
        self._invoke(f"""
$value = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}')) | ConvertFrom-Json
$task = Get-ScheduledTask -TaskName $value.task_name -ErrorAction SilentlyContinue
if ($null -ne $task) {{ Unregister-ScheduledTask -TaskName $value.task_name -Confirm:$false }}
""")


class WindowsStartupService:
    """Validate, install, repair and remove one owned current-user logon task."""
    TASK_NAME = 'NTP Payroll Assistant'
    ARGUMENTS = '-X utf8 -m app.main --startup'

    def __init__(self, *, project_root=None, executable=None, scheduler=None, platform=None):
        self.project_root = Path(project_root or ROOT).resolve()
        self.executable = Path(executable).resolve() if executable else None
        self.scheduler = scheduler or PowerShellTaskScheduler()
        self.platform = platform or os.name

    def definition(self):
        if self.platform != 'nt':
            raise StartupUnavailable('Windows startup is available only on Windows')
        project = self.project_root
        entry = project / 'app' / 'main.py'
        executable = self.executable or project / '.venv' / 'Scripts' / 'pythonw.exe'
        if not project.is_dir():
            raise StartupError('Project folder is no longer available')
        if not entry.is_file():
            raise StartupError('Application entry point is missing')
        if not executable.is_file():
            raise StartupError('The windowless Python executable is missing')
        return StartupDefinition(self.TASK_NAME, str(executable), self.ARGUMENTS, str(project))

    def validate(self):
        try:
            expected = self.definition()
        except StartupUnavailable as exc:
            return StartupStatus(StartupState.UNAVAILABLE, str(exc))
        except StartupError as exc:
            return StartupStatus(StartupState.INVALID_LAUNCH, str(exc))
        try:
            actual = self.scheduler.query(expected.task_name)
        except StartupUnavailable as exc:
            return StartupStatus(StartupState.UNAVAILABLE, str(exc), expected)
        except StartupError:
            return StartupStatus(StartupState.ERROR, 'Unable to check the Windows startup task', expected)
        if actual is None:
            return StartupStatus(StartupState.NOT_INSTALLED, 'Startup is off', expected)
        mismatches = self._mismatches(expected, actual)
        if mismatches:
            return StartupStatus(StartupState.NEEDS_REPAIR, 'Startup task needs repair', expected, actual, tuple(mismatches))
        return StartupStatus(StartupState.VALID, 'Startup is enabled', expected, actual)

    @staticmethod
    def _same_path(left, right):
        return str(left or '').replace('/', '\\').casefold() == str(right or '').replace('/', '\\').casefold()

    def _mismatches(self, expected, actual):
        checks = {
            'executable': self._same_path(actual.get('executable'), expected.executable),
            'arguments': str(actual.get('arguments') or '').strip() == expected.arguments,
            'working_directory': self._same_path(actual.get('working_directory'), expected.working_directory),
            'logon_trigger': bool(actual.get('logon')),
            'interactive_user': str(actual.get('logon_type') or '').casefold() == 'interactive',
            'limited_privilege': str(actual.get('run_level') or '').casefold() == 'limited',
            'enabled': bool(actual.get('enabled')),
        }
        return [name for name, matches in checks.items() if not matches]

    def is_startup_enabled(self):
        return self.validate().enabled

    def install(self):
        status = self.validate()
        if status.state == StartupState.VALID:
            return StartupResult(True, status, False)
        if status.state == StartupState.NEEDS_REPAIR:
            return StartupResult(False, status, False)
        if status.state not in {StartupState.NOT_INSTALLED}:
            return StartupResult(False, status, False)
        try:
            self.scheduler.install(status.expected)
        except StartupError:
            return StartupResult(False, StartupStatus(StartupState.ERROR,
                'Unable to enable Start with Windows. Check Windows permissions and try again.', status.expected), False)
        verified = self.validate()
        return StartupResult(verified.state == StartupState.VALID, verified, True)

    def repair(self):
        status = self.validate()
        if status.state == StartupState.VALID:
            return StartupResult(True, status, False)
        if status.expected is None:
            return StartupResult(False, status, False)
        try:
            self.scheduler.install(status.expected)
        except StartupError:
            return StartupResult(False, StartupStatus(StartupState.ERROR,
                'Unable to repair Start with Windows. Check Windows permissions and try again.', status.expected), False)
        verified = self.validate()
        return StartupResult(verified.state == StartupState.VALID, verified, True)

    def remove(self):
        status = self.validate()
        if status.state == StartupState.NOT_INSTALLED:
            return StartupResult(True, status, False)
        if status.expected is None:
            return StartupResult(False, status, False)
        try:
            self.scheduler.remove(status.expected.task_name)
        except StartupError:
            return StartupResult(False, StartupStatus(StartupState.ERROR,
                'Unable to disable Start with Windows. Check Windows permissions and try again.', status.expected), False)
        verified = self.validate()
        return StartupResult(verified.state == StartupState.NOT_INSTALLED, verified, True)
