# Controlled Payroll UAT — Synthetic Test Plan

## Purpose and boundary

This plan defines controlled UAT evidence for the payroll application without
using any real employee, company, historical, or reference-workbook data.  It
does not authorize production activation, a production write, automatic
monitoring, Windows Task Scheduler changes, or a change to payroll policy.

Every artefact created by this plan must be below
`test_workspace/uat_synthetic/`.  The session must neither read from nor copy
from `reference_data/`, `test_workspace/uat_month8/`,
`test_workspace/app_state/`, or `test_workspace/qa_sessions/manual_ui/`.
The existing `--qa-ui` presentation fixture is deliberately out of scope: it
has no real Excel writer and therefore is not Excel UAT evidence.

## Fixture contract

The fixture generator creates new, fictional workbooks from code:

| Artefact | Contract |
| --- | --- |
| Attendance workbook | Literal daily rows, unique synthetic identities, and reader-recognised Thai headers.  It is parsed by `read_attendance()`; no mocked reader is permitted. |
| Payroll workbook | A new workbook with the exact label/layout contract accepted by `PayrollWorkbookAdapter.read()`, including genuine formula cells and their independently asserted inputs. |
| Payslip workbook | New synthetic payslip sheets with the exact labels and merged section headers accepted by `PayslipAdapter`; no copied payslip is permitted. |
| Database/configuration | A fresh SQLite database and an explicit workflow configuration under the UAT root.  It starts with monitoring disabled. |
| Output/backup/log folders | New folders below the UAT root only.  Tests assert their resolved paths remain there. |

The fixture may use fictional names only: **Arun Demo**, **Bua Example**, and
**Chai Fixture**.  Test reports contain identifiers and aggregate expected
values only; they must not contain cells, names, paths, or evidence copied from
any source workbook.

## Evidence levels

`PASS` means an automated assertion met the stated criterion.  `BLOCKED` means
the system correctly prevented the action.  `USER_REVIEW_REQUIRED` means a
deliberately unresolved policy or source decision was surfaced; it is not
converted into an invented amount.  `NOT VERIFIED` is used when a native Excel
or manual review action is unavailable.

The implementation's established rules are tested as implementation behavior,
not as an approval of company policy.  In particular, salary, OT money,
holiday money, tax, social security, total income, and net-pay formulas are
read from the approved payroll workbook formula/cached-value contract.  This
UAT will not invent statutory rates, rounding, deductions, or any financial
formula not already represented by the synthetic fixture.

## Case matrix

| ID | Scenario | Expected evidence / acceptance criterion |
| --- | --- | --- |
| E-CALC-01 | Clean normal workdays | `read_attendance()` preserves the daily evidence and returns exact literal travel/allowance and OT-hour subtotals; `PayrollService.prepare()` produces the expected fictional roster only. |
| E-CALC-02 | Normal OT | An explicit normal-OT decision is required before the draft can be ready; the stored hours match the independent `Decimal` fixture total. |
| E-CALC-03 | Holiday work and holiday OT | A confirmed synthetic calendar/decision supplies the classification; hours/days are recorded exactly.  No rate is inferred beyond workbook formulas. |
| E-CALC-04 | Leave affecting attendance bonus | A leave event needs an explicit allowed leave type and explicit bonus consequence.  The resulting bonus matches the selected fixture decision, not a guessed rule. |
| E-CALC-05 | Recurring values | Effective-dated values may recur only after the applicable confirmation; a missing recurring value creates a review item. |
| E-CALC-06 | One-time deductions | Advance, loan, damage, adjustment and comparable manual fields are never silently carried into the new period. |
| E-CALC-07 | Formula-derived output | The generated workbook's formula cells and input cells are inspected through the real adapter; values are compared with an independent fixture expectation where the fixture defines the formula. |
| E-REV-01 | Missing employee identity | An unmatched attendance/payroll identity is a blocking review issue.  No employee is automatically matched by a partial name. |
| E-REV-02 | Duplicate attendance / incomplete source | Duplicate date, missing day, invalid value, or formula-only daily evidence remains review/blocking evidence; it is never silently zeroed or deduplicated. |
| E-REV-03 | Unclassified OT, calendar and leave | The draft cannot become `READY` or `CONFIRMED` while any required decision is unresolved. |
| E-REV-04 | Confirm only after resolution | Confirmation requires `READY`, the expected revision and unchanged source hashes; the audit log records the explicit transition. |
| E-WRITE-01 | Preflight and backup | The writer preflight accepts only the generated workbook and mappings.  A byte-verified backup exists before a write attempt. |
| E-WRITE-02 | Safe generated output | Writes are confined to the generated payroll and payslip files below the UAT root.  Formula/layout/style fingerprint checks pass except at approved writable cells. |
| E-WRITE-03 | Invalid destination / changed source | A reference/outside destination, unexpected source hash, invalid mapping, or structural change is blocked before COM/Excel mutation. |
| E-WRITE-04 | Reopen/retry safety | A failed or staged write does not claim success.  Retry and reopen need explicit actions; no duplicate write or inconsistent payroll state is produced. |
| E-STATE-01 | State machine | Expected progression is `DRAFT` → `NEEDS_REVIEW`/`READY` → `CONFIRMED` → `WRITTEN` → `LOCKED`; prohibited shortcuts are rejected. |
| E-STATE-02 | Post-confirm change | A changed source/hash blocks confirmation or write until an explicit safe workflow action; it never overwrites the prior evidence. |
| E-SAFE-01 | Isolation and monitoring | All resolved artefacts are inside `uat_synthetic`; monitoring remains disabled and no watcher, scheduler, QA session, real Excel input, or production destination is used. |
| E-SAFE-02 | No production mutation | Reference hashes/inventory and normal/QA state paths are unchanged before and after the synthetic run. |

## Independent expected-results method

For each golden case, the fixture module declares literal `Decimal` inputs and
an expected result table separately from the production calculator call.  The
test compares reader evidence, persisted draft fields, review issues and
adapter-visible workbook cells against that table.  Tests do not copy values
from a historical workbook and do not assert a business rule merely because a
production function returned it.  Where the system intentionally delegates a
money calculation to workbook formulas, the fixture formula is stated in the
test and its inputs/output are inspected; the test labels it
`FORMULA_DERIVED`, not an independent payroll-policy approval.

## Exit criteria

Phase E is complete only when all case IDs above have recorded PASS/BLOCKED as
appropriate, all unresolved behavior is explicitly marked
`USER_REVIEW_REQUIRED` or `NOT VERIFIED`, the full unit suite/smoke/compile
checks pass, and a final synthetic UAT report names every limitation.  A PASS
does **not** authorize production payroll, real employee data, production
writing, or a Phase F/G change.
