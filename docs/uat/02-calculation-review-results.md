# Calculation, Review and Confirmation — Synthetic Results

## Method

Each case creates fresh attendance and payroll `.xlsx` files and a new SQLite
database below `test_workspace/uat_synthetic/`. The actual
`read_attendance()`, `PayrollWorkbookAdapter.read()`, `PayrollService.prepare()`
and `PayrollService.confirm()` implementations are used. No historical
workbook, employee, database or `--qa-ui` artefact is an input.

All monetary expectations below are literal `Decimal` fixture facts. Workbook
formula previews are tested against the stated synthetic formula; this does
not approve a real-world salary, tax, OT-rate or deduction policy.

## Implemented-field inventory

| Field | Thai display | Source / implemented rule | Review condition | UAT coverage |
| --- | --- | --- | --- | --- |
| `base` | เงินเดือน/ค่าจ้าง | confirmed base profile, effective recurring value, or explicit decision | no confirmed value | profile/golden case |
| `normal_ot`, `holiday_ot`, `holiday_days` | OT ปกติ, OT วันหยุด, ทำงานวันหยุด | exact attendance hours/days after explicit classification | unclassified OT/holiday | OT gate |
| `normal_money`, `holiday_money`, `holiday_ot_money` | เงิน OT/วันหยุด | existing supported payroll-sheet arithmetic only | unsupported/unknown formula | formula-preview golden case |
| `bonus` | เบี้ยขยัน | confirmed profile plus complete calendar/leave decisions | missing calendar, leave or bonus decision | profile/full-entitlement case |
| `travel`, `allowance` | ค่าเดินทาง, เบี้ยเลี้ยง | complete literal daily attendance subtotal | incomplete/invalid source | golden case |
| `phone`, `position`, `housing` | ค่าโทรศัพท์, ค่าตำแหน่ง, ที่พัก+ค่าน้ำ+ไฟ | recurring/effective/profile values | no explicit source | profile case |
| manual fields | เงินเบิก, เงินกู้, ภาษี, ประกันสังคม, โบนัสพิเศษ และรายการอื่น | never silently carried; explicit value/decision only | missing decision | existing regression suite, business sign-off still needed |
| `income`, `net` | รวมเงินได้, รายได้สุทธิ | preview of the fixture's own protected formula | formula cannot be safely evaluated | golden case |

`tax`, social security, formula rates, rounding and statutory/company policy
remain **BUSINESS_RULE_REVIEW_REQUIRED**. The product deliberately does not
invent them from a template label.

## Golden calculation comparison

| ID | Input / approved synthetic rule | Expected | Actual | Result |
| --- | --- | ---: | ---: | --- |
| E-CALC-01 | 30 days × travel 10 | 300 | 300 | PASS |
| E-CALC-01 | 30 days × allowance 20 | 600 | 600 | PASS |
| E-CALC-01 | confirmed profile attendance bonus | 1,000 | 1,000 | PASS |
| E-CALC-01 | confirmed base/phone/position/housing | 30,000 / 500 / 700 / 900 | same | PASS |
| E-CALC-01 | no approved OT/holiday units | 0 / 0 / 0 | same | PASS |
| E-CALC-01 | synthetic existing formula, after zero OT | income 33,100; net 32,200 | same | PASS |
| E-CALC-02 | 2 literal OT hours + explicit `NORMAL` decision | normal OT 2; holiday OT 0 | same | PASS |

Formula totals are `FORMULA_DERIVED`; the result proves the protected
synthetic formula preview and inputs, not a business approval of an amount.

## Review and confirmation results

| ID | Scenario | Expected | Actual | Result |
| --- | --- | --- | --- | --- |
| E-REV-01 | new roster with unconfirmed recurring fields | `NEEDS_REVIEW`; confirm rejected | rejected | PASS |
| E-REV-02 | unmatched synthetic attendance identity | `IDENTITY`; no automatic match | blocked | PASS |
| E-REV-03 | literal OT without category | `OT` review; confirm rejected | blocked | PASS |
| E-REV-04 | reasoned OT decision | recalculation produces `READY` | `READY` | PASS |
| E-CONF-01 | ready revision | `CONFIRMED` and audit `PAYROLL_CONFIRMED` | persisted | PASS |
| E-CONF-02 | wrong expected revision | reject without transition | covered by regression test | PASS |

Holiday, leave, manual deduction and changed-source variants remain scheduled
for the final isolated regression pass. None is assumed resolved merely
because a field is present in a workbook.
