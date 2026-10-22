# Automated Final Acceptance Completion

**Date:** 22 October 2026 (Asia/Bangkok)
**Repository / branch:** `Ohm5656/PayrollProjectPersonal` / `main`
**Starting remote baseline:** `9fec0e2`
**Existing local acceptance commits retained:** `a762abb`, `16abe88`

This report records the safe, automated work completed after the technical
acceptance report. All payroll records, databases, workbooks, and UI captures
used here were synthetic and isolated. This is not production authorization.

## Safety boundary and method

- A pre-existing user-owned Python QA process was neither controlled nor
  terminated.
- Native UI automation used a newly generated, UUID-named QA root below the
  ignored `test_workspace` directory. It did not invoke `app.main`, acquire the
  shared single-instance lock, or open the normal database.
- The source-level Excel tests first confirmed that no `EXCEL.EXE` process was
  present. They created and closed only their own synthetic Excel instance.
- No reference workbook, Scheduled Task, Windows security setting, production
  write path, or normal persistent database was modified.
- The frozen EXE was not retried. The existing Windows Application Control
  diagnosis remains in force.

## Verified source UI correction

Native Windows Qt rendering exposed two reproducible visual defects that were
not apparent in offscreen-only QA:

| Test ID | Expected result | Actual result before correction | Correction and regression evidence | Status |
| --- | --- | --- | --- | --- |
| FA-AUTO-UI-01 | Light canvas and table surfaces remain light under the Windows palette. | Scroll bodies and table viewports inherited dark native palette areas, producing black gaps/surfaces. | Scoped canvas/table QSS plus explicit opaque palette helpers for only the affected scroll and table widgets. `test_visual_polish.py` verifies scoped surfaces and table viewports. | PASS |
| FA-AUTO-UI-02 | Application stylesheet parses when the repository path includes spaces. | Qt emitted `Could not parse application stylesheet`; the checkbox SVG used a percent-encoded `file:` URI. | Use a quoted forward-slash local QSS path. The test asserts a quoted path and rejects `%20`; a native Windows Qt harness emitted no stylesheet diagnostic after the change. | PASS |

The correction is presentation-only. It does not change payroll rules, state
transitions, Excel writing, database schema, watcher ownership, monitoring, or
Windows-startup behaviour.

## Automated acceptance evidence

| Test ID | Test method | Expected result | Actual result | Status | Evidence / remaining action |
| --- | --- | --- | --- | --- | --- |
| FA-AUTO-UI-03 | Native PySide6 `windows`-platform harness with a fresh QA DB and visible `MainWindow`. | Overview, Review, History, Problems, and Settings render and navigate without state mutation. | All five rendered; Thai UI text was present; no stylesheet diagnostic; monitoring remained disabled. | PASS | Synthetic native captures only. Human visual/tray interaction remains required. |
| FA-AUTO-UI-04 | Native harness resized the source window to 1920x1080, 1366x768, 1024x768, and 900x700. | Pages remain reachable and their light surfaces are retained while resizing. | All five pages were captured at each requested size; native sample checks found no black canvas/table region after the correction. | PASS | A human must still assess the active monitor's DPI and subjective clipping. |
| FA-AUTO-UI-05 | Native synthetic period navigation September -> October -> November. | Table, selection, actions, and overview context belong only to the selected period. | September had 2 rows, October had 2 different rows, November had 0 rows and selection `-1`; returning to an existing month reloaded its data. | PASS | Covered further by period/table regression tests. |
| FA-AUTO-UI-06 | Native Qt focused UI regression set. | Page navigation, history/review/problem/detail/settings behaviour, accessible focus, period synchronization, and controller lifecycle remain safe. | `56 passed in 71.99 s` with `QT_QPA_PLATFORM=windows`. | PASS | Notification-area shell clicks are not simulated by this result. |
| FA-AUTO-TRAY-01 | Qt controller and native platform availability check. | One window restores; tray menu callbacks and Exit use the authoritative controller; QA monitoring stays disabled. | Native platform reported tray availability; lifecycle tests exercised Open, DoubleClick, Trigger, Exit, restore and single-instance isolation. | PASS (controller) | Actual Windows notification-area click/restore/Exit is not verified. |
| FA-AUTO-PAY-01 | Isolated synthetic payroll UAT. | Identity, attendance, Decimal calculations, OT/allowances/deductions, recurring changes, review gates, lifecycle, payment date rollover, payslips, source/revision guards, and workbook safety behave as specified. | `111 passed in 101.93 s` across Phase E/F/G focused UAT, watcher/runtime, writer, workbook, recovery, and packaging-contract tests. | PASS | Payroll owner must still approve real business rules. |
| FA-AUTO-EXCEL-01 | Source-level native COM tests with fresh synthetic workbooks. | Application owns/releases Excel; workbook operations, formula results, backups, restore target, audit evidence, and structure are safe. | `3 passed in 14.13 s`; zero user Excel processes before test start. | PASS | This is source-only synthetic COM, not the frozen package. |
| FA-AUTO-REL-01 | Unit tests for debounce, locked files, pause/resume, durable jobs, restart/shutdown, idempotency, SQLite and recovery boundaries. | No destructive automatic recovery and no watcher/runtime regression. | Included in the focused 111-test set and final 331-test suite. | PASS | Operator recovery rehearsal and retention decision remain human work. |
| FA-AUTO-PKG-01 | Non-executing packaging safety tests and artifact inspection. | Staging contains allowlisted application files only; runtime state/workbooks are rejected; candidate paths/hashes/signatures are explicit. | Packaging-contract and installer-safety tests passed; canonical installer hash matches its G.6 report. | PASS | Installation and signed-package execution require a disposable authorized environment. |
| FA-AUTO-PKG-02 | Read-only Authenticode/hash inspection of the canonical G.6 candidate. | Recorded artifact identity remains traceable; no claim that an unsigned file is trusted. | Candidate EXE hash `255E2C50FA04F8CD4802034489F80326C46A1AB10C9C5293BA95C8DF9BA69C2B`, 51,466,805 bytes; installer hash `D7C8C8E87B0D8FCBFE59737026A3AFA4B16D31AD3C6E56787500DF2C1C74A8DB`, 87,796,196 bytes. Both are `NotSigned` / `None`. | PASS (inspection) | Frozen EXE remains BLOCKED by Code Integrity; signing/policy approval is required. |
| FA-AUTO-PKG-03 | Review ignored distribution artifacts without executing them. | Only the documented build-directory candidate is treated as the G.6 artifact. | Older ignored `dist` files have different hashes and were not executed, staged, or accepted as the candidate. | PASS | Release operator must use the exact canonical path recorded in Phase G.6 until a signed rebuild creates new artifacts. |

## Final command results

| Command or suite | Result |
| --- | --- |
| Native Qt focused UI suite | `56 passed in 71.99 s` |
| Synthetic payroll/reliability/packaging-focused suite | `111 passed in 101.93 s` |
| Native source Excel COM suite | `3 passed in 14.13 s` |
| `python -X utf8 -m pytest tests/unit -q` | `331 passed in 334.15 s (0:05:34)` |
| `python -X utf8 -m compileall -q app` | exit 0 |
| `git diff --check` | exit 0 |

## Packaging and trust boundary

The canonical candidate is
`dist/build-6c5c459ccfac4d498ad85c6c517a46e9/NTP Payroll Assistant - Test Candidate/NTP Payroll Assistant - Test Candidate.exe`.
Its installer is
`artifacts/NTP-Payroll-Assistant-Test-Candidate-Setup.exe`.

Read-only inspection confirms both are unsigned. The documented Event 3077
evidence identifies the main EXE, rather than a bundled DLL, as the initial
Windows Code Integrity block. No workaround was attempted. See
[Windows Application Control diagnosis](../phase-g/07-windows-application-control-diagnosis.md).

## Decision

Automated source acceptance is sufficient to begin the business-owner and
operator sign-off activities listed in the companion Thai document. It is not
sufficient for trusted packaged deployment or production activation.

| Decision | Status |
| --- | --- |
| Automated Final Acceptance | PARTIAL |
| Source synthetic UAT / reliability / backup boundaries | PASS |
| Native source UI | PARTIAL (automated rendering/navigation only) |
| Native notification-area interaction | NOT VERIFIED |
| Frozen EXE | BLOCKED |
| Installer execution | NOT VERIFIED |
| Business-owner approval | PENDING |
| Ready to begin business-owner acceptance | YES |
| Ready for production activation | NO |
