# Phase D.0.3 — Visual System and Implementation Plan

## Purpose and non-goals

This document turns the audited workflow into an implementation-ready UI direction for Phase D.1 onward. It is a design and delivery plan only. It does not alter current application code, runtime ownership, database schema, payroll calculations, Excel templates, task scheduling, or production-write protections.

The preferred visual character is calm and operational: a Thai-first desktop tool for accountable monthly work, not a consumer dashboard. Information hierarchy must be stronger than decoration. A user should be able to identify the period, payroll state, blocking review work, source safety and monitoring status in a few seconds.

## Visual foundations

### Typography

Use the Windows system UI font stack: `Segoe UI`, `Leelawadee UI`, `Tahoma`, `sans-serif`. Do not require a downloaded font to render Thai correctly. Use regular 14 px body text as the baseline; do not use font size alone to convey status.

| Role | Size / weight | Usage |
| --- | --- | --- |
| Page title | 24 px / 600 | Page name and current period context. |
| Section title | 18 px / 600 | Cards/panels such as “Next action” or “Source copies”. |
| Table heading | 14 px / 600 | Column headers and grouped labels. |
| Body | 14 px / 400 | Standard Thai UI copy and values. |
| Supporting text | 12–13 px / 400 | Evidence, updated timestamp, helper text, path. |
| Numeric emphasis | 16–20 px / 600, tabular figures if available | Counts, financial summary and state metrics. |

### Colour and semantic tokens

All values below are proposed tokens for a QSS/theme layer. Names, rather than raw colour literals, are the implementation contract. Status is always accompanied by text and an icon/shape.

| Token | Value | Usage |
| --- | --- | --- |
| `color.canvas` | `#F6F8FB` | Application background. |
| `color.surface` | `#FFFFFF` | Cards, table surfaces, dialogs. |
| `color.surface.subtle` | `#EEF2F6` | Secondary areas, selected navigation hover. |
| `color.border` | `#D7DEE8` | Cards, inputs, separators. |
| `color.text` | `#172033` | Primary text. |
| `color.text.muted` | `#5D6878` | Supporting information. |
| `color.primary` | `#1E5AA8` | Normal primary action and link focus. |
| `color.primary.hover` | `#174982` | Hover/pressed primary state. |
| `color.success` | `#197A4A` | Ready/completed state; paired with check icon/text. |
| `color.warning` | `#9A6700` | Review required/processing attention; paired with text. |
| `color.danger` | `#B42318` | Error/blocking destructive emphasis; paired with text. |
| `color.info` | `#245EA8` | Neutral information. |
| `color.focus` | `#124F9E` | 2 px visible keyboard focus indicator. |

The visual system must meet WCAG 2.1 AA contrast for normal-sized text (4.5:1) and meaningful graphical controls (3:1). The exact token values should be contrast-checked with final widget states before adoption.

### Spacing, shape and elevation

Use a 4 px spacing scale: 4, 8, 12, 16, 24, 32. Use 8 px corner radii for cards and inputs, 6 px for compact controls, and restrained elevation (one low shadow or border, never both heavily). Primary workflows gain hierarchy from layout, state, and spacing; avoid gradients, decorative illustrations, or dense colour blocks.

### Component state tokens

Every interactive component defines default, hover, pressed, disabled, focused, selected and error states. Disabled controls explain the missing prerequisite near the control or in the action panel; a disabled “Confirm” button with no explanation is insufficient. Processing state uses text and a progress indicator, not an indeterminate busy cursor alone.

## Application shell and responsive layout

### Wide desktop (recommended at 1366 px and above)

```text
+----------------------+------------------------------------------------------+
| NTP Payroll          |  ภาพรวม / กันยายน 2569     [Monitoring: หยุดแล้ว] |
|                      |------------------------------------------------------|
|  ■ ภาพรวม            |  [Payroll: ต้องตรวจสอบ] [Windows start: เปิด]      |
|  ◉ รอตรวจสอบ   (8)   |  [Source copies] [Next safe action] [Health]       |
|  ◷ ประวัติ            |------------------------------------------------------|
|  ! ปัญหาและการกู้คืน  |  Employee / review summary table                    |
|  ⚙ ตั้งค่า             |  contextual details and guarded actions              |
|                      |                                                      |
|  Tray status / Help   |                                                      |
+----------------------+------------------------------------------------------+
```

The sidebar is approximately 240 px and is fixed while page content scrolls. The top context bar includes current page, selected period, last refresh and the compact independent status cluster. Do not place a monitoring start/stop toggle beside Settings Save; monitoring actions belong to the tray contract.

### Compact desktop (roughly 1024–1365 px)

Collapse sidebar labels or permit a drawer, while keeping page title, period and payroll state visible. Cards flow from three columns to two; tables remain horizontally scrollable with a frozen identity/status edge where feasible. Do not shrink Thai copy below baseline to fit.

### Small/narrow window and high DPI

Use a hamburger/drawer navigation, a stacked header, single-column cards and explicit table detail entry. Important actions wrap into a clear vertical action area. At 125–200% Windows scaling, preserve control height and visible focus instead of clipping text or relying on tooltips for essential meaning.

## Screen specifications

### Overview

Purpose: orient the user to the selected period and drive the one next safe action.

```text
ภาพรวม  |  กันยายน 2569  | อัปเดต 10:42

[สถานะเงินเดือน: ต้องตรวจสอบ]  [Monitoring: หยุดเฝ้าดูโดยผู้ใช้]
[Windows start: เปิดใช้งาน]     [ผลลัพธ์: เขียนได้เฉพาะไฟล์สำเนา]

แหล่งข้อมูลสำเนา                ขั้นตอนถัดไป
Attendance: ready / timestamp     ตรวจสอบ 8 รายการ  [ไปที่รอตรวจสอบ]
Payroll: ready / timestamp        (or [อ่านไฟล์และเตรียมฉบับร่าง])

[พนักงาน 42] [ต้องตรวจสอบ 8] [พร้อม 34] [สถานะ: NEEDS REVIEW]

พนักงาน / OT ปกติ-วันหยุด (ชม.) / เบี้ยเลี้ยง / ค่าเดินทาง /
เบี้ยขยัน / รายการพิเศษ (จำนวน) / สถานะ
```

Rules:

- The highest-emphasis button is exactly one permitted next state transition: prepare/read, go to review, confirm, write copy, or lock. It is derived from persisted run state and existing permissions, not from a UI-only guess.
- Status cards remain separate: monitoring is not payroll state, Windows start is not monitoring, and copy-write readiness is not confirmation.
- Cards use a concise value, plain-language label and optional “view details” link. Do not repeat the same number in multiple attention colours.
- Table uses current values but improves headers: OT normal/holiday **(hours)**; special items **(count)**. `None` remains “awaiting confirmation”, never `0`.
- Row selection opens employee detail. It must not directly confirm, write, or mutate a value.

### Review queue

Purpose: make required human decisions finite, prioritised and evidence-led.

```text
รอตรวจสอบ  [ทั้งหมด 8] [ต้องดำเนินการ 5] [ข้อมูลอ้างอิง 3]
[ค้นหาพนักงาน/ชีต/ข้อความ] [ประเภท] [พนักงาน] [เฉพาะที่ยังไม่เสร็จ]

!  สมชาย ใจดี     12/09/2569   การลา/เบี้ยขยัน      ต้องเลือกผลต่อเบี้ยขยัน  [ตรวจสอบ]
!  ...
```

Rules:

- Preserve source sheet/cell/date/raw-evidence context and explicit required reason from the existing decision flow.
- Use issue severity/criticality from the existing draft; do not invent a financial priority value when no value is available.
- Resolve interaction opens a single issue detail, with employee context and a back-to-queue return point.
- The user can opt to remember a rule only through the existing intentional scope controls. The UI must explain “this occurrence” versus “this employee/company” scope before save.

### Employee detail and financial explainability

Purpose: let the user verify a number without creating another calculation path.

Use a two-column layout: employee/period/status at top; financial table on the left and evidence/issue panel on the right. Each row displays Thai field name, final value, unit, category (`automatic`, `recurring`, `manual`, `review required`), and review state. Detail shows source, prior value, override, final value, rule/reason and linked issue only where those values exist.

For **เบี้ยขยัน**:

- label the internal field once as `bonus` in technical/evidence context only, not as user-facing “bonus”;
- state whether the amount comes from confirmed attendance-bonus default, approved cut/custom result, or an explicit field override;
- list the relevant calendar/leave review requirements without deciding them in the UI;
- show **โบนัสพิเศษ** separately as a manual field.

This resolves the audit’s financial-presentation risk without changing the correct existing mapping.

### History

Purpose: answer who changed what, when and for which period.

Phase D UI can initially present the current audit history more clearly with period/state context and a selected-row detail drawer only if the supplied row has the required data. Month/action/actor filters and event detail must be implemented only after a minimal repository/service query supports them efficiently and truthfully. No client-side claim that an unreturned detail exists.

### Problems and recovery

Purpose: make operational failures recoverable without offering unsafe shortcuts.

Show separate panels for runtime health, source/configuration health, current background-job summary, and copy-write availability. Each panel has: state label, last known context/time where available, concise explanation, and one safe action (open settings, review items, open copies, retry identified job when supported). Preserve logs for technical detail. A stale notification alone is not the primary record.

### Settings

Purpose: configure workflow prerequisites without changing payroll or runtime state unexpectedly.

Group the existing fields into:

1. **Workflow folders and monthly template** — attendance folder, payroll folder, template, copy-only hint.
2. **Start with Windows** — checkbox, validation state, repair action, independent-state explanation.
3. **Monitoring** — a read-only current preference/status explanation with “Use tray menu to pause or resume monitoring.”

Save result language must be precise. On external Task Scheduler failure: “Folder/template settings were saved. Windows start was not changed. Monitoring was not changed.” The user must remain able to correct settings or retry/repair. Save must never cause a paused watcher to start or create a duplicate watcher.

## Component catalogue

| Component | Required behaviour | Existing contract preserved |
| --- | --- | --- |
| App shell/sidebar | Page routing with current-page selection, keyboard focus and compact mode | Window lifecycle and lazy creation remain outside widgets. |
| Context bar | Page title, period, refreshed-at time and independent status cluster | No mutation merely from navigation. |
| Status pill | Icon + text + token for one named state | Does not use colour as sole information. |
| Summary card | One metric/status, supporting text, optional safe link | No hidden state transition. |
| Primary action panel | Explains prerequisite and presents one next safe action | Existing state gates and service calls remain authority. |
| Source-copy card | Path/name, timestamp, validation/safety label, open action | Copy-only path validation remains in service/safety layer. |
| Review queue row | Identity, issue/evidence summary, severity, CTA | Existing issue/decision data and reason requirement. |
| Financial detail table | Thai label, unit, final value, category, status | Calculator values are shown, not recalculated. |
| Evidence drawer | Source/previous/override/final/reason information | Read-only evidence; mutations go through existing dialogs/services. |
| Guarded confirmation dialog | Explicit consequence, period, required reason/acknowledgement where current flow requires it | Confirm/reopen/lock/write invariants unchanged. |
| Inline outcome banner | Success, error, partial success or recovery next action | Never masks partial failure as success. |
| Empty/loading panel | Contextual setup/no-draft/processing explanation | Prevents duplicate commands and stale-data implication. |

## Qt implementation architecture

Phase D should evolve `MainWindow` from a vertically assembled command page into a shell containing a sidebar/navigation controller and a `QStackedWidget` (or similarly explicit page host). This is a presentation refactor only:

```text
WindowController (lazy window ownership)
  └─ MainWindow (presentation coordinator)
      ├─ AppShell / navigation
      ├─ OverviewPage
      ├─ ReviewQueuePage
      ├─ HistoryPage
      ├─ ProblemsPage
      ├─ SettingsPage
      └─ existing service/runtime adapters

AutomationRuntime ─── owns watchers, jobs, recovery and monitoring state
PayrollService   ─── owns payroll transitions/current draft
Repository       ─── owns persisted data/audit/query access
Writer/Safety    ─── owns copy-only write validation
```

Rules:

- Existing `AutomationRuntime`, `PayrollService`, `WorkflowService`, writer, repository and safety services remain injected dependencies. Pages do not instantiate parallel runtime/watchers or compute payroll values.
- Keep UI mutations on the Qt GUI thread. Existing background job signalling remains the pattern for long operations.
- Extract view models/presenters only for formatting and UI state derived from existing data. Do not put state-machine transitions, SQL, calculation, file validation or Task Scheduler calls in widgets.
- Preserve `WindowController`, tray callbacks, `SingleInstance` behaviour and close/shutdown coordination. Navigation routing must not assume a window exists until the controller creates it.
- Centralise QSS/tokens in a theme module or asset. Widgets must not accumulate competing inline stylesheets.
- Keep compatibility adapters during staged migration where test coverage relies on current entry methods (`review`, `settings`, `history`, `open_copy`). Remove them only after tray and tests move to the new page contract.

## Delivery roadmap: Phase D.1–D.7

Each phase is a proposed future implementation session set, not work completed by D.0. Every phase must preserve application behaviour, run the full relevant regression suite, and receive focused UI tests before moving on.

| Phase | Scope and deliverables | Likely UI/components | Required validation and risks |
| --- | --- | --- | --- |
| D.1 — Shell and tokens | Introduce theme tokens, typography, app shell, sidebar/drawer and safe page host; retain existing main-page content through a compatibility page. | New theme module, `MainWindow`, shell/sidebar components. | Smoke test/tray launch/close/lazy-window tests; high risk: breaking tray callbacks or DPI layout. |
| D.2 — Overview | Build overview status cluster, next-action panel, source-copy card, summary cards and revised employee table labels. | `OverviewPage`, table formatter/presenter. | State-gating snapshots/unit tests for DRAFT through LOCKED; verify no action resumes watcher; risk: stale UI after async result. |
| D.3 — Review workflow | Move Review Centre and employee detail into a queue/detail presentation while preserving DecisionDialog contracts and reasons. | Review queue/detail components, existing review dialogs/adapters. | Decision persistence/scope/reason, unresolved/ready transitions, Thai evidence display; risk: hiding critical issue context. |
| D.4 — History and period lifecycle | Present history coherently; place reopen/lock in period context; add only minimal read query support required for truthful filters/details. | History page, period detail/reopen components, perhaps repository read method. | Audit/reopen/revision/lock regression tests; risk: accidental broader schema/query redesign or misleading history. |
| D.5 — Problems and recovery | Add runtime/configuration/job health surface and safe recovery links. Expose retry only with an identified persisted job and existing runtime path. | Problems page, runtime-status adapter. | Watcher health/restart/job-recovery tests with fakes; risk: duplicate watcher or unbounded retry UI. |
| D.6 — Settings and first run | Redesign settings/first-run UI around independent Windows start and monitoring concepts, precise partial-success feedback and repair. | Settings page/adapters, `SetupWizard` presentation. | Fake Task Scheduler, paused/active/no-duplicate watcher, first-run preference and external failure tests; risk: regression of C.1 safety boundary. |
| D.7 — Polish, accessibility and release verification | Keyboard/accessibility pass, high-DPI layout, consistency, help text, documentation and visual regression/manual QA checklist. | Cross-page fixes, theme polish, tests/docs. | Full units, smoke test, compile, diff check, manual checklist; risk: late style changes concealing state or breaking focus. |

### Suggested dependency order

```text
D.1 shell/tokens
  └─ D.2 overview
       ├─ D.3 review/detail
       ├─ D.4 history/lifecycle
       └─ D.5 problems/recovery
             └─ D.6 settings/first-run
                   └─ D.7 accessibility, polish and release validation
```

History and Problems can be implemented in either order after D.2, provided their new data/query requirements are reviewed separately. Settings should follow once the shell/status language is established, and must explicitly rerun the Phase C.1 regression matrix.

## Test strategy

### Automated UI/service boundary tests

- Existing test suite remains mandatory. Add focused tests for page action enablement across DRAFT, NEEDS_REVIEW, READY, CONFIRMED, WRITTEN and LOCKED.
- Verify Overview navigation/open/close does not call `resume_monitoring`, does not mutate `watch_enabled`, and does not create a watcher.
- Verify only explicit tray Resume invokes runtime resume path; use runtime/watcher fakes and assert no duplicates.
- Verify Settings Save with a fake Windows Task Scheduler preserves paused/active monitoring, reports partial success on installation/removal failure, and never performs real Task Scheduler operations.
- Verify employee table/detail labels and units: `bonus` displays as เบี้ยขยัน; `special_bonus` remains separate; OT is hours; special-items count is not formatted as currency.
- Verify decision and profile controls still require/record reasons and respect one-time versus remembered scope.
- Verify copy-only writer gating, reopen acknowledgement/reason, revision conflict handling and lock restrictions from UI entry points.
- Verify tray shortcuts continue to create/restore the window safely and route to the intended page/dialog.

### Visual/manual acceptance

- Check 100%, 125%, 150% and 200% Windows scaling on a Thai Windows locale where possible.
- Keyboard-only pass: launch, sidebar, table, detail, dialog, save/cancel and return focus.
- Contrast/state pass for normal, hover, selected, disabled, warning/error, focus and empty/loading conditions.
- Inspect narrow-window behaviour and table scrolling; no clipped Thai text or hidden primary action.
- Run copy-only workflow with a test fixture only. Confirm source/original workbook is never offered as a write target.

### Release commands for every implementation phase

```powershell
python -X utf8 -m pytest tests/unit -q
python -X utf8 -m app.main --smoke-test
python -X utf8 -m compileall -q app
git diff --check
```

Run integration tests when the changed workflow has applicable coverage. UI documentation-only work (D.0) needs no production/Excel operation and must not create/delete Scheduled Tasks.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| A visual refactor changes lifecycle behaviour. | Preserve controller/tray entry methods behind adapters; test lazy creation, close and exit explicitly. |
| UI duplicates payroll logic to populate cards/details. | Use service-returned draft values and presentation-only view models. |
| Status cards imply a relationship between monitoring and Windows start. | Render separate labels/sources, test every combination, and retain tray-only explicit resume semantics. |
| “Problems” page exposes unsafe or vague recovery actions. | Bind only to existing safe commands with identity/preconditions; hide unsupported actions. |
| More history filters require expensive/untruthful client behaviour. | Define/benchmark a narrow repository query before adding UI controls. |
| Dense Thai labels clip or lose accessibility. | Tokenised typography, adaptive layouts, keyboard/focus tests and high-DPI manual checks. |
| Financial presentation is cosmetically clearer but semantically wrong. | Preserve field mapping and sources; add explicit tests for เบี้ยขยัน/โบนัสพิเศษ and units. |
| Styles are scattered and regress later. | One token/theme layer with named components and review of inline QSS additions. |

## Definition of done for Phase D implementation

- All five navigation destinations have a clear purpose and route from supported tray/main-window entry points.
- Overview states the selected period, payroll state, next safe action, monitoring state, Windows-start state and copy-only boundary independently.
- Review and employee detail preserve all source evidence, reasons, scopes and approval gates.
- No UI operation creates a watcher directly, resumes paused monitoring through Settings/navigation, or bypasses runtime validation.
- No application code writes to a production original; all existing safety tests continue to pass.
- High-DPI, keyboard and non-colour state requirements are verified.
- Every implementation phase is committed as scoped work and pushed only after its complete validation, following the project Git workflow.
