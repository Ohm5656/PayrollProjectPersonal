# Runtime Reliability and Operational Recovery

The existing runtime remains the sole watcher owner. Existing deterministic
tests cover debounce, locked-save handling, idempotent hashes, durable job
claims, retry/reconciliation, watcher supervision, pause/shutdown suppression,
single-instance restore, tray lifecycle and mocked startup inspection.

Phase F adds no second watcher, scheduler or retry loop. Monitoring remains
paused unless an explicit existing resume action is used; settings/preflight
are observational. Ambiguous workbook writes remain recovery-required rather
than retryable automatically.

Operator-visible states remain: paused, processing, review required, failed,
recovery required and validated write. Logs carry job/operation identifiers and
timestamps; reports must not contain real workbook contents or payroll values.
