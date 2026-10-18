# Phase D.0.2 — User Flows and Navigation

## Design intent

The future UI should answer three questions immediately:

1. Is the background automation healthy, and is monitoring intentionally on or off?
2. What payroll period is active, what state is it in, and what is the next safe action?
3. What specifically needs a human decision before a financial transition can proceed?

The design keeps the existing runtime and payroll state machines authoritative. Navigation changes where an action is presented; it does not change who may perform it, its preconditions, its audit requirements, or its copy-only output boundary.

## Proposed information architecture

The interactive window uses a persistent left navigation on wider screens and a compact drawer on narrow screens. Page names are Thai-first and task-oriented.

| Navigation item | Thai label | Responsibility | Existing capability it brings together |
| --- | --- | --- | --- |
| Overview | ภาพรวม | Current period, next safe action, high-level health and summary | Main cards, state/status bar, period selection, copy preparation, read draft, confirm/write gating. |
| Review queue | รอตรวจสอบ | Issues that prevent or qualify the draft, ordered for action | Review Centre, Employee Review, Decision dialog, zero-manual review, calendar review. |
| History | ประวัติ | Audit events and completed workflow context | Current audit history; later filter/detail UI only when supporting queries exist. |
| Problems | ปัญหาและการกู้คืน | Runtime/job/file/configuration problems, with safe recovery direction | Runtime status/notifications, existing recovery/source-copy paths and future job retry exposure. |
| Settings | ตั้งค่า | Workflow folders/template, Windows startup, monitoring preference explanation | SetupWizard and documented monitoring/startup independence. |

Period context (month/year and current payroll state) is global to Overview and Review queue, but not silently changed when a user opens History or Settings. The selected employee is local to employee detail/review, never a hidden global instruction for write or profile changes.

## Global status model

These are separate signals, rendered as text plus icon/colour; no signal substitutes for another.

| Signal | Values to communicate | Source of truth | Required interaction |
| --- | --- | --- | --- |
| Monitoring | Watching, paused, processing, review required, error | `AutomationRuntime` state and persisted `watch_enabled` intent | Pause/resume only from explicit runtime commands; Show tray control hint. |
| Windows start | On and valid, on but needs repair, off, unavailable/error | `WindowsStartupService.validate()` | Open Settings; Repair or change only through existing service. |
| Current payroll period | No draft, draft, needs review, ready, confirmed, written, locked | Persisted run via `PayrollService` | Display state and permitted next action. |
| Background job/recovery | Idle, processing, failed/retryable, review required | Existing persisted jobs/runtime summary where exposed | Link to Problems; never claim a job was retried unless service confirms it. |
| Write target | Copy-only / writer unavailable / copy written | Existing writer and workflow safety validation | Show target and gate write actions exactly as now. |

The Overview header should state these independently, for example: “Monitoring: paused by user”, “Windows start: on”, and “Payroll: September 2026 — needs review”. Enabling Windows start must never alter monitoring text, toggle, watcher count, or watcher state.

## Page responsibilities and action placement

| Existing action | Proposed location | Presentation rule |
| --- | --- | --- |
| Select month/year and actor | Overview context bar | Persist/refresh actor as current implementation does; do not hide the chosen period. |
| Prepare safe copies / choose recovery files | Overview, “Source copies” card; Problems when configuration is incomplete | Clearly name copy location and source status. Do not expose a production path as a target. |
| Read / calculate draft | Overview primary action when sources are ready | Use a single clear label such as “Read files and prepare draft”. Show busy/progress and last refresh. |
| Open review issues | Overview “needs attention” card and Review queue | Badge count must distinguish blocking from non-blocking review where existing data allows it. |
| Open employee details | Employee list row | Detail includes field value, category, source evidence, previous/override/final value and associated issues. |
| Profile values | Employee detail, protected secondary action | Require selected mapped employee; preserve confirmed-profile semantics and recalculation. |
| Calendar review | Review queue for calendar issues; period tools menu otherwise | Present affected date/scope and required reason; do not imply that a suggestion is policy. |
| Confirm payroll | Overview primary action only at READY | Explain that it uses the existing revision check and creates a confirmed state; no confirm shortcut in tray. |
| Write payroll copy | Overview completion area only at CONFIRMED and writer available | Name it “Write to payroll copy”; show destination/safety condition before execution. |
| Update payslips | Completion area after confirmation | Keep selection dialog and existing state/writer gate. |
| Lock period | Completion area after write | Treat as a guarded finalisation action with clear written-state prerequisite. |
| Reopen confirmed period | History/period detail, not the daily primary path | Require the existing difference acknowledgement and reason; show affected period. |
| One-employee copy test / month-8 UAT | Settings or clearly labelled “Test and recovery” subsection | Keep copy-only language, selected-employee/ready checks and reason requirement. Do not mix with normal confirmation. |
| Pause/resume monitoring | Tray menu remains canonical; Overview only displays state and guides user | A future visible button may be considered only if it invokes the same explicit runtime methods and does not conflate it with Settings. |
| Windows startup / repair | Settings | Clarify that this starts the application, not necessarily file monitoring. |
| Open source/payroll copy | Overview source card; tray quick actions retained | Reveal as “Open attendance copy” / “Open payroll copy”, never a production original. |
| Audit history | History page and tray shortcut retained | Current data supports a basic list; filter/detail promises require later service support. |

## Core user flows

### 1. Normal monthly preparation and confirmation

1. User opens the main window from the tray or a manual launch. The app does not change monitoring state.
2. Overview shows monitoring, Windows-start status, current period state and safe source-copy status.
3. User selects period/actor and prepares or selects the permitted copies.
4. User chooses **Read files and prepare draft**. The page shows processing rather than leaving an apparently stale table interactive.
5. Overview displays employee count, blocking-review count, source timestamp, state, and a single next action.
6. If review is required, user opens Review queue; if all conditions are satisfied, user confirms payroll from Overview.
7. After confirmation, Overview exposes the copy-only write action. After a successful write, it exposes lock as the deliberate final action.

### 2. Resolve a review item

1. User enters **รอตรวจสอบ** from the badge or navigation.
2. Queue defaults to unresolved blocking items, ordered by payroll impact/issue class when supported by current data; it always retains employee, date/sheet/cell evidence and issue description.
3. User opens an item. Employee detail/Decision dialog presents source evidence, field/category, permitted decision controls, scope and required reason.
4. Saving uses the same repository/service decision path. The UI refreshes the draft and queue; it never assumes a result without recalculation.
5. When no blocking issues remain, the Overview state changes to ready using the persisted run state.

### 3. Investigate a financial value

1. User selects an employee from Overview or Review queue.
2. Detail lists financial fields with Thai label, unit, final value, category and review state.
3. Selecting a field shows its source value/evidence, previous value where available, override value/reason if present, and final value.
4. For **เบี้ยขยัน**, detail must explicitly identify it as `bonus` derived from the confirmed attendance-bonus default plus verified calendar/leave rules, or identify the approved cut/custom/override reason. **โบนัสพิเศษ** remains a separate manual field.
5. The user can enter an existing permitted review/profile flow; UI does not calculate or alter an amount itself.

### 4. Configure folders and Windows startup

1. User opens **ตั้งค่า** from navigation or tray.
2. The page states the independent status of (a) workflow folders/template, (b) monitoring preference, and (c) Windows auto-start.
3. User saves folders/template and optionally changes “Start with Windows”.
4. The existing sequence persists valid workflow configuration before attempting external Scheduled Task change.
5. If the external operation fails, show a durable inline partial-success message: folders were saved; Windows start was not changed; monitoring was not changed. Keep the dialog/page available for retry or repair.
6. Saving Settings must not resume monitoring, create another watcher, or alter an explicit paused preference.

### 5. First-run setup

1. On interactive first launch without configuration, show setup before normal daily work.
2. Explain folder/template selection, copy-only output and the optional Windows-start setting.
3. Preserve current first-run convenience: only when `watch_enabled` has never been set may successful setup request monitoring resume.
4. If the preference is explicitly false, first-run setup must leave monitoring paused. Setup completion must make this visible, not silently override it.

### 6. Background monitoring and tray operation

1. The program may start hidden from Windows startup when the tray is available.
2. Tray icon/tooltip communicates runtime state. Clicking the icon opens the window but does not alter the runtime.
3. Tray retains focused quick actions: Open, Review, open copy files, History, Settings, Pause monitoring, Resume monitoring, Exit.
4. **Resume monitoring** remains an intentional action. Runtime validates configuration and preserves singleton/watcher lifecycle guarantees.
5. If the tray is unavailable, the normal interactive window remains the fallback according to current startup logic.

### 7. Recover from a failure or source change

1. Notification, Overview status, or Problems page leads the user to a human-readable description and known context (source, period/job where available).
2. The page offers only existing safe recovery options: open settings, prepare/select source copies, review required decisions, or use a runtime retry that has an explicit persisted job identity.
3. A change detected after confirmation leads to the existing difference/reopen flow. User reviews old/new values, acknowledges, supplies a reason, and then reopens.
4. No UI action deletes jobs, bypasses review, edits source evidence, or writes an original workbook.

### 8. Close and exit

1. Closing the main window hides/returns to tray according to the existing lifecycle; it does not pause monitoring.
2. Choosing Exit is the deliberate application shutdown path. UI waits for runtime shutdown coordination rather than abandoning active work.

## Required states on every page

| State | Behaviour |
| --- | --- |
| Empty / not configured | Explain the one next setup action and copy-only purpose; no financial action available. |
| Empty / no current draft | Let the user set period and sources; show no invented totals. |
| Loading / processing | Disable duplicate state-changing controls, preserve readable context, indicate current operation and offer no misleading completion signal. |
| Success | State what was persisted/completed, period and source/copy context; update permitted next action. |
| Review required | Show count and direct path to the queue; distinguish this from runtime watcher health. |
| Partial success | State exactly which component succeeded and which failed, with retry/repair path. |
| Error | Show plain-language summary, retain technical detail in logs where it is today, and point to safe recovery action. |
| Final / locked | Clearly read-only; route reopen through the existing protected flow. |

## Thai terminology and content rules

| Use | Avoid | Reason |
| --- | --- | --- |
| **รอตรวจสอบ** | “error” for every review item | A review requirement is not necessarily a failure. |
| **ปัญหาและการกู้คืน** | “fix everything” | Keeps recovery scoped to validated actions. |
| **เริ่มเฝ้าดูไฟล์อีกครั้ง** / **หยุดเฝ้าดูชั่วคราว** | vague “start/stop system” | Distinguishes monitoring from the application and Windows start. |
| **เริ่มพร้อม Windows** | “เปิด monitoring ตอนเปิดเครื่อง” | Reinforces independence. |
| **เขียนลงไฟล์สำเนา** | “บันทึกเงินเดือน” alone | Makes copy-only boundary explicit. |
| **รายการพิเศษ (จำนวนรายการ)** | “รายการพิเศษ” without unit | Prevents reading a count as a currency total. |
| **OT ปกติ / OT วันหยุด (ชั่วโมง)** | `OT` alone | Makes the current numeric unit unambiguous. |
| **เบี้ยขยัน** and **โบนัสพิเศษ** | one generic “โบนัส” label | Preserves separate fields and source rules. |

## Accessibility and interaction requirements

- All status categories require text and an icon/shape in addition to colour; green/yellow/red alone is insufficient.
- Every actionable control has a Thai accessible name, tooltip/help text where the label is abbreviated, visible keyboard focus, and logical tab order.
- Tables support keyboard row navigation, Enter to open details, and a visible selected-row state with adequate contrast.
- Dialogs place focus on their explanatory content or first required input, identify required reasons before Save, and return focus to the initiating control after close.
- Critical confirmation/write/lock/reopen actions cannot rely on hover-only information and cannot be activated by accidental double-click in a table.
- Dates use Thai-readable display (`dd/mm/yyyy` Buddhist Era where shown) while preserving the existing canonical persisted value internally.
- Currency shows grouping and two decimals; hours/days are visibly labelled as quantities. Missing/awaiting confirmation is text, not zero.
- Layout must remain usable at Windows 125–200% scaling, with wrapping/scrolling rather than clipped Thai labels.

## Capability boundaries for later implementation

This navigation specification does not assert data that the current application does not expose. In particular, the current history UI only calls `audit_history()` and has no documented filter/detail query; runtime retry exists but is not yet a UI feature; and a full Problems page needs a defined read model for persisted job/error detail. D.1–D.7 must add only the minimum presentation/service query support justified by each screen, with regression tests, and must not create a second business-logic path in the UI.
