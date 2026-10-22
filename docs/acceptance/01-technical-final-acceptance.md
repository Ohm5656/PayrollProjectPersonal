# Technical Final Acceptance

**Date:** 22 October 2026 (Asia/Bangkok)
**Repository:** `Ohm5656/PayrollProjectPersonal`
**Remote baseline:** `9fec0e2`
**Technical acceptance base:** `a762abb`

This is a technical, copy-only assessment. It does not authorize production
payroll, real-data use, deployment, monitoring, Windows startup, or a change to
Windows security protection.

## Preflight and safety

- Branch: `main`; HEAD: `a762abb`.
- User-owned `docs/qa/` was read as historical evidence only; it was never
  modified, staged, or committed.
- Tests used pytest temporary fixtures, synthetic workbooks below
  `test_workspace`, or a disposable source clone. No normal database,
  reference workbook, user Excel process, Scheduled Task, or production workbook
  was used.
- The normal `--smoke-test` was not run because its non-QA path opens the
  persistent development DB and may run migration/import paths.
- The known-blocked frozen EXE was not re-run. No security policy, exclusion,
  registry value, or certificate was changed.
- The disposable source clone remains below the Windows temporary directory
  because the terminal safety guard declined its recursive-cleanup command. It
  contains only the synthetic QA smoke state and is outside this repository.

## Validation results

| Validation | Result | Actual evidence |
| --- | --- | --- |
| Focused D–G regression | PASS | 61 passed in 39.82 s |
| Native Excel COM (owned instance) | PASS | 3 passed in 14.99 s; zero `EXCEL.EXE` before and after |
| Full unit suite | PASS | 330 passed in 347.65 s; no failures or skips |
| Source QA smoke | PASS, offscreen only | `--qa-ui --smoke-test` completed in a disposable clone and created its own synthetic QA DB |
| Compilation | PASS | `python -X utf8 -m compileall -q app` exit 0 |
| Diff hygiene | PASS | `git diff --check` exit 0 before acceptance documentation |

The source smoke emitted non-fatal Qt offscreen font/size-hint messages. It
exited normally. Those messages do not establish native Windows typography,
DPI, or notification-area behavior.

## Phase D — desktop UI

| Area | Status | Evidence and boundary |
| --- | --- | --- |
| Primary pages, period context, empty states | PASS (automated) | Qt/offscreen coverage covers Overview, Review, History, Problems and Settings at 1920×1080, 1366×768, 1024×768 and 900×700. |
| Period/table synchronization | PASS | September/October/no-draft cases clear stale employee rows, selection and actions. |
| Theme, Thai fallback and surfaces | PASS (automated) | Tests assert scoped light surfaces, fallback fonts, wrapping and accessible labels. |
| Safe keyboard controls/focus | PASS (automated) | Enter, Space, arrows and navigation focus are covered without invoking payroll actions. |
| Full native keyboard traversal, clipping and DPI | NOT VERIFIED | Offscreen Qt cannot prove Windows compositor/focus-order behavior. |
| Tray lifecycle/single instance | PASS (Qt/controller) | Hide/restore/exit and single-instance regression tests passed. |
| Native notification-area interaction | NOT VERIFIED | No current live tray icon/menu was controlled. |
| Automatic monitoring | PASS (automated) | QA fixture keeps `watch_enabled=false` and lifecycle regressions passed. |

The historical Windows QA report provides earlier native Settings evidence only.
It does not replace a controlled current native UI/tray check.

## Phase E — synthetic payroll and Excel

| Area | Status | Evidence and boundary |
| --- | --- | --- |
| Attendance/identity/period recognition | PASS | Synthetic fixtures exercise readers, adapters, identity rejection and review gates. |
| Salary, OT, holiday values, bonus, allowance, deduction, income, net | PASS (synthetic) | Decimal assertions include income 33,100 and net 32,200; explicit OT classification is required. |
| Payslips/payment date/year transition | PASS (technical) | Payslip mapping and workbook payment-date tests pass; the month-12 workflow asserts payment date `2027-01-05`. |
| Confirmation/source hash/revision/single copy | PASS | Confirmation, explicit-reason and changed-source/destination gates passed. |
| Workbook write/formula/format/backup | PASS (synthetic) | Owned native COM tests validate write, structure preservation and backup hash. |
| Native Excel COM | PASS (synthetic only) | Tests created and closed their own Excel instance. |
| Business payroll policy | BUSINESS OWNER REVIEW REQUIRED | Technical fixtures do not approve real rates, taxes, deductions, rounding or accounting rules. |
| Real-data copy-only UAT | DEFERRED | Requires separate written approval and approved copies. |

## Phase F — reliability and recovery

| Area | Status | Evidence |
| --- | --- | --- |
| Readiness is read-only; UNKNOWN is not PASS | PASS | Isolated readiness test asserts `MONITORING_STATE=NOT_VERIFIED`. |
| SQLite schema/snapshot and path boundaries | PASS | Disposable DB, snapshot and boundary tests passed. |
| Source/revision mismatch and backup hash gates | PASS | Changed source/destination is rejected; restore requires a fresh target and matching hash. |
| Staged-write ambiguity/no destructive recovery | PASS (automated) | Failure tests retain verified backups and do not auto-retry ambiguity. |
| Watcher/jobs/audit history | PASS (automated) | Full suite covers supervision, pause/shutdown, durable jobs and audit evidence. |
| Operator rehearsal and retention ownership | PENDING | Requires human operational approval. |

## Phase G — packaged candidate

| Area | Status | Evidence |
| --- | --- | --- |
| QA-only entry/staging allowlist | PASS | Packaging/G.6 contract tests pass; existing report records 228 allowlisted files. |
| Installer build | PASS | Inno Setup 6.7.3 artifact and SHA-256 are recorded. |
| Frozen EXE | BLOCKED | Windows Code Integrity Event 3077 blocked the unsigned main EXE under `VerifiedAndReputableDesktop`. |
| Installer execution/install/uninstall | NOT VERIFIED | No disposable installation authorization; installer was not executed. |
| Packaged Excel COM | NOT VERIFIED | Requires successful trusted frozen execution. |
| Code signing | PENDING | EXE and installer are `NotSigned`; see [Application Control diagnosis](../phase-g/07-windows-application-control-diagnosis.md). |

## Defects and remaining acceptance

No reproducible source-code defect was found and no production/payload behavior
was changed in this session. Required human gates are:

1. Native Windows UI, keyboard, Thai clipping, DPI and tray acceptance.
2. Business-owner approval of payroll and accounting policies.
3. Backup/recovery operator rehearsal and retention decision.
4. Trusted code signing plus, if applicable, administrator approval of App
   Control policy.
5. Disposable-machine install/upgrade/uninstall and signed packaged COM tests.

## Decision

Technical regression and synthetic UAT evidence support a **copy-only test
candidate**. They do not support production activation or a claim of complete
final acceptance.

| Final status | Result |
| --- | --- |
| Technical Final Acceptance | PARTIAL |
| Source Application QA | PASS (automated/offscreen) |
| Native Windows UI | NOT VERIFIED |
| System Tray | NOT VERIFIED natively |
| Payroll Calculation UAT | PASS (synthetic; business approval pending) |
| Native Excel COM | PASS (synthetic owned-instance test) |
| Backup & Recovery | PASS (automated isolated fixtures) |
| Runtime Reliability | PASS (automated) |
| Frozen EXE | BLOCKED |
| Installer Build | PASS |
| Installer Execution | NOT VERIFIED |
| Packaged Excel COM | NOT VERIFIED |
| Business Owner Acceptance | PENDING |
| Production Authorization | NOT GRANTED |
| Ready for Production Activation | NO |
