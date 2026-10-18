"""Persistent folder-based orchestration for the normal monthly workflow."""
from pathlib import Path

from app.excel.attendance_reader import read_attendance
from app.safety import SafetyError
from app.services.monthly_workflow import (
    MonthlyWorkflowError, create_monthly_payroll, master_template_path,
    validate_workflow_configuration,
)


WORKFLOW_SETTING = 'workflow_configuration'


class WorkflowService:
    def __init__(self, payroll_service):
        self.payroll_service = payroll_service
        self.repo = payroll_service.repo

    def configuration(self):
        return self.repo.setting(WORKFLOW_SETTING)

    def configured(self):
        config = self.configuration()
        return bool(config and {'attendance_folder', 'payroll_folder', 'template_path'} <= set(config))

    def configure(self, attendance_folder, payroll_folder, template_path=None):
        attendance, payroll, template = validate_workflow_configuration(
            attendance_folder, payroll_folder, template_path or master_template_path())
        value = {'attendance_folder': str(attendance), 'payroll_folder': str(payroll), 'template_path': str(template)}
        self.repo.set_setting(WORKFLOW_SETTING, value)
        return value

    def process_attendance(self, path):
        config = self.configuration()
        if not config:
            raise MonthlyWorkflowError('ยังไม่ได้ตั้งค่าโฟลเดอร์ทำงาน')
        attendance_folder, payroll_folder, template = validate_workflow_configuration(
            config['attendance_folder'], config['payroll_folder'], config['template_path'])
        source = Path(path).resolve()
        if not self.is_approved_attendance_source(source, attendance_folder=attendance_folder):
            raise SafetyError('Attendance event is outside the configured folder')
        # The reader uses filename, internal dates, and validated attendance
        # structure; it raises rather than guessing when evidence conflicts.
        attendance = read_attendance(source)
        monthly = create_monthly_payroll(template, payroll_folder, attendance.year, attendance.month)
        result = self.payroll_service.prepare(source, monthly.path, year=attendance.year, month=attendance.month)
        if config.get('mode') == 'UAT_MONTH8' and (attendance.year, attendance.month) == (2026, 8):
            from app.services.month8_uat import month8_comparison
            result['comparison_report'] = str(month8_comparison(monthly.path, config.get('historical_month8')))
        return {**result, 'monthly_payroll': monthly, 'attendance': attendance}

    def is_approved_attendance_source(self, path, *, attendance_folder=None):
        """Use the normal attendance reader to reject non-input XLSX files.

        The attendance folder is a deliberately small approved scope.  A file
        still has to have a recognisable attendance structure before startup
        reconciliation may enqueue it; output payroll workbooks and arbitrary
        XLSX files consequently never become automatic inputs.
        """
        config = self.configuration()
        if not config and attendance_folder is None:
            return False
        folder = Path(attendance_folder or config['attendance_folder']).resolve()
        source = Path(path).resolve()
        if (source.parent != folder or source.suffix.lower() != '.xlsx'
                or source.name.startswith('~$') or not source.is_file()):
            return False
        try:
            attendance = read_attendance(source)
        except Exception:
            return False
        return any(employee.header_row is not None for employee in attendance.employees)
