import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from decimal import Decimal

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QTableWidget

from app.domain import ReviewIssue, issue_key
from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from app.ui.review import DecisionDialog, EmployeeReview, ReviewCenter
from app.ui.review import ZeroManualReview
from app.ui.calendar_review import CalendarReview
from app.ui.tray import PayrollTray

# Pure model fixture is shared from the engine suite without modifying Phase 2.
from tests.unit.test_draft_engine import draft_case, calculate


@pytest.fixture(scope='session')
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app
    app.processEvents()


def test_main_window_thai_columns_and_review_gate(qt_app, draft_case):
    repo, _, _, _ = draft_case
    service = PayrollService(repo)
    draft = calculate(draft_case)
    window = MainWindow(service)
    window.show_result({'run': {'state': 'NEEDS_REVIEW', 'revision': 1}, 'draft': draft})
    assert window.table.horizontalHeaderItem(0).text() == 'ชื่อ'
    assert window.table.item(0, 3).text() == '1,500.00'
    assert not window.confirm_button.isEnabled()
    assert window.review_button.isEnabled()
    assert not window.write_button.isEnabled()
    window.close()


def test_one_time_deduction_previous_checkbox_is_not_prechecked(qt_app, draft_case):
    repo, eid, attendance, _ = draft_case
    with repo.db.transaction() as con:
        con.execute('INSERT INTO payroll_observations VALUES (?,?,?,?,?,?,?,?)', (eid, 2026, 8, 'advance', '3000', None, 'fixture', 'old'))
    draft = calculate(draft_case)
    issue = next(i for i in draft.issues if i.kind == 'FIELD' and i.field == 'advance')
    dialog = DecisionDialog(PayrollService(repo), draft, issue)
    assert dialog.use_previous.isEnabled()
    assert not dialog.use_previous.isChecked()
    assert dialog.controls['value'].text() == ''
    assert dialog.policy.currentData() == 'NEVER_REUSE'
    dialog.close()


def test_calendar_bulk_choice_is_explicit_and_employee_scoped(qt_app,draft_case):
    repo,eid,_,_=draft_case
    with repo.db.transaction() as con: con.execute('DELETE FROM company_calendar')
    draft=calculate(draft_case)
    dialog=CalendarReview(PayrollService(repo),draft,employee=draft.employees[0])
    assert all(not c.isChecked() for c in dialog.weekdays)
    assert all(c.currentData()=='UNKNOWN' for _,c,_,_ in dialog.rows)
    for check in dialog.weekdays[:5]: check.setChecked(True)
    dialog.fill_weekdays()
    dialog.reason.setText('ปฏิทินสมมติเพื่อทดสอบเท่านั้น')
    dialog.persist()
    assert repo.calendar(eid,'2026-09-05')['type']=='WEEKLY_HOLIDAY'
    assert repo.calendar('other employee','2026-09-05') is None
    dialog.close()


def test_monthly_zero_approval_never_reuses_nonzero_source_or_previous_value(qt_app,draft_case):
    from dataclasses import replace
    repo,eid,attendance,_=draft_case
    draft=calculate(draft_case)
    employee=draft.employees[0]
    zero=replace(employee.values['advance'],source_value=None,previous_value=Decimal(3000))
    employee=replace(employee,values={**employee.values,'loan':replace(zero,field='loan')})
    dialog=ZeroManualReview(PayrollService(repo),draft,employee)
    assert 'advance' not in dialog.checks  # Current source is nonzero.
    assert not dialog.checks['loan'].isChecked()
    dialog.checks['loan'].setChecked(True)
    dialog.reason.setText('ตรวจแล้วไม่หักเงินกู้เดือนนี้')
    dialog.persist()
    assert repo.decisions(attendance.source_hash)[issue_key('FIELD',eid,'loan')]['value']=='0'
    assert repo.remembered(eid,'loan','2026-10-01') is None
    dialog.close()


def test_ui_leave_decision_is_one_occurrence_unless_remember_selected(qt_app, draft_case):
    repo, eid, attendance, _ = draft_case
    draft = calculate(draft_case)
    issue = ReviewIssue('test-leave', 'LEAVE', eid, 'test', '2026-09-01', 'D3', 'ลา', 'ลา')
    dialog = DecisionDialog(PayrollService(repo), draft, issue)
    dialog.controls['leave_type'].setCurrentIndex(1)
    dialog.controls['bonus_effect'].setCurrentIndex(2)
    dialog.reason.setText('ใช้เฉพาะครั้งนี้')
    dialog.persist()
    assert repo.decisions(attendance.source_hash)['test-leave']['leave_type'] == 'SICK_LEAVE'
    assert repo.rule('LEAVE', 'ลา', eid) is None
    dialog.remember.setChecked(True)
    dialog.persist()
    assert repo.rule('LEAVE', 'ลา', eid)['bonus_effect'] == 'KEEP'
    assert repo.rule('LEAVE', 'ลา', 'another employee') is None
    dialog.close()


def test_ui_failed_rule_save_rolls_back_occurrence(qt_app, draft_case):
    repo, eid, attendance, _ = draft_case
    with repo.db.transaction() as con:
        con.execute('DELETE FROM company_calendar')
    issue = ReviewIssue('test-ot', 'OT', eid, 'test', '2026-09-01', 'H3', 'OT', '2')
    dialog = DecisionDialog(PayrollService(repo), calculate(draft_case), issue)
    dialog.controls['category'].setCurrentIndex(1)
    dialog.reason.setText('test')
    dialog.remember.setChecked(True)
    with pytest.raises(ValueError, match='ยืนยันสถานะวัน'):
        dialog.persist()
    assert 'test-ot' not in repo.decisions(attendance.source_hash)
    dialog.close()


def test_review_center_groups_and_diff_evidence(qt_app, draft_case):
    repo, _, _, _ = draft_case
    draft = calculate(draft_case)
    dialog = ReviewCenter(PayrollService(repo), draft)
    assert dialog.tree.topLevelItemCount() == 1
    employee = draft.employees[0]
    employee_dialog = EmployeeReview(PayrollService(repo), draft, employee)
    assert employee_dialog.table.columnCount() == 7
    assert employee_dialog.table.horizontalHeaderItem(1).text() == 'ต้นทาง'
    employee_dialog.close()
    dialog.close()


def test_tray_actions_states_and_close_to_tray(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))
    tray = PayrollTray(window, qt_app)
    window.tray = tray
    actions = [a.text() for a in tray.contextMenu().actions()]
    assert 'เปิด NTP Payroll Assistant' in actions and 'ออก' in actions
    tray.state('error')
    assert 'ข้อผิดพลาด' in tray.toolTip()
    tray.state('review')
    assert 'ต้องตรวจสอบ' in tray.toolTip()
    assert window.shutdown()
    tray.hide()
    window.close()
