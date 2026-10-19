# Excel Writing, Payslip and Recovery — Synthetic Results

## Scope and method

The test target is a newly generated workbook under
`test_workspace/uat_synthetic/<unique>/payroll_output/`. It is never a copy of
`reference_data` or a normal/QA workbook. The actual `build_plan()`,
`PayslipAdapter`, `PayrollWriter`, `BackupService`, hash validation and staging
paths are exercised. The gateway is a failure-injection substitute: no Excel
COM process is created or inspected in this session.

## Result matrix

| Case | Expected evidence | Result |
| --- | --- | --- |
| E-WRITE-01 | only generated target, approved state and matching source hash form a plan | PASS |
| E-WRITE-02 | payroll-cell writes remain on the calculation sheet; payslip adapters recognise every fictional person | PASS |
| E-WRITE-03 | changed generated target fails `build_plan()` before write | PASS |
| E-WRITE-04 | unconfirmed month fails `write_month()` and stale expected revision fails confirm | PASS |
| E-RECOVERY-01 | backup is created before gateway entry, backup SHA-256 equals original target | PASS |
| E-RECOVERY-02 | gateway failure leaves target SHA-256 unchanged and retains verified backup | PASS |
| E-RECOVERY-03 | failure retains the isolated staged copy as recovery evidence; it is not marked successful or auto-restored | PASS |
| E-COM-01 | native Excel recalculates and output structure/format is verified | NOT VERIFIED |

The fault-injection case deliberately leaves its staged copy inside the unique
synthetic workspace. This is appropriate recovery evidence for an ambiguous
operation: the code does not silently delete, restore, or mark it successful.

## Integrity status

- Payroll formula cells are treated as protected by `build_plan()`; proposed
  results must equal arithmetic preview rather than overwrite those formulas.
- The payslip adapter validates exact fictional full-name identity and the
  mapped values before a write plan is allowed.
- A native COM write, post-recalculation cached values, Excel-native style
  preservation and final `WorkbookStructure` comparison are **NOT VERIFIED**.
  They require an explicit future run with Microsoft Excel available, against a
  dedicated synthetic copy, and without controlling any unrelated Excel
  process.
