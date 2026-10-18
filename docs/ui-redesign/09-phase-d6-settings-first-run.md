# Phase D.6 — Settings & First-Run Setup

## Delivered

- Settings is an embedded page; sidebar and tray routing use the same page.
- Workflow folders and the monthly template are validated by the existing
  `WorkflowService` before they are persisted. The page neither creates
  folders nor opens or writes an Excel workbook.
- Monitoring is displayed as a read-only runtime/preference state. Saving
  Settings calls `AutomationRuntime.reconfigure()` only after a valid folder
  save; it never calls `resume_monitoring()` and therefore preserves the
  persisted `watch_enabled` value (`None`, `False`, or `True`).
- Windows startup is independent. Its Task Scheduler status is cached in the
  view model and refreshed only by an explicit page refresh/save action.
  Install/remove is requested only by an explicit saved checkbox change;
  repair is a separate button and is never inferred from Save.
- If the workflow save succeeds but a startup operation fails, the page says
  that the folders were saved and reports the remaining startup failure.
- First-run setup shows an explicit monitoring choice. A pre-existing paused
  preference is disabled in the wizard and cannot be silently overridden.

## Safety boundary

The page uses the established development validation path. It remains limited
to `test_workspace` copies and does not enable production output, alter payroll
calculation, confirm a payroll period, or create/delete a real scheduled task
in automated tests.

## Verification focus

Tests cover paused and active monitoring, duplicate watcher prevention,
partial startup failure, explicit repair, dirty navigation, tray routing,
first-run preference persistence, and unsafe workflow rejection.
