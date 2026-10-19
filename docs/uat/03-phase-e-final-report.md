# Phase E Final Synthetic Payroll UAT Report

## Environment and boundary

- OS: Windows; Python: project `.venv`; Git baseline: `d131505`.
- Fresh fixture/database/output roots: `test_workspace/uat_synthetic/<unique>/`.
- Inputs: newly generated fictional workbooks for Arun Demo, Bua Example and
  Chai Fixture only. No `reference_data`, normal DB, QA DB or `uat_month8`
  content is used as a UAT input.
- Excel COM: **NOT VERIFIED**. No native Excel process was launched or
  controlled; the active user-owned `--qa-ui` process was not touched.

## Evidence summary

| Area | Result |
| --- | --- |
| Actual attendance reader, payroll adapter and payslip adapter | PASS |
| Normal, October, invalid and review-required synthetic inputs | PASS |
| Golden values (travel 300, allowance 600, bonus 1,000, income 33,100, net 32,200) | PASS; formula-derived where applicable |
| OT, holiday work/OT, leave bonus decisions, identity/review gates | PASS |
| Revision/source-change/confirm/reopen/lock guards | PASS |
| Isolated write-plan, payslip preflight, hash/backups/recovery evidence | PASS |
| Native COM recalculation, native output format/structure after COM write | NOT VERIFIED |
| Business-owner payroll-policy approval | PENDING |

Full unit suite: **313 passed in 372.24s**. The normal `--smoke-test` was not
run because its documented non-QA route may migrate/import the persistent
development database. `compileall`, focused Phase E tests and `git diff
--check` are run as final safe validation.

## Business-owner acceptance worksheet

Before any real-data copy-only UAT, payroll owner must explicitly approve:

- employee identities and effective base salary;
- normal/holiday OT rate and rounding formulas;
- calendar/leave/attendance-bonus policy;
- allowances, deductions, tax and social-security rules;
- payslip totals, monthly totals, backup/restore procedure and a native Excel
  test on a dedicated approved copy.

Synthetic tests do not establish real-company payroll accuracy or production
authorization.

## Decision

Synthetic automated UAT is complete. Native Excel output and business-owner
approval remain separate gates. Production activation remains prohibited.
