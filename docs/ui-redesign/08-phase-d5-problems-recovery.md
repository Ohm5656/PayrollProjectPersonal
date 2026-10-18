# Phase D.5 — Problems and Recovery

## Architecture and data sources

Phase D.5 replaces the Problems placeholder with an embedded `ProblemsPage`.
It remains a presentation and controller surface: it neither owns a watcher nor
implements a second job engine.

`ProblemsViewModel` reads only authoritative services:

- persisted `watch_enabled` and the optional `AutomationRuntime` state/health;
- a bounded maximum of 50 persisted automation jobs through
  `AutomationJobService.latest()`;
- `WorkflowService` configuration and safe filesystem availability checks;
- `AutomationJobService.staged_write_inspection()` for recorded `STAGED` write
  operations.

Monitoring, jobs, configuration, payroll review, and staged Excel writes are
separate health domains. A user-paused watcher is shown as intentional pause,
not an error. A review-required job is not presented as a watcher failure.
When runtime data is unavailable, the page says that status cannot be verified;
it never substitutes a green success state.

## Jobs, failures, and details

The recent-job table is bounded and uses the persisted job ID as its stable
identity. It shows state, period, updated time, and a short explanation. The
detail page reads that job again by ID and shows its recorded attempt count,
failure code, and a safe filename only; it does not expose a clickable arbitrary
filesystem path or source content.

Known persisted failure codes receive Thai guidance for `SOURCE_MISSING`,
`SOURCE_INVALID`, `SOURCE_CHANGED`, `SOURCE_CHANGED_OFFLINE`,
`CONFIGURATION_CHANGED`, and `INTERRUPTED`. Unknown codes retain their recorded
message and receive a neutral explanation rather than a fabricated diagnosis.

## Staged Excel writes

The staged-write view is strictly inspection-only. It reports operation ID,
safe target-existence evidence, backup validity, and recorded classification.
It has no restore, resume, overwrite, delete-backup, or mark-success action.
Those actions require a separately designed recovery policy because a staged
operation is not evidence that a final Excel write succeeded.

## Guarded retry

Retry is available only from a selected persisted `FAILED` job and requires a
confirmation dialog. The UI calls the existing `AutomationRuntime.retry_job()`
inside the application's existing background work wrapper, so the Qt GUI event
loop remains free. Completion callbacks return to the GUI thread through the
existing job signals.

Before enabling retry, `AutomationRuntime.retry_eligibility()` checks job state,
shutdown state, active processing, supported job type, current configuration,
and a cheap approved-source boundary check. `retry_job()` repeats the source
boundary check, validates the source hash through `retry_source()`, revalidates
configuration, and atomically claims the persisted job. The service remains the
authority and can still reject a race or stale state.

Manual jobs now store `attendance_path` in newly created contexts. Historical
manual jobs use their persisted `source_path` as a compatibility fallback.
Both pending and retry paths compare the current manual attendance/payroll/year/
month configuration before preparing any draft.

Changed source bytes produce a separate pending replacement job. The UI reports
that a replacement was created and explicitly does not call it a successful
retry. Retry never confirms payroll, approves review issues, writes final Excel,
locks/reopens a period, restores a backup, creates a watcher, or resumes paused
monitoring.

## UI and visual QA

Sidebar Problems opens the embedded dashboard; job and staged-write details
remain in the same `MainWindow` stack. Existing tray actions are unchanged.
Opening Problems only performs bounded read-only queries.

Automated offscreen checks cover 1366×768, 1920×1080, and 900×700, including
long-safe detail areas, status filtering, stable identity, staged-write display,
explicit retry routing, and the changed-source outcome. These do not replace
interactive Windows testing of native focus, tray behaviour, DPI scaling, and
Thai text clipping.

## Remaining work

The page intentionally does not provide automated Excel repair. Future work is
D.6 Settings and First Run, D.7 final accessibility/visual polish, then UAT,
production activation, and packaging.
