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
| Candidate EXE | `dist/build-6c5c459ccfac4d498ad85c6c517a46e9/NTP Payroll Assistant - Test Candidate/NTP Payroll Assistant - Test Candidate.exe` |
| EXE size / SHA-256 | 51,466,805 bytes / `255E2C50FA04F8CD4802034489F80326C46A1AB10C9C5293BA95C8DF9BA69C2B` |
| Frozen QA smoke | BLOCKED; Windows Application Control policy blocked the unsigned EXE before launch |
| Candidate persistent state | PASS; `%LOCALAPPDATA%/.../State/test_workspace` |
| Installer staging | PASS; 228 allowlisted files, manifest `build/installer-manifests/667da7cfa59b49a0b813d1797906cf79.json` |
| Prohibited payload data | PASS; no runtime workspace, DB, log, backup, XLS/XLSX or reference path in manifest |
| Packaged pywin32 | build hooks for `pythoncom`, `pywintypes`, `win32com` included; packaged COM execution remains NOT VERIFIED |

## Installer result

Inno Setup 6.7.3 was found at `%LOCALAPPDATA%/Programs/Inno Setup 6/ISCC.exe`.
The compiler rebuilt the EXE, staged 228 allowlisted files and successfully
compiled the unsigned installer below. Compiler output listed only the verified
staging payload; no payload extractor was present, so binary extraction was
not an additional validation method.

| Item | Value |
| --- | --- |
| Installer | `artifacts/NTP-Payroll-Assistant-Test-Candidate-Setup.exe` |
| Size | 87,796,196 bytes |
| SHA-256 | `D7C8C8E87B0D8FCBFE59737026A3AFA4B16D31AD3C6E56787500DF2C1C74A8DB` |
| Signature | NotSigned |
| Install/uninstall | NOT VERIFIED; no installer was executed |

The `.iss` definition is per-user, unsigned, QA-labelled, has a Start Menu
shortcut plus optional Desktop shortcut, and deliberately has no `[Run]`
action, startup task, monitoring activation or uninstall-delete rule.

## Remaining gates

Perform installation/upgrade/uninstall only in an explicitly approved
disposable Windows environment. Windows Application Control blocked the fresh
unsigned EXE on this machine, so frozen runtime, native UI/tray/DPI and
packaged Excel COM remain unverified. Clean-machine compatibility, signing
decision and all business-owner payroll acceptance remain deferred. Production
authorization remains not granted.
