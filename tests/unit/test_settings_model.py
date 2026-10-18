import os

import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication

from app.services.automation_runtime import AutomationRuntime, RuntimeState
from app.services.windows_startup import StartupState, StartupStatus
from app.services.workflow_service import WorkflowService
from app.ui.settings_model import SettingsViewModel
from app.db.database import Database
from app.db.repositories import Repository
from app.services.payroll_service import PayrollService


class FakeStartup:
    def __init__(self, state=StartupState.NOT_INSTALLED):
        self.state = state
        self.calls = 0

    def validate(self):
        self.calls += 1
        return StartupStatus(self.state, f'{self.state} fixture')


@pytest.fixture(scope='session')
def qt_app():
    return QApplication.instance() or QApplication([])


def _workflow(workbook_workspace):
    return WorkflowService(PayrollService(Repository(Database(workbook_workspace / 'payroll.db'))))


def test_settings_snapshot_is_read_only_and_caches_startup_status(workbook_workspace):
    workflow = _workflow(workbook_workspace)
    workflow.repo.set_setting('watch_enabled', False)
    startup = FakeStartup()
    model = SettingsViewModel(workflow, startup_service=startup)

    first = model.snapshot()
    second = model.snapshot()

    assert first.watch_preference is False
    assert first.monitoring_state == 'UNKNOWN'
    assert first.startup_state == StartupState.NOT_INSTALLED
    assert second == first and startup.calls == 1
    assert workflow.repo.setting('watch_enabled', None) is False


def test_settings_snapshot_preserves_unset_monitoring_preference(workbook_workspace):
    workflow = _workflow(workbook_workspace)
    model = SettingsViewModel(workflow, startup_service=FakeStartup())

    snapshot = model.snapshot()

    assert snapshot.watch_preference is None
    assert 'ยังไม่ได้เลือก' in snapshot.monitoring_detail
    assert workflow.repo.setting('watch_enabled', None) is None


def test_settings_snapshot_refreshes_startup_only_when_requested(workbook_workspace):
    workflow = _workflow(workbook_workspace)
    startup = FakeStartup(StartupState.VALID)
    model = SettingsViewModel(workflow, startup_service=startup)

    assert model.snapshot().startup_enabled
    startup.state = StartupState.NEEDS_REPAIR
    assert model.snapshot().startup_state == StartupState.VALID
    assert model.snapshot(refresh_startup=True).startup_state == StartupState.NEEDS_REPAIR
    assert startup.calls == 2


def test_settings_snapshot_does_not_create_or_resume_a_watcher(qt_app, workbook_workspace, monkeypatch):
    workflow = _workflow(workbook_workspace)
    workflow.repo.set_setting('workflow_configuration', {
        'attendance_folder': str(workbook_workspace),
        'payroll_folder': str(workbook_workspace),
        'template_path': str(workbook_workspace / 'template.xlsx'),
    })
    runtime = AutomationRuntime(workflow.payroll_service, qt_app)
    workflow.repo.set_setting('watch_enabled', False)
    resumes = []
    monkeypatch.setattr(runtime, 'resume_monitoring', lambda: resumes.append(True))

    snapshot = SettingsViewModel(workflow, runtime=runtime, startup_service=FakeStartup()).snapshot()

    assert snapshot.monitoring_state == RuntimeState.DISABLED
    assert runtime.watcher is None and resumes == []
    assert workflow.repo.setting('watch_enabled', None) is False
