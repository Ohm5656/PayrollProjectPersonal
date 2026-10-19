# Phase G Packaging Handoff

Entry point: `python -m app.main`. Package Python, PySide6, openpyxl, pywin32,
Qt assets and application modules; retain writable state under approved paths,
SQLite migrations, single-instance IPC, tray lifecycle and explicit startup
design. Installer work must preserve data, support rollback/uninstall, and
must not change `development_target()` or activate production writes.
