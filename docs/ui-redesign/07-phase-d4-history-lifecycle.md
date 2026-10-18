# Phase D.4 — History and payroll-period lifecycle

## Scope

Phase D.4 replaces the legacy modal History view with an embedded, read-only
page in the existing application shell. It does not change the payroll state
machine, calculation rules, audit persistence, Excel templates, or runtime
monitoring behaviour.

## History architecture

`Repository` remains the only database access layer. Its new audit read APIs
query `audit_log` with parameterized SQL:

- `audit_events()` returns a bounded, descending-ID page using an optional
  `before_id` keyset cursor.
- `audit_event_count()` returns the matching total.
- `audit_event()` obtains one stable event identity for the detail page.
- `audit_filter_values()` supplies the filter choices.

The filters (year, month, action, and actor) are applied to every database
query. The page never loads the whole audit log merely to paginate it. Existing
`audit_history()` is unchanged for compatibility.

`HistoryViewModel` converts persisted audit fields to presentation values only.
It displays timezone-aware UTC ISO timestamps in Asia/Bangkok time and uses
Buddhist Era years for user-facing period labels. JSON is decoded only when it
is valid; `NULL`, an empty field, zero, a plain string, malformed JSON, lists,
and objects remain distinguishable. No model writes to the database.

`HistoryPage` owns filters, keyset pagination, empty/error states, stable event
IDs, double-click inspection, and Enter-key inspection. `HistoryDetailPage`
shows the exact selected payload with a timeline containing only audit events
actually recorded for that period. It does not infer missing lifecycle steps.

## Navigation and privacy

Sidebar and tray History both call `MainWindow.history()`, which opens the
embedded page. Selecting an event changes only presentation state. It does not
prepare a draft, calculate payroll, confirm, reopen, write Excel, alter audit
records, or resume monitoring.

An event's period is not selected automatically. The user must choose **Open
this payroll period**. That changes only the visible period selector and opens
Overview; it does not perform a payroll action.

## Guarded period lifecycle

Reopen and Lock retain the existing `PayrollService` APIs and service-side
validation. Before either UI action, `MainWindow` reads the currently selected
year/month and reloads the persisted run. A stale displayed `self.run` or a
background result for another period therefore cannot redirect the action.

Reopen is available only for existing final states and still requires viewing
the recorded source-difference evidence, explicit acknowledgement, and a
non-empty reason. If no recorded differences exist, the UI says so without
claiming that a source comparison was performed. A successful reopen reloads
the persisted period and refreshes Overview, Review Queue, History, and action
availability. It never recalculates, confirms, or writes Excel automatically.

Lock is offered only for a freshly reloaded `WRITTEN` run, requires an explicit
confirmation dialog, then calls `PayrollService.lock()`. A service rejection is
reported without claiming success. After a successful lock the same read-only
views refresh and the normal state-driven controls update.

## Visual QA and limitations

Automated offscreen checks exercise History layout at 1366×768, 1920×1080,
and 900×700, keyboard selection, detail navigation, explicit period selection,
and read-only behaviour with synthetic audit data. Offscreen automation cannot
replace an interactive Windows rendering review; Thai clipping, native focus
appearance, and tray interaction still require that manual check.

Timeline results are intentionally bounded to the most recent 100 recorded
events for a selected period. This preserves UI responsiveness but means an
exceptionally long period history is not a complete archival export.
