# NTP Payroll Assistant

A Windows desktop application for reviewing payroll workbooks and preparing changes on test copies.

## Tech Stack

<p align="left">
  <img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/PySide6-41CD52?style=flat-square&logo=qt&logoColor=white" alt="PySide6" />
  <img src="https://img.shields.io/badge/SQLite-003B57?style=flat-square&logo=sqlite&logoColor=white" alt="SQLite" />
  <img src="https://img.shields.io/badge/openpyxl-217346?style=flat-square&logo=microsoftexcel&logoColor=white" alt="openpyxl" />
  <img src="https://img.shields.io/badge/Excel_COM-217346?style=flat-square&logo=microsoftexcel&logoColor=white" alt="Microsoft Excel COM via pywin32" />
  <img src="https://img.shields.io/badge/watchdog-555555?style=flat-square" alt="watchdog" />
  <img src="https://img.shields.io/badge/pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white" alt="pytest" />
  <img src="https://img.shields.io/badge/PowerShell-5391FE?style=flat-square&logo=powershell&logoColor=white" alt="PowerShell" />
</p>

## Project Structure

- `app/ui` — desktop interface and system tray
- `app/services` — application and payroll workflows
- `app/domain.py` and `app/models.py` — domain logic and data models
- `app/db` — SQLite database, migrations, and repositories
- `app/excel` — workbook reading, validation, and writing
- `tests` — unit and integration tests
- `scripts` — optional Windows startup setup

## Requirements

- Windows
- Python
- Microsoft Excel for Excel COM automation

## Setup

```powershell
python -m pip install -r requirements.txt
python -m app.main
```

Alternatively, launch the application with `Start NTP Payroll.cmd`.

## Tests

```powershell
python -X utf8 -m pytest -q
python -X utf8 -m app.main --smoke-test
```

Excel integration tests require Microsoft Excel and use test-workspace copies. The application is configured for copies-only workflows; do not use it to modify production payroll files.

## Windows test-candidate build

The deployment candidate is an onedir **QA-only** executable. It never starts
normal payroll mode: its frozen entry point always requests `--qa-ui`, creates
synthetic data in its own `test_workspace`, and leaves monitoring disabled.
It is not a production release.

```powershell
Set-Location 'C:\path\to\NTP payroll'
& '.\.venv\Scripts\python.exe' -m pip install 'pyinstaller>=6.16,<7'
& '.\packaging\build_exe.ps1'
```

The build script creates a fresh `dist\build-<id>` directory and prints its
exact EXE path and SHA-256; it never overwrites a prior candidate directory.
Launch the reported EXE. Generated `build/`, `dist/` and `artifacts/` folders
are intentionally ignored by Git. Microsoft Excel
Desktop remains an external prerequisite for real COM operations; packaged COM
must be verified separately against fictional workbooks only.

`packaging/installer/ntp_payroll.iss` is a per-user, unsigned Inno Setup
definition. `build_installer.ps1` first stages only the allowlisted EXE and
`_internal` payload, then requires Inno Setup. Compile it only after installing
Inno Setup with explicit approval, and do not execute an installer outside an
approved disposable test environment. It neither launches the application nor
creates a Scheduled Task. Candidate state is preserved separately beneath
`%LOCALAPPDATA%\NTP Payroll Assistant Test Candidate\State`. No production
activation flag, configuration, data import or production writing exists.

## Windows sign-in startup (manual verification)

Windows startup is opt-in. In **Settings**, select **Start with Windows** and save; this creates one current-user Task Scheduler task named `NTP Payroll Assistant`. It launches the project virtual environment's absolute `pythonw.exe` path with `-X utf8 -m app.main --startup`, so no console window is expected.

Do not run these steps as part of automated testing. Perform them manually on a safe copies-only configuration:

1. Configure approved test-workspace folders and enable monitoring only if that is desired.
2. In Settings, enable Start with Windows and confirm the status reads enabled.
3. In PowerShell, inspect the task: `Get-ScheduledTask -TaskName 'NTP Payroll Assistant'`.
4. Check its action executable, arguments, working directory, logon trigger, Interactive logon type, and Limited run level in Task Scheduler.
5. Start it manually with `Start-ScheduledTask -TaskName 'NTP Payroll Assistant'`; confirm a tray icon appears, no main window appears, and no console appears.
6. Confirm the tray status reflects the persisted monitoring preference; open the main window manually from the tray if needed.
7. Exit from the tray. Verify the process ends while the Scheduled Task remains installed.
8. Sign out and sign in manually to verify the logon trigger. Do not force logoff/restart from the application.
9. Disable Start with Windows in Settings and confirm the task is removed. A broken task may be repaired explicitly with the Settings **Repair** button.
