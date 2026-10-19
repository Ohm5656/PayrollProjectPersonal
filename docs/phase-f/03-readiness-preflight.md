# Readiness Preflight

`ReadinessService` reports assessment only: copy-only boundary, workflow paths,
read-only SQLite integrity/schema evidence, disk space, monitoring state and an
injected owned-Excel probe. It never creates `Database()` for a normal path,
imports history, changes settings, resumes monitoring, installs startup, or
changes `development_target()` permissions.
