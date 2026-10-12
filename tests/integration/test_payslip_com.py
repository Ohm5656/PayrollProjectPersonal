from dataclasses import replace
from decimal import Decimal

import pytest

from app.excel.payslip_adapter import PayslipAdapter
from app.excel.payroll_writer import PayrollWriter, build_plan
from app.excel.payroll_writer import CellWrite
from app.excel.workbook_validator import WorkbookStructure, validate_expected
from tests.unit.test_writer_safety import controlled_draft, payroll_copy

pytestmark = pytest.mark.excel_com


def test_single_employee_payslip_updates_existing_layout(payroll_copy):
    draft, payroll = controlled_draft(payroll_copy)
    employee = draft.employees[0]
    normal=replace(employee.values['travel'],field='normal_ot',source_value=payroll.employees[0].cells['normal_ot'].value,
                   draft_value=Decimal(7),final_value=Decimal(7))
    employee=replace(employee,values={**employee.values,'normal_ot':normal})
    draft=replace(draft,employees=(employee,))
    slip_adapter = PayslipAdapter.read(payroll_copy)
    changes, expected = slip_adapter.plan_employee(employee, payroll.employees[0])
    slip=slip_adapter.employee(employee.name)
    changes=(*changes,CellWrite(slip.sheet,slip.period_cell,8),CellWrite(slip.sheet,slip.payment_date_cell,payroll.payment_date()))
    expected=(*expected,(slip.sheet,slip.period_cell,8),(slip.sheet,slip.payment_date_cell,payroll.payment_date()))
    plan = build_plan(draft, payroll)
    plan = replace(plan, writes=(*plan.writes,*changes), expected=(*plan.expected,*expected))
    structure = WorkbookStructure.read(payroll_copy)
    result = PayrollWriter().execute(plan)
    assert result['validated']
    assert any(isinstance(change.value,str) for change in changes)
    validate_expected(payroll_copy, (('คิดค่าจ้าง ', 'P9', Decimal(1325)), ('ดนุกานต์', 'D12', Decimal(1325))))
    structure.validate(WorkbookStructure.read(payroll_copy))
