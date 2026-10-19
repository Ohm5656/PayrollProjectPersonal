# Phase E.6 Native Excel COM Report

## Environment

- Windows 11 build 26200; Python 3.14.3 (64-bit); pywin32 available.
- Microsoft Excel Desktop COM version: **16.0**.
- Before each run no `EXCEL.EXE` existed. `ExcelGateway` used `DispatchEx`,
  recorded an owned PID/creation identity, and exited it cleanly. No active
  user-owned QA process was controlled.
- Each run used a new `test_workspace/uat_synthetic/<unique>` root, database,
  workbook, backup and lifecycle log. No reference or normal/QA DB input was
  used.

## Native results

| Case | Actual evidence | Result |
| --- | --- | --- |
| E6-A single employee | `write_employee_copy()` opened/saved/reopened a synthetic workbook through owned Excel; selected income/net recalculated to 33,100 / 32,200; other employee input cells unchanged | PASS |
| E6-B monthly write | `write_month()` completed through owned Excel; all three synthetic rows recalculated to income 33,100 and net 32,200; state `WRITTEN` and audit recorded | PASS |
| E6-C structure/formulas | `WorkbookStructure` before/after validation passed; formulas/styles/settings unchanged except approved values/caches | PASS |
| E6-D backup/lifecycle | SHA-256 backup matched pre-write target; lifecycle log was retained inside the unique UAT root; owned Excel exited | PASS |
| Native fault interruption | no destructive interruption attempted; existing isolated fault injection remains evidence | NOT VERIFIED |

## Defect corrected

The synthetic payslip payment-date cell was initially a general-format string.
Excel `Value2` legitimately serialised its replacement date as a number, while
the validator expected a date. The fixture now supplies a real date with
`yyyy-mm-dd` format, matching the production writer contract. This changed no
payroll policy or production workbook.

## Deferred final acceptance

Phase D native UI/tray/keyboard/startup checks, business-owner validation of
all payroll policies, real-data copy-only permission, packaging and production
activation remain pending. Native COM evidence is technical only.
