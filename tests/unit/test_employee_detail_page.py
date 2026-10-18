from app.domain import PayrollState
from app.ui.employee_detail_page import EmployeeDetailPage, money, value_category
from tests.unit.test_draft_engine import calculate, draft_case
from tests.unit.test_ui import qt_app


def test_employee_detail_displays_payroll_value_evidence_without_mutation(qt_app, draft_case):
    draft = calculate(draft_case)
    employee = draft.employees[0]
    page = EmployeeDetailPage()
    page.refresh(draft, employee, {'state': PayrollState.NEEDS_REVIEW})

    assert page.table.rowCount() == len(employee.values)
    assert page.table.item(0, 1).text() != ''
    assert money(None) == '—' and money(0) == '0.00'
    assert value_category('MANUAL') == 'รายการที่ต้องยืนยัน'


def test_employee_detail_routes_only_explicit_field_request_and_blocks_final_state(qt_app, draft_case):
    draft = calculate(draft_case)
    employee = draft.employees[0]
    page = EmployeeDetailPage()
    requested = []
    page.field_review_requested.connect(requested.append)
    page.refresh(draft, employee, {'state': PayrollState.NEEDS_REVIEW})
    page.open_field(0)
    assert requested == [next(iter(employee.values))]

    page.refresh(draft, employee, {'state': PayrollState.CONFIRMED})
    page.open_field(0)
    assert len(requested) == 1 and not page.review_field.isEnabled()
