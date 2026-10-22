# Phase G Final Packaging Report

## Candidate artifact

The reproducible PyInstaller onedir build completed on Windows 11
10.0.26200 using Python 3.14.3, PyInstaller 6.22.3 and PySide6 6.12.0.

| Item | Value |
| --- | --- |
| Label | NTP Payroll Assistant - Test Candidate |
| EXE | `dist/build-6c5c459ccfac4d498ad85c6c517a46e9/NTP Payroll Assistant - Test Candidate/NTP Payroll Assistant - Test Candidate.exe` |
| Size | 51,466,805 bytes |
| SHA-256 | `255E2C50FA04F8CD4802034489F80326C46A1AB10C9C5293BA95C8DF9BA69C2B` |
| Build source revision | G.6 working tree (documentation follows) |
| Signature | unsigned |
| Excel requirement | Microsoft Excel Desktop remains external for COM |

The EXE is intentionally absent from Git. It is a QA-only candidate: frozen
launch forces `--qa-ui`, and data/logs/SQLite/IPC remain in the fixed validated
`%LOCALAPPDATA%/NTP Payroll Assistant Test Candidate/State/test_workspace`
instead of the application directory. No normal payroll or reference-data
fallback is available.

## Installer

The per-user Inno Setup definition compiled with Inno Setup 6.7.3. The unsigned
installer is `artifacts/NTP-Payroll-Assistant-Test-Candidate-Setup.exe`
(87,796,196 bytes; SHA-256
`D7C8C8E87B0D8FCBFE59737026A3AFA4B16D31AD3C6E56787500DF2C1C74A8DB`). It
has not been installed or uninstalled. The script is intentionally
lowest-privilege and has no automatic launch, monitoring, Windows startup
registration or data import.

## Validation status

| Level | Result |
| --- | --- |
| Source focused packaging/safety/UI checks | PASS (11 tests) |
| Frozen executable QA smoke | BLOCKED (Windows Application Control policy) |
| Qt SVG asset inclusion | PASS |
| Native Windows UI/tray/keyboard | NOT VERIFIED |
| Packaged Excel COM | NOT VERIFIED |
| Installer build/execution/upgrade/uninstall | PASS / NOT VERIFIED |
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
