from openpyxl import load_workbook
import shutil

from app.services.monthly_workflow import create_monthly_payroll, master_template_path, verify_monthly_copy
from app.services.workflow_service import WorkflowService
from app.services.payroll_service import PayrollService
from app.db.database import Database
from app.db.repositories import Repository


def test_monthly_master_copy_updates_only_deterministic_metadata(workbook_workspace):
    output = workbook_workspace / 'payroll'
    output.mkdir()
    cases = {8: '2026-09-05', 10: '2026-11-05', 12: '2027-01-05'}
    for month, pay_date in cases.items():
        item = create_monthly_payroll(master_template_path(), output, 2026, month)
        verified = verify_monthly_copy(item.path, 2026, month)
        assert item.path.name == f'เดือน {month}.xlsx'
        assert verified['payment_date'] == pay_date
        assert verified['payslips'] == 12
        # Formula cells, layout, and print setup are checked by creation; this
        # spot check also proves the output is an editable independent copy.
        book = load_workbook(item.path, data_only=False)
        try:
            assert book['คิดค่าจ้าง ']['F9'].data_type == 'f'
            assert book['คิดค่าจ้าง '].page_setup.orientation
            assert book['คิดค่าจ้าง '].merged_cells.ranges
        finally:
            book.close()


def test_folder_workflow_detects_period_then_creates_matching_copy(copied_reference, workbook_workspace):
    attendance_folder, payroll_folder = workbook_workspace / 'attendance', workbook_workspace / 'payroll'
    attendance_folder.mkdir(); payroll_folder.mkdir()
    source = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    attendance = attendance_folder / source.name
    shutil.copy2(source, attendance)
    workflow = WorkflowService(PayrollService(Repository(Database(workbook_workspace / 'workflow.db'))))
    workflow.configure(attendance_folder, payroll_folder)
    result = workflow.process_attendance(attendance)
    assert (result['draft'].year, result['draft'].month) == (2026, 8)
    assert result['monthly_payroll'].path == payroll_folder / 'เดือน 8.xlsx'
