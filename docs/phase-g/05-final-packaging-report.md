# Phase G Final Packaging Report

## Candidate artifact

The reproducible PyInstaller onedir build completed on Windows 11
10.0.26200 using Python 3.14.3, PyInstaller 6.22.3 and PySide6 6.12.0.

| Item | Value |
| --- | --- |
| Label | NTP Payroll Assistant - Test Candidate |
| EXE | `dist/build-fadcfcd335fa46d69208f5e232a3c7fd/NTP Payroll Assistant - Test Candidate/NTP Payroll Assistant - Test Candidate.exe` |
| Size | 51,466,927 bytes |
| SHA-256 | `2186A3F37A9A8C5F9A57AFD682B824948DD3DA9C6F3AE35088D3E182992CED40` |
| Build source revision | G.6 working tree (documentation follows) |
| Signature | unsigned |
| Excel requirement | Microsoft Excel Desktop remains external for COM |

The EXE is intentionally absent from Git. It is a QA-only candidate: frozen
launch forces `--qa-ui`, and data/logs/SQLite/IPC remain in the fixed validated
`%LOCALAPPDATA%/NTP Payroll Assistant Test Candidate/State/test_workspace`
instead of the application directory. No normal payroll or reference-data
fallback is available.

## Installer

The per-user Inno Setup definition is present at
`packaging/installer/ntp_payroll.iss`. `ISCC.exe` was unavailable, so there
is **no installer artifact, size, SHA-256, compile result or installation
evidence**. The script is intentionally lowest-privilege and has no automatic
launch, monitoring, Windows startup registration or data import.

## Validation status

| Level | Result |
| --- | --- |
| Source focused packaging/safety/UI checks | PASS (11 tests) |
| Frozen executable QA smoke | PASS (exit code 0) |
| Qt SVG asset inclusion | PASS |
| Native Windows UI/tray/keyboard | NOT VERIFIED |
| Packaged Excel COM | NOT VERIFIED |
| Installer build/execution/upgrade/uninstall | BLOCKED / NOT VERIFIED |
| Production authorization | NOT GRANTED |

See `04-packaging-qa-report.md` and the Thai acceptance playbook for precise
manual acceptance steps. Candidate artifacts are suitable for controlled
operator review only after the deferred checks are completed.

## Go / no-go

**PACKAGING CODE COMPLETE: YES.** Reproducible EXE source/build configuration,
candidate sandbox and installer definition are versioned.

**READY FOR FINAL ACCEPTANCE: YES.** The generated QA-only EXE can be presented
for controlled manual review; installer and native checks remain explicit gates.

**READY FOR PRODUCTION: NO.** Business-owner acceptance and every applicable
acceptance-register gate remain required.
