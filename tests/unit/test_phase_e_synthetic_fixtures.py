from decimal import Decimal

from app.excel.attendance_reader import read_attendance
from app.excel.formulas import row_values
from app.excel.payslip_adapter import PayslipAdapter
from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.safety import REFERENCE_ROOT, TEST_ROOT
from tests.phase_e_fixtures import PEOPLE, create_synthetic_excel_fixture, uat_root


def test_phase_e_fixture_uses_only_new_synthetic_files_and_real_readers():
    fixture = create_synthetic_excel_fixture(uat_root("fixture_contract"))
    root = fixture["root"]
    assert TEST_ROOT.resolve() in root.parents
    assert REFERENCE_ROOT.resolve() not in root.parents

    attendance = read_attendance(fixture["attendance"], year=2026, month=9)
    payroll = PayrollWorkbookAdapter.read(fixture["payroll"])
    slips = PayslipAdapter.read(fixture["payroll"])

    assert [employee.full_name for employee in attendance.employees] == [full_name for _, full_name in PEOPLE]
    assert all(employee.totals["travel"].numeric_subtotal == Decimal("300") for employee in attendance.employees)
    assert payroll.period() == (2026, 9)
    assert [employee.name for employee in payroll.employees] == [full_name for _, full_name in PEOPLE]
    first = payroll.employees[0]
    assert first.cells["normal_money"].formula == "=D7*E7"
    assert row_values(first, {})(first.cells["income"].coordinate) == Decimal("34400")
    assert [slip.full_name for slip in slips.slips] == [full_name for _, full_name in PEOPLE]
    assert all(slip.period_cell and slip.payment_date_cell for slip in slips.slips)
