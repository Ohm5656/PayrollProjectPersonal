from pathlib import Path

from app.db.database import Database
from app.db.repositories import Repository
from app.services.month8_uat import prepare_month8_uat
from app.services.payroll_service import PayrollService
from app.services.workflow_service import WorkflowService


def test_month8_uat_prepares_copy_archives_rerun_and_generates_output(workbook_workspace):
    workflow = WorkflowService(PayrollService(Repository(Database(workbook_workspace / 'uat.db'))))
    root = workbook_workspace / 'uat_month8'
    prepared = prepare_month8_uat(workflow, root=root)
    assert prepared['attendance'].is_file()
    assert not list(prepared['payroll_output'].glob('*.xlsx'))
    result = workflow.process_attendance(prepared['attendance'])
    payroll = prepared['payroll_output'] / 'เดือน 8.xlsx'
    assert payroll.is_file() and result['monthly_payroll'].path == payroll
    assert Path(result['comparison_report']).is_file()
    reset = prepare_month8_uat(workflow, root=root)
    assert reset['archive'] and (reset['archive'] / 'payroll_output' / 'เดือน 8.xlsx').is_file()
    assert not list(reset['payroll_output'].glob('*.xlsx'))
