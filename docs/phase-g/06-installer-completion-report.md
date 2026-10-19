# Phase G.6 Installer Completion Report

## Completed safety engineering

The frozen QA candidate now keeps all mutable synthetic state beneath the
fixed path `%LOCALAPPDATA%/NTP Payroll Assistant Test Candidate/State/test_workspace`.
It is separate from the per-user installed application directory
`%LOCALAPPDATA%/Programs/NTP Payroll Assistant Test Candidate`. Source-mode
paths are unchanged. Frozen execution still requires QA mode and all writes
pass the existing `development_target()` boundary.

`app.packaging_safety` prepares a fresh UUID-named installer staging directory.
It copies only the candidate EXE and `_internal` directory, rejects links,
runtime state, databases, logs, backups, workbooks and reference/report paths,
then writes a SHA-256 manifest outside the payload. Existing output directories
are never overwritten. This is independent of Git ignore rules.

## Build evidence

| Item | Result |
| --- | --- |
| Windows | 11 10.0.26200 |
| Python / PyInstaller / PySide6 | 3.14.3 / 6.22.3 / 6.12.0 |
| Candidate EXE | `dist/build-fadcfcd335fa46d69208f5e232a3c7fd/NTP Payroll Assistant - Test Candidate/NTP Payroll Assistant - Test Candidate.exe` |
| EXE size / SHA-256 | 51,466,927 bytes / `2186A3F37A9A8C5F9A57AFD682B824948DD3DA9C6F3AE35088D3E182992CED40` |
| Frozen QA smoke | PASS; exited 0 |
| Candidate persistent state | PASS; `%LOCALAPPDATA%/.../State/test_workspace` |
| Installer staging | PASS; 228 allowlisted files, manifest `build/installer-manifests/bb88db84e376447db8b45da2c4c11ab7.json` |
| Prohibited payload data | PASS; no runtime workspace, DB, log, backup, XLS/XLSX or reference path in manifest |
| Packaged pywin32 | build hooks for `pythoncom`, `pywintypes`, `win32com` included; packaged COM execution remains NOT VERIFIED |

## Installer result

`ISCC.exe` was not found on PATH or in the standard Inno Setup locations. The
reproducible `build_installer.ps1` fails closed with an explicit message and
does not build, download or install software. Therefore there is no installer
artifact, compiler version, installer hash, install/uninstall execution,
upgrade rehearsal or packaged COM execution evidence.

The `.iss` definition is per-user, unsigned, QA-labelled, has a Start Menu
shortcut plus optional Desktop shortcut, and deliberately has no `[Run]`
action, startup task, monitoring activation or uninstall-delete rule.

## Remaining gates

Install Inno Setup only with explicit approval, then run
`packaging/build_installer.ps1` and perform installation/upgrade/uninstall in
a disposable Windows environment. Native UI/tray/DPI, packaged Excel COM,
clean-machine compatibility, signing decision and all business-owner payroll
acceptance remain deferred. Production authorization remains not granted.
