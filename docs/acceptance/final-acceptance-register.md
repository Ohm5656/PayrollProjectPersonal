# Final Acceptance Register

| Area | Status | Required evidence |
| --- | --- | --- |
| Phase D source UI, period context and lifecycle | PASS (automated) | 331-test final suite; isolated native Qt rendering/navigation and synthetic period checks recorded in `03-automated-completion-report.md` |
| Phase D native pages/tray/focus/DPI | PARTIAL | native Windows Qt harness rendered all five pages at four sizes and controller tests passed; actual notification-area clicks, physical keyboard flow and monitor-DPI review remain manual |
| Phase D sign-in startup | DEFERRED | explicit authorization; not part of test candidate |
| Phase E synthetic payroll calculation UAT | PASS (technical) | isolated synthetic fixtures, Decimal assertions and source-level native COM tests |
| Phase E business salary/OT/leave/bonus/deduction rules | PENDING | payroll-owner approval |
| Phase E real-data copy-only UAT | DEFERRED | separate permission and approved copies |
| Phase E native Excel recovery | PASS (synthetic) | owned Excel COM instance and fresh synthetic workbooks only |
| Phase F safety, recovery and runtime reliability | PASS (automated) | isolated DB/workbook snapshots, path/hash gates, watcher/job regression coverage |
| Phase F operator restore/configuration review | PENDING | operator rehearsal/sign-off |
| Phase F backup ownership/retention and final risk review | PENDING | owner-approved operational policy |
| Phase G frozen EXE native UI/tray/keyboard/DPI | BLOCKED | Windows Application Control blocked the unsigned fresh EXE; require approved signing/policy decision before manual QA |
| Phase G installer compile | PASS | Inno Setup 6.7.3; staged allowlist and unsigned artifact SHA-256 recorded |
| Phase G signing preflight | PARTIAL | opt-in `packaging/verify_signatures.ps1` verifies every shipped EXE/DLL/PYD, hash, Authenticode and timestamp evidence; trusted signing identity remains external |
| Phase G installer install/upgrade/uninstall | DEFERRED | explicitly approved disposable installation rehearsal |
| Phase G candidate data retention | DEFERRED | inspect that uninstall preserves `%LOCALAPPDATA%` candidate state in a disposable installation |
| Phase G packaged Excel COM | DEFERRED | isolated fictional workbook and owned Excel process |
| Phase G clean-machine compatibility | DEFERRED | Windows test machine without project Python |
| Phase G code signing/security warnings | PENDING | verified signing decision; current candidate is unsigned |
| Automated final acceptance completion | PARTIAL | `03-automated-completion-report.md`: 331 unit tests, source-native Qt checks, synthetic COM/UAT and packaging inspection passed; human/trust gates remain |
| Final engineering completion | PASS (automatable scope) | `05-final-engineering-completion-report.md`: 332 tests, native Qt/UI and source COM rerun, runtime/recovery/package audit, and signing preflight complete |
| Human acceptance package | READY | `06-human-acceptance-package-th.md` consolidates only human/external evidence, owner decisions and sign-off forms |
| Remaining blockers | EXTERNAL / HUMAN | `07-remaining-blockers.md` proves no safely automatable task remains and records the trust, physical-interaction and business gates |
| Final technical acceptance | PARTIAL | technical evidence is recorded in `01-technical-final-acceptance.md` and `03-automated-completion-report.md`; manual, business and trusted-deployment gates remain |
| Production activation | NOT_VERIFIED | every applicable gate plus explicit business-owner authorization |
