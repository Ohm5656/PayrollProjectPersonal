# Packaging QA Report

## Scope and environment

This report covers only the **NTP Payroll Assistant - Test Candidate**. It
uses Python 3.14.3, PyInstaller 6.22.3, PySide6 6.12.0 and Windows 11
10.0.26200. PyInstaller was installed only in the project `.venv`. Inno Setup
(`ISCC.exe`) is not installed, so no installer was compiled.

## Executable result

`packaging/build_exe.ps1` produced an onedir candidate and verified its EXE
with SHA-256. The candidate was launched with `--smoke-test`; it exited with
code 0 and created state only under:

```text
dist/NTP Payroll Assistant - Test Candidate/test_workspace/qa_sessions/manual_ui/
```

The frozen entry point injects `--qa-ui`; `app.main` rejects a frozen launch
without it. This prevents fallback to the normal application database or
reference-workbook startup path. Its test workspace is a descendant of the
candidate executable directory and continues to be checked by
`development_target()`.

## Results

| Check | Result | Evidence / limit |
| --- | --- | --- |
| PyInstaller onedir build | PASS | `build_exe.ps1`, PyInstaller 6.22.3 |
| Frozen QA smoke launch | PASS | `--smoke-test` exited 0 |
| Candidate sandbox boundary | PASS | frozen QA entry and source regression tests |
| `checkmark.svg` resource | PASS | explicitly packaged and resolved beside `theme.py` |
| Normal database/reference data access | PASS | frozen execution requires QA mode; no reference data is bundled |
| Monitoring / Scheduled Task changes | PASS | QA runtime and inert startup service only; no task command run |
| Native five-page UI, tray and keyboard | NOT VERIFIED | smoke mode is non-interactive |
| Packaged Excel COM | NOT VERIFIED | no isolated native Excel rehearsal was run |
| Inno Setup compile | BLOCKED | `ISCC.exe` unavailable |
| Installer execution, upgrade, uninstall | NOT VERIFIED | no installer exists and no installation was performed |

No existing application process, normal/QA project database, reference
workbook, Windows Scheduled Task or user-owned Excel process was opened or
changed for this packaging check. The generated `build/` and `dist/`
directories are Git-ignored and were not staged.
