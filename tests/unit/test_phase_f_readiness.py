from types import SimpleNamespace

from app.db.database import Database
from app.db.repositories import Repository
from app.services.readiness import ReadinessService


def test_phase_f_readiness_reads_only_isolated_database_and_reports_thai(workbook_workspace):
    root = workbook_workspace / 'uat'; attendance = root / 'attendance'; output = root / 'output'
    attendance.mkdir(parents=True); output.mkdir(); template = root / 'template.xlsx'; template.write_bytes(b'x')
    repo = Repository(Database(root / 'data.db'))
    workflow = SimpleNamespace(repo=repo, configuration=lambda: {'attendance_folder': str(attendance), 'payroll_folder': str(output), 'template_path': str(template)})
    report = ReadinessService(workflow, database_path=root / 'data.db', excel_probe=lambda: '16.0').assess()
    checks = {check.id: check for check in report.checks}
    assert checks['DATABASE_SCHEMA'].status == 'PASS'
    assert checks['EXCEL_COM'].summary_th.startswith('Excel')
    assert all(check.read_only for check in report.checks)
    assert checks['MONITORING_STATE'].status == 'NOT_VERIFIED'
