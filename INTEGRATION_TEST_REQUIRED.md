# Excel integration safety and validation

The original Phase 1–2 checkpoint used saved XLSX bytes only. Phases 6–10 now contain a real isolated Excel COM writer and integration tests. Local validation reports are intentionally excluded from version control because they may contain payroll information.

All write targets, backups and test databases must resolve below `test_workspace`. Never target `reference_data`, the currently open real Month 8 workbook, or another user's Excel instance. DispatchEx ownership must be verified by PID and creation time before application properties are changed. Only explicitly opened copies may be closed. Quit only the application's isolated empty instance. Never kill EXCEL.EXE or use GetActiveObject.

The integration suite checks verified backups before writes, dynamic January/March payroll headers, intended inputs, isolated CalculateFull/Save/reopen, formulas, styles, merged cells, dimensions, print settings, existing payslip labels and totals, partial/all coverage, no-op repeats, rollback, locked/protected source changes and exact travel-delta propagation.

Run on this Windows/Excel host:

```powershell
python -X utf8 -m pytest tests/integration -m excel_com -v
```

Python 3.14/pywin32/Office cleanup has emitted handled native RPC diagnostics in pytest's faulthandler output. Passing exit status and post-write checks are recorded alongside these diagnostics; they must not be hidden or presented as a clean production certification. The application remains copies-only pending manual acceptance and investigation on the chosen deployment environment.

Startup scripts are parsed only during tests and never registered automatically. No production activation is part of this implementation.
