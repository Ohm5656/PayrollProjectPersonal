from dataclasses import replace
from decimal import Decimal

import pytest

from app.domain import EmployeeDraft, PayrollValue, ValueCategory
from app.excel.payslip_adapter import PayslipAdapter, PayslipReviewError
from app.excel.payroll_reader import PayrollWorkbookAdapter


def observed_approved_employee(person, *, eid='fixture-approved'):
    values = {key: PayrollValue(key, ValueCategory.MANUAL, cell.value, None, cell.value or Decimal(0),
        None, cell.value or Decimal(0), 'Explicit test fixture approval', 'fixture', True)
        for key, cell in person.cells.items() if key not in {'normal_rate','holiday_rate','holiday_ot_rate'}}
    return EmployeeDraft(eid, eid, person.name, None, values, ())


@pytest.mark.parametrize('month', range(1, 10))
def test_all_historical_payslip_layouts_can_be_inspected(copied_reference, month):
    path = next((copied_reference / 'payroll').glob(f'* {month}.xlsx'))
    adapter = PayslipAdapter.read(path)
    assert len(adapter.slips) >= 10
    assert all(s.slots and {'income','deductions','net'} <= s.totals.keys() for s in adapter.slips)
    assert all(s.period_cell and s.payment_date_cell for s in adapter.slips)


def test_payslip_uses_full_name_not_wrong_sheet_title(copied_reference):
    path = next((copied_reference / 'payroll').glob('* 8.xlsx'))
    adapter = PayslipAdapter.read(path)
    assert adapter.employee('วรรณษรณ์ ทองทวี').sheet == 'จริยา'


def test_existing_housing_split_retained_without_guessing(copied_reference):
    path = next((copied_reference / 'payroll').glob('* 8.xlsx'))
    payroll = PayrollWorkbookAdapter.read(path)
    slips = PayslipAdapter.read(path)
    person = payroll.employee('บรรจง มูลที')
    employee = observed_approved_employee(person)
    changes, expected = slips.plan_employee(employee, person)
    assert ('บรรจง', 'I9', Decimal(1000)) in expected
    assert ('บรรจง', 'I10', Decimal(414)) in expected
    housing = replace(employee.values['housing'], final_value=Decimal(1500))
    employee = replace(employee, values={**employee.values, 'housing': housing})
    with pytest.raises(PayslipReviewError, match='แบ่ง'):
        slips.plan_employee(employee, person)


def test_ambiguous_tool_caption_requires_explicit_mapping(copied_reference):
    path = next((copied_reference / 'payroll').glob('* 8.xlsx'))
    payroll = PayrollWorkbookAdapter.read(path)
    slips = PayslipAdapter.read(path)
    person = payroll.employee('อดิศักดิ์ สาคำตา')
    employee = observed_approved_employee(person)
    with pytest.raises(PayslipReviewError, match='tool_loss'):
        slips.plan_employee(employee, person)
    changes, expected = slips.plan_employee(employee, person, mapping={'assignments': {'I9': ['tool_loss']}})
    assert ('อดิศักดิ์', 'I9', Decimal(184)) in expected


def test_known_inline_units_are_updated_from_approved_count(copied_reference):
    path = next((copied_reference / 'payroll').glob('* 8.xlsx'))
    payroll = PayrollWorkbookAdapter.read(path)
    slips = PayslipAdapter.read(path)
    person = payroll.employees[0]
    employee = observed_approved_employee(person)
    changes, expected = slips.plan_employee(employee, person)
    caption = next(c for c in changes if c.address == 'B8')
    assert 'x2.5' in caption.value
    assert caption.sheet == 'ดนุกานต์'


def test_payment_date_read_from_workbook_not_assumed_day(copied_reference):
    path = next((copied_reference / 'payroll').glob('* 8.xlsx'))
    payroll = PayrollWorkbookAdapter.read(path)
    assert payroll.payment_date().isoformat() == '2026-09-05T00:00:00'
