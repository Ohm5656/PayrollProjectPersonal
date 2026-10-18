# Phase D.0.1 — Current UI and Workflow Audit

## Scope and evidence

This is a read-only audit of the UI and its existing application contracts as of the Phase C.1 baseline (`1047bd7`). It records the implementation that exists today; it does not propose or apply business-rule, database, Excel-template, or production-write changes.

Primary evidence inspected: `app/main.py`, `app/ui/main_window.py`, `app/ui/tray.py`, `app/ui/lifecycle.py`, `app/ui/setup_wizard.py`, `app/ui/review.py`, `app/ui/calendar_review.py`, `app/ui/presentation.py`, `app/domain.py`, the draft calculator, runtime services, and unit tests.

## What users have today

The product is tray-first. Its background runtime owns the watcher, jobs, recovery, and state; a `MainWindow` is created only when a user asks to open it. Opening or closing that window is therefore not the same action as starting, stopping, or restarting monitoring.

The current main window is a single vertically stacked control centre (1130 × 720 initial size). It contains setup, manual copy selection, summary cards, a seven-column employee table, primary payroll actions, and a collapsed “additional options” group. This exposes nearly every capability, but it mixes a normal monthly workflow, recovery tools, administration, and test/UAT actions in one place.

## Screen and dialog inventory

| Surface | Existing responsibility | Entry points | Current outcome |
| --- | --- | --- | --- |
| System tray | Background status and quick actions | Windows tray icon; application startup | Shows state colour/tooltip and opens the lazy main window for UI actions. |
| Main window | Monthly payroll control centre | Manual launch, tray Open, tray shortcuts, second interactive launch | Selects period/sources, presents a draft, drives review/confirm/write, and exposes advanced utilities. |
| First-run / Settings (`SetupWizard`) | Folder/template configuration and Windows startup preference | First interactive launch; Main window; tray Settings | Saves workflow folders, then installs/removes the owned Scheduled Task when requested. It reports partial success if Task Scheduler action fails. |
| Copy preparation / file picker | Select or create safe source copies | Main-window recovery area, “prepare copies”, tray Open source file | Keeps source selection in the development/test workspace; source fields are read-only apart from chooser flow. |
| Review Centre | Triage all draft issues | Main action; tray Review; unmapped employee double-click | Lists review issues and opens a specific decision form. |
| Decision dialog | Record an accountable resolution | Double-click an issue in Review Centre | Captures the decision, required reason, optional reusable rule and scope, then recomputes the draft. |
| Employee Review | Examine one employee’s values and issues | Double-click a mapped employee row | Lists payroll fields and issues; double-click supports field review; includes explicit zero-manual-item confirmation. |
| Zero-manual-item dialog | Confirm monthly manual values are zero | Employee Review | Prevents silent carry-forward of selected manual items; requires an explicit check/reason path. |
| Calendar Review | Confirm workday/holiday rules | Advanced options | Records day type, required workday and attendance-bonus effect, with reason and scope. |
| Employee profile dialog | Maintain confirmed recurring values | Main action after selecting employee | Edits base/recurring allowances, attendance bonus default and attendance requirement; recomputes draft. |
| Confirm / write actions | State progression and copy-only output | Main actions | Confirm only when ready. Write is enabled only for confirmed state and an available writer; target remains a copy. |
| Single employee copy test | Write one ready employee into a selected copy | Advanced options | Requires a selected ready employee, non-final period, reason, and copy writer. |
| Payslip selection dialog | Update selected payslips in a copy | Main action | Allows individual/all selection; enabled only in confirmed/written state with writer. |
| Reopen differences dialog | Inspect source changes after confirmation before reopening | Advanced options | Shows old/new source/final values; requires acknowledgement and a reason before reopening. |
| Audit history dialog | Read recorded audit events | Advanced options; tray History | Displays timestamp, action, period and actor. |

## Action and state inventory

| User action | Preconditions and result | Safety/visibility observation |
| --- | --- | --- |
| Open main window | Tray trigger/double-click/menu or normal launch | Restores a window without changing monitoring state. |
| Pause monitoring | Tray action while watching/processing/review/error | Explicit runtime action; persists disabled monitoring intent. |
| Resume monitoring | Tray action while disabled/error | Explicit runtime action; watcher/configuration validation remains in runtime. |
| Configure folders/template | Setup dialog Save | Workflow configuration is persisted before a requested Scheduled Task install/remove; a Scheduler failure is shown as partial application. |
| Start with Windows | Setup checkbox | Independent of monitoring preference. A checked, broken owned task stays checked and exposes Repair rather than being silently removed. |
| Prepare month-8 UAT | Top main-window action | Sets up copy-only UAT and currently requests monitoring resume; it is a specialised test action, not ordinary Settings Save. |
| Select period / actor / copies | Recovery controls | Creates or selects only copy inputs; the actor is stored as a setting. |
| Read and calculate draft | Main primary action | Creates/revises draft using attendance and payroll copies; UI becomes busy while work runs. |
| Open issue review | Main/tray/table | Decisions require reasons; a decision can be one-time or intentionally remembered at selected scope. |
| Edit recurring profile | Main action with selected employee | Requires re-read/recalculation; applies to employee profile, not an uncontrolled worksheet edit. |
| Confirm payroll | Ready draft only | Uses expected revision, then refreshes persisted state. |
| Write monthly copy | Confirmed draft plus writer | Writes through writer service only; not enabled otherwise. |
| Update selected payslips | Confirmed/written period plus writer | Uses selected employee IDs and refreshes after writer completion. |
| Reopen | Final state with acknowledged difference and reason | Makes reopen deliberate and evidence-led. |
| Lock | Written state | Locks the payroll period. |
| View history | Any time | Current presentation is a single audit table with no filters or drill-down. |
| Exit | Tray exit or window lifecycle | Runtime coordinates shutdown; active UI work is considered before exit completes. |

## Current data presentation and accuracy findings

The table columns are: Name, `OT`, Allowance, Travel, Attendance bonus, Special items, and Status. `OT` combines normal and holiday hours as `normal / holiday`; the table does not label the unit in its header. “Special items” is a count of non-zero payroll fields after excluding travel, allowance, attendance bonus, base salary and OT/day fields. It is not a money total.

### Attendance bonus vs. bonus field

There is no evidence of a value-mapping bug in the audited code:

- The Thai field catalogue maps internal `bonus` to **เบี้ยขยัน**.
- The employee profile label `attendance_bonus_default` is **เบี้ยขยันเมื่อผ่านเงื่อนไข**.
- The draft calculator produces `values['bonus']` from that confirmed per-employee default only after its calendar, required-workday and leave rules are deterministically resolved; an approved cut/custom/field override is also represented through this field.
- `special_bonus` is a distinct manual field (**โบนัสพิเศษ**) and is excluded from the attendance-bonus column; when non-zero it contributes only to the “special items” count.

Therefore the current header **เบี้ยขยัน** and displayed `bonus` value are semantically aligned. The presentation remains risky because it provides neither provenance nor a visible distinction between an automatic eligibility result, a custom approved amount, and a manual field override. The redesign must retain the one field mapping but show source/category/reason in drill-down, and must label `OT` as hours and “special items” as a count.

## UX audit findings

| Priority | Finding | User impact | Phase D response direction |
| --- | --- | --- | --- |
| P0 | A dense single page combines state-changing payroll actions with setup, UAT and recovery controls. | It is easy to lose the intended next action in a high-consequence workflow. | Separate Overview, Review queue, History, Problems and Settings; retain guarded actions. |
| P0 | Payroll state, watcher state, job/recovery health, and Windows startup state are not shown together as distinct concepts. | A user can confuse “watching”, “ready to confirm”, “Task Scheduler installed”, and “copy write completed”. | Use independent, named status indicators; never infer one from another. |
| P0 | Critical financial values have insufficient traceability in the summary table. | The user sees a number but not whether it is calculated, profile-based, overridden, or awaiting confirmation. | Add per-employee details and source/reason/category signals without changing calculation rules. |
| P1 | The primary action row has many equal-weight buttons. | Confirmation, review, profile administration and payslips compete visually. | Make the next permitted state transition primary; make secondary actions contextual. |
| P1 | Empty, loading, error and partial-success states are mostly status-bar messages. | Important feedback can be missed; the table/cards may look stale during background work. | Define page-level state panels, inline errors, refresh timestamps and action recovery. |
| P1 | Review Centre is issue-led while daily work often begins with “what must I do now?”. | Users must interpret counts and open dialogs to find priority. | Provide a prioritised review queue with employee, issue class, amount/status, evidence and next action. |
| P1 | History is only a four-column unfiltered table. | It is difficult to answer what changed, why, and for which employee/month. | Design filters, event detail and deep links; add query capability only in a later implementation phase if needed. |
| P1 | The app has no dedicated visible problem/recovery surface. | Watcher/job errors and partial configuration outcomes have weak discoverability after a notification disappears. | Define a Problems page fed by existing runtime/status data first; do not invent persistence claims. |
| P2 | Advanced options hide useful but infrequent actions in a checkable group. | Discoverability is low and action grouping is not task-based. | Move each item to its owning page/context; keep destructive actions guarded. |
| P2 | Some labels are concise but ambiguous (for example `OT`, “special items”). | Incorrect interpretation is possible even when calculation is correct. | Use Thai labels with units and explanatory helper text/tooltips. |
| P2 | Current tables do not specify keyboard, focus or screen-reader behaviour. | Accessibility quality is unverified. | Establish Qt accessibility, focus order, contrast and non-colour state requirements. |

## Existing constraints the redesign must preserve

- The tray remains the background control surface; closing/hiding the main window must not stop automation.
- Monitoring preference and Windows auto-start remain independent. Only explicit tray Resume may resume paused monitoring in normal operation.
- Runtime owns watcher lifecycle, configuration validation, persisted jobs, recovery and retry semantics. UI must request actions through those contracts rather than creating watchers.
- The state machine remains DRAFT → NEEDS_REVIEW/READY → CONFIRMED → WRITTEN → LOCKED, with deliberate reopen handling.
- No production payroll or template writes are permitted. Copy-only/test safety boundaries, source checks and writer gating remain intact.
- Review decisions, reasons, audit records, revision checks, confirmed-period differences and lock guarantees remain visible and enforceable.
- Existing services/repositories remain the authority for data. Phase D UI must not embed duplicate payroll logic.

## Audit conclusion

The core workflow and safety controls are materially stronger than their current presentation. The redesign should make the safe workflow legible rather than changing it: make the current state and next safe action obvious, surface review evidence before financial transitions, reserve settings/recovery for their own contexts, and preserve the tray-first runtime boundary.
