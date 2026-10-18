# Phase D.3 — Review Queue and Employee Detail

## Architecture

`ReviewQueueModel` converts the selected persisted `PayrollDraft` into
read-only queue items. It classifies actual `ReviewIssue` metadata, preserves
the original issue/evidence, sorts critical items before warnings, and does not
call services or write data. `ReviewQueuePage` renders that snapshot and applies
search, category, employee, and severity filters in memory only.

`EmployeeDetailPage` renders the selected `EmployeeDraft` and its existing
`PayrollValue` fields. `MainWindow` remains the controller: it reads the
selected period through `PayrollService.current`, owns navigation, and routes
explicit user actions to existing dialogs/services.

## Queue and filtering

Queue rows show employee/global context, category, Thai date where supplied,
issue description, severity text, and source evidence in the item tooltip.
Critical items are labelled **ต้องดำเนินการ** and warnings **คำเตือน**.
Counts always describe the full snapshot; the visible metric separately reports
the filtered count. Filters neither acknowledge nor remove evidence.

`SOURCE_` critical issues are intentionally not approval actions. They instruct
the user to correct the approved Excel copy and read it again.

## Employee evidence

The employee page keeps source, previous, draft, user override, final value,
reason, source reference, category, and confirmation status separate. Missing
values show `—`; numeric zero remains zero. It preserves domain labels,
including `bonus` (เบี้ยขยัน), `special_bonus` (โบนัสพิเศษ), and distinct
normal/holiday OT fields.

## Decision and refresh flow

Selecting a resolvable queue issue opens the existing `DecisionDialog` or
`PayslipMappingDialog`. Employee detail uses the existing DecisionDialog,
profile, calendar, and zero-manual-review paths. No new decision persistence or
financial calculation exists in the redesigned pages.

Only after a dialog returns Accepted does MainWindow invoke the existing
`PayrollService.prepare()` asynchronously with the selected draft's approved
copy paths. The queue and overview refresh from that service result, not from an
optimistic client-side state change. A dialog decision is source-hash scoped by
the existing repository contract; a different-period result does not replace
the visible selected period.

## Safety and compatibility

Final states render evidence read-only and disable ordinary employee-detail
mutation controls. Queue navigation, filters, Tray Review, and employee detail
never create/resume watchers or write Excel. Existing revision checks,
reasons, rule scope, audit history, writer copy-only restrictions, and runtime
ownership remain unchanged.

The legacy review dialogs remain the authoritative implementation during this
migration. Review Queue is now the public `review()`/Tray Review destination.

## QA and limitations

Automated offscreen tests cover queue state/filtering, keyboard-capable table
selection, detail rendering, dialog routing, critical-source protection,
navigation, Tray compatibility, and monitoring independence. Layout checks use
1366×768, 1920×1080, and 900×700 through the existing shell tests.

WINDOWS INTERACTIVE VISUAL QA: NOT VERIFIED

Remaining UI phases are D.4 History & Period Lifecycle, D.5 Problems &
Recovery, D.6 Settings & First Run, and D.7 Accessibility & Visual Polish.
