from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

from app.domain import encode, utc_now
from app.services.automation_runtime import AutomationRuntime
from app.services.payroll_service import PayrollService
from app.services.windows_startup import StartupState, StartupStatus
from app.ui.main_window import MainWindow
from tests.unit.test_draft_engine import calculate
from tests.unit.test_ui import qt_app, draft_case


class FakeStartup:
    def validate(self):
        return StartupStatus(StartupState.NOT_INSTALLED, 'synthetic test fixture')


def _persist_draft(repo, draft):
    run_id = str(uuid4())
    with repo.db.transaction() as con:
        con.execute('INSERT INTO payroll_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)', (
            run_id, draft.year, draft.month, draft.state.value, draft.source_path,
            draft.source_hash, draft.payroll_path, draft.payroll_hash, 1,
            encode(draft.evidence()), utc_now(),
        ))


def _two_periods(draft_case):
    repo, *_ = draft_case
    september = calculate(draft_case)
    september_employee = replace(september.employees[0], name='September Synthetic Employee')
    september = replace(september, employees=(september_employee,), source_path='sept-attendance-copy.xlsx',
                         payroll_path='sept-payroll-copy.xlsx', source_hash='sept-source', payroll_hash='sept-payroll')
    october_values = dict(september_employee.values)
    october_values['allowance'] = replace(october_values['allowance'], final_value=Decimal('9876'))
    october_employee = replace(september_employee, name='October Synthetic Employee', values=october_values)
    october = replace(september, month=10, employees=(october_employee,), source_path='oct-attendance-copy.xlsx',
                      payroll_path='oct-payroll-copy.xlsx', source_hash='oct-source', payroll_hash='oct-payroll')
    _persist_draft(repo, september)
    _persist_draft(repo, october)
    return september, october


def _window(draft_case):
    service = PayrollService(draft_case[0])
    service.repo.set_setting('watch_enabled', False)
    return MainWindow(service, startup_service=FakeStartup()), service


def test_period_change_replaces_employee_rows_and_selected_context(qt_app, draft_case):
    _two_periods(draft_case)
    window, _ = _window(draft_case)

    window.year.setValue(2026); window.month.setValue(9)
    assert window.table.item(0, 0).text() == 'September Synthetic Employee'
    assert window.table.item(0, 3).text() == '4,500.00'
    window.table.selectRow(0)
    assert window.selected_employee().name == 'September Synthetic Employee'

    window.month.setValue(10)
    assert window.table.item(0, 0).text() == 'October Synthetic Employee'
    assert window.table.item(0, 3).text() == '9,876.00'
    assert window.table.currentRow() == -1 and window.selected_employee() is None

    window.month.setValue(9)
    assert window.table.item(0, 0).text() == 'September Synthetic Employee'
    assert window.table.item(0, 3).text() == '4,500.00'
    window.close()


def test_no_draft_clears_stale_rows_actions_and_period_scoped_sources(qt_app, draft_case):
    _two_periods(draft_case)
    window, service = _window(draft_case)
    actions = []
    for name in ('prepare', 'confirm', 'write', 'lock', 'reopen'):
        monkey = lambda *args, _name=name, **kwargs: actions.append(_name)
        setattr(service, name, monkey)

    window.year.setValue(2026); window.month.setValue(9)
    window.attendance.setText('sept-attendance-copy.xlsx')
    window.payroll.setText('sept-payroll-copy.xlsx')
    window._source_period = (2026, 9)
    window.table.selectRow(0)
    window.month.setValue(11)

    assert window.draft is None and window.run is None
    assert window.table.rowCount() == 0 and window.table.currentRow() == -1
    assert window.selected_employee() is None
    assert not window.review_button.isEnabled()
    assert not window.overview_page.primary_action.isEnabled()
    assert 'ยังไม่ได้เลือกไฟล์สำเนา' in window.overview_page.attendance_source.text()
    assert actions == [] and service.repo.setting('watch_enabled', None) is False

    window.month.setValue(10)
    assert window.table.item(0, 0).text() == 'October Synthetic Employee'
    window.close()


def test_other_period_watcher_result_does_not_replace_selected_table_or_monitoring(qt_app, draft_case, monkeypatch):
    september, october = _two_periods(draft_case)
    service = PayrollService(draft_case[0])
    service.repo.set_setting('watch_enabled', False)
    runtime = AutomationRuntime(service, qt_app)
    window = MainWindow(service, runtime=runtime, startup_service=FakeStartup())
    window.year.setValue(2026); window.month.setValue(9)
    monkeypatch.setattr(window.workflow, 'configured', lambda: True)

    window.receive_watched_result({'run': {'state': october.state.value}, 'draft': october})

    assert window.table.item(0, 0).text() == 'September Synthetic Employee'
    assert window.draft.year == september.year and window.draft.month == september.month
    assert runtime.watcher is None and service.repo.setting('watch_enabled', None) is False
    window.close()
