# Packaging Architecture

PyInstaller onedir packages immutable application code/QSS/SVG resources next
to the frozen executable. Candidate writable state is a fresh, explicit
synthetic sandbox below `test_workspace`; it is not `%APPDATA%` production
state and cannot weaken `development_target()`. Reference workbooks, history,
reports and existing workspaces are excluded. Excel remains an external Desktop
COM prerequisite. Packaged startup remains disabled; an installed-EXE startup
task is future separately-approved work.

Resources are resolved from the frozen bundle, never current working directory.
State, logs, SQLite, IPC and staging must be candidate-scoped and disposable.
Uninstall preserves persistent data; package upgrade/rollback must not alter
database/schema state without an explicit future migration policy.
