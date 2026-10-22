# Final Acceptance Register

| Area | Status | Required evidence |
| --- | --- | --- |
| Phase D native pages/tray/focus/DPI | DEFERRED | real manual Windows QA |
| Phase D sign-in startup | DEFERRED | explicit authorization; not part of test candidate |
| Phase E business salary/OT/leave/bonus/deduction rules | PENDING | payroll-owner approval |
| Phase E real-data copy-only UAT | DEFERRED | separate permission and approved copies |
| Phase E native Excel recovery | DEFERRED | approved synthetic native-Excel rehearsal |
| Phase F operator restore/configuration review | PENDING | operator rehearsal/sign-off |
| Phase F backup ownership/retention and final risk review | PENDING | owner-approved operational policy |
| Phase G frozen EXE native UI/tray/keyboard/DPI | BLOCKED | Windows Application Control blocked the unsigned fresh EXE; require approved signing/policy decision before manual QA |
| Phase G installer compile | PASS | Inno Setup 6.7.3; staged allowlist and unsigned artifact SHA-256 recorded |
| Phase G installer install/upgrade/uninstall | DEFERRED | explicitly approved disposable installation rehearsal |
| Phase G candidate data retention | DEFERRED | inspect that uninstall preserves `%LOCALAPPDATA%` candidate state in a disposable installation |
| Phase G packaged Excel COM | DEFERRED | isolated fictional workbook and owned Excel process |
| Phase G clean-machine compatibility | DEFERRED | Windows test machine without project Python |
| Phase G code signing/security warnings | PENDING | verified signing decision; current candidate is unsigned |
| Production activation | NOT_VERIFIED | every applicable gate plus explicit business-owner authorization |
