from hashlib import sha256

import pytest

from app.db.database import Database
from app.db.repositories import Repository
from app.qa_environment import QAEnvironment, QAStartupService, seed_synthetic_fixture
from app.safety import SafetyError
from app.services.automation_runtime import AutomationRuntime, RuntimeState
from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from tests.unit.test_ui import qt_app


def _normal_database(path):
    repo = Repository(Database(path))
    for number in range(13):
        repo.create_employee(f'Ordinary Record {number}', actor='ordinary-fixture')
    repo.set_setting('watch_enabled', True)
    return repo


def test_qa_environment_is_separate_synthetic_and_preserves_ordinary_state(workbook_workspace):
    ordinary = workbook_workspace / 'app_state' / 'data' / 'ntp_payroll.db'
    normal_repo = _normal_database(ordinary)
    before = sha256(ordinary.read_bytes()).hexdigest()

    environment = QAEnvironment.create(sessions_root=workbook_workspace / 'qa_sessions')
    qa_repo = Repository(Database(environment.database_path))
    seed_synthetic_fixture(qa_repo, environment)

    assert qa_repo.db.path != normal_repo.db.path
    assert [row['canonical_name'] for row in qa_repo.employees()] == ['Avery Sample', 'Blair Example', 'Casey Demo']
    assert qa_repo.run(2026, 9) and qa_repo.run(2026, 10) and qa_repo.run(2026, 11) is None
    assert qa_repo.setting('watch_enabled') is False
    assert sha256(ordinary.read_bytes()).hexdigest() == before
    assert normal_repo.setting('watch_enabled') is True
    assert all(environment.contains(path) for path in environment.root.rglob('*'))


def test_qa_paths_startup_and_monitoring_cannot_escape_or_touch_windows(qt_app, workbook_workspace):
    environment = QAEnvironment.create(sessions_root=workbook_workspace / 'qa_sessions')
    repo = Repository(Database(environment.database_path))
    seed_synthetic_fixture(repo, environment)
    with pytest.raises(SafetyError):
        environment.require_path(workbook_workspace / 'outside-qa.txt')

    startup = QAStartupService()
    assert startup.validate().state.name == 'UNAVAILABLE'
    assert not startup.install().success and not startup.remove().success and not startup.repair().success

    runtime = AutomationRuntime(PayrollService(repo), qt_app, qa_mode=True, qa_root=environment.root)
    assert runtime.start() is False
    assert runtime.state == RuntimeState.DISABLED and runtime.watcher is None
    assert runtime.resume_monitoring() is False
    failed_job = next(job for job in runtime.jobs.latest() if job['state'] == 'FAILED')
    assert runtime.retry_eligibility(failed_job['id'])[0] is False
    assert repo.setting('watch_enabled') is False


def test_qa_synthetic_pages_and_period_navigation_are_read_only(qt_app, workbook_workspace, monkeypatch):
    environment = QAEnvironment.create(sessions_root=workbook_workspace / 'qa_sessions')
    repo = Repository(Database(environment.database_path))
    seed_synthetic_fixture(repo, environment)
    service = PayrollService(repo)
    runtime = AutomationRuntime(service, qt_app, qa_mode=True, qa_root=environment.root)
    window = MainWindow(service, runtime=runtime, startup_service=QAStartupService(), qa_environment=environment)
    calls = []
    for name in ('prepare', 'confirm', 'reopen', 'lock'):
        monkeypatch.setattr(service, name, lambda *args, _name=name, **kwargs: calls.append(_name))

    assert 'QA MODE' in window.windowTitle()
    for page in ('overview', 'review', 'history', 'problems', 'settings'):
        window.navigate_to(page)
        assert window.page_host.currentIndex() == window._page_indexes[page]
    window.year.setValue(2026); window.month.setValue(9)
    assert window.table.item(0, 0).text() == 'Avery Sample'
    window.month.setValue(10)
    assert window.table.item(0, 0).text() == 'Avery Sample'
    assert window.table.item(0, 3).text() == '1,900.00'
    window.month.setValue(11)
    assert window.table.rowCount() == 0 and window.selected_employee() is None
    assert calls == [] and runtime.watcher is None
    window.close()
