# Phase D.2 — Overview Dashboard

## Scope and architecture

Phase D.2 makes `OverviewPage` the single visible dashboard for the selected
payroll period. It is deliberately a presentation layer: it reads persisted
state through `OverviewViewModel` and sends a user-selected action back to the
existing `MainWindow` controller. It does not calculate payroll, write Excel,
start monitoring, or install Windows startup tasks.

| Component | Responsibility |
| --- | --- |
| `app/ui/overview_model.py` | Read the selected persisted run/draft, runtime state, startup validation, copy-source metadata, and matching background job evidence. |
| `app/ui/overview_page.py` | Render the period, four independent statuses, metrics, source information, employee table host, and one next-action button. |
| `app/ui/main_window.py` | Own existing workflow handlers, reload the selected period before an action, refresh after completion, and retain legacy tools as a compatibility page. |

The compatibility page is still reachable with **เปิดเครื่องมือเงินเดือนเพิ่มเติม**.
Its former dashboard cards are retained only as internal compatibility state and
are not shown alongside the Overview.

## Data and statuses

The model reads `PayrollService.current(year, month)` for the selected period.
Before a draft exists, it only displays the user-selected copy paths; it does
not infer payroll totals. Source labels show a missing file distinctly from a
missing selection.

Four badges remain independent:

- Monitoring: disabled, watching, processing, review required, or error from `AutomationRuntime`.
- Payroll: no draft, draft, needs review, ready, confirmed, written, or locked from the persisted run.
- Windows startup: read-only `WindowsStartupService.validate()` result.
- Excel output: writer availability and the persisted confirmation/write state.

This separation means enabling Windows startup never implies that monitoring is
running, and a successful payroll confirmation never implies Excel output was
written.

## Employee summary

The employee table presents domain values only:

| Column | Source and format |
| --- | --- |
| ชื่อพนักงาน | Employee name |
| OT ปกติ / OT วันหยุด | `normal_ot` and `holiday_ot`, formatted as hours |
| เบี้ยเลี้ยง / ค่าเดินทาง / เบี้ยขยัน | `allowance`, `travel`, and `bonus`, right-aligned monetary values |
| รายการพิเศษ | Count of non-zero extra fields, never a currency value |
| สถานะ | Existing readiness/review outcome |

Missing values render as `—`; actual zero remains `0`. The period title uses the
Buddhist Era once (`year + 543`) and financial calculation code is unchanged.

## One explicit next action

The only prominent action is calculated from persisted payroll state. Clicking
it routes to existing controller methods and their existing service gates.

| Payroll state | Action | Safety retained |
| --- | --- | --- |
| `NO_DRAFT` | อ่านข้อมูลและเตรียมฉบับร่าง | Requires both selected copy files; uses existing asynchronous prepare path. |
| `DRAFT`, `NEEDS_REVIEW` | ตรวจสอบรายการ | Opens the existing Review Center and preserves review evidence. |
| `READY` | ยืนยันเงินเดือน | Uses the existing expected-revision confirmation path. |
| `CONFIRMED` | เขียนลงไฟล์สำเนา | Requires the existing writer; copy-only validation, backup, and rollback remain in the writer. |
| `WRITTEN` | ปิดรอบเงินเดือน | Uses the existing lock workflow and its written-state requirement. |
| `LOCKED` | None | No ordinary confirm/write action is displayed. Guarded reopen remains an advanced action. |

The action is disabled while work is running. Opening Overview, changing the
period, navigating, opening Settings, restoring from Tray, and receiving a
watcher status never perform a financial transition. If a watcher result is for
another period, MainWindow keeps the selected context unchanged and reports
which period has new results.

## Existing features and Tray compatibility

Advanced actions remain available from the compatibility page: source-copy
preparation, employee profile, calendar review, payslip selection,
single-employee copy testing, UAT preparation, guarded reopen, and lock.
Existing sidebar routes and public methods (`review`, `history`, `settings`,
`open_copy`) remain intact. Tray shortcuts continue to call those public entry
points; MainWindow neither creates nor resumes a watcher during navigation.

## Regression protections

Phase D.2 does not change payroll calculations, OT/leave/allowance rules,
employee matching, database schema, Excel templates, writer safety, production
write protection, `AutomationRuntime` ownership, watcher lifecycle, persistent
jobs, crash recovery, Windows startup configuration, or single-instance logic.

Automated checks cover state presentation, primary-action mapping and gating,
employee formatting, different-period watcher results, shell navigation,
Settings/monitoring independence, Tray entry points, and copy-only writer
safety through the existing unit suite.

## Visual QA and limitations

Offscreen automated layout checks exercised 1366×768, 1920×1080, and 900×700,
including readable sidebar sizing and keyboard focus on the Overview primary
action. These checks do not replace visual review on a Windows desktop and do
not use payroll screenshots or private data.

WINDOWS INTERACTIVE VISUAL QA: NOT VERIFIED

Future work remains scoped to D.3 Review Queue, D.4 History, D.5
Problems/Recovery, D.6 Settings, and D.7 visual/accessibility polish.
