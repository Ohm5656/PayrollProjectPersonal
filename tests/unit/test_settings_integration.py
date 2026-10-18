import os

import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication

from app.db.database import Database
from app.db.repositories import Repository
from app.services.automation_runtime import AutomationRuntime, RuntimeState
from app.services.payroll_service import PayrollService
from app.services.windows_startup import StartupResult, StartupState, StartupStatus
from app.ui.main_window import MainWindow


class FolderWatcher:
    instances = []
    def __init__(self, *args, **kwargs): self.started = self.stopped = False; type(self).instances.append(self)
    def start(self): self.started = True
    def stop(self): self.stopped = True; return True


class FakeStartup:
    def __init__(self, *, fail_install=False):
        self.state = StartupState.NOT_INSTALLED
        self.fail_install = fail_install
        self.install_calls = self.remove_calls = self.repair_calls = 0

    def validate(self):
        return StartupStatus(self.state, f'{self.state} fixture')

    def install(self):
        self.install_calls += 1
        self.state = StartupState.ERROR if self.fail_install else StartupState.VALID
        return StartupResult(not self.fail_install, self.validate(), not self.fail_install)

    def remove(self):
        self.remove_calls += 1
        self.state = StartupState.NOT_INSTALLED
        return StartupResult(True, self.validate(), True)

    def repair(self):
        self.repair_calls += 1
        self.state = StartupState.VALID
        return StartupResult(True, self.validate(), True)


@pytest.fixture(scope='session')
def qt_app():
    return QApplication.instance() or QApplication([])


def configured_window(workbook_workspace, startup):
    FolderWatcher.instances.clear()
    attendance, payroll = workbook_workspace / 'attendance', workbook_workspace / 'payroll'
    attendance.mkdir(); payroll.mkdir()
    service = PayrollService(Repository(Database(workbook_workspace / 'settings.db')))
    runtime = AutomationRuntime(service, folder_watcher_factory=FolderWatcher)
    runtime.workflow.configure(attendance, payroll)
    return MainWindow(service, runtime=runtime, startup_service=startup), runtime


def settings_values(window, *, startup=False):
    values = window.workflow.configuration().copy()
    values['start_with_windows'] = startup
    return values


def test_settings_enables_windows_startup_without_resuming_paused_monitoring(qt_app, workbook_workspace):
    window, runtime = configured_window(workbook_workspace, FakeStartup())
    runtime.repo.set_setting('watch_enabled', False)

    assert window._save_settings(settings_values(window, startup=True))

    assert runtime.repo.setting('watch_enabled', None) is False
    assert runtime.state == RuntimeState.DISABLED and runtime.watcher is None
    assert len(FolderWatcher.instances) == 0
    window.close()


def test_settings_save_reuses_active_watcher_and_never_calls_resume(qt_app, workbook_workspace, monkeypatch):
    window, runtime = configured_window(workbook_workspace, FakeStartup())
    assert runtime.resume_monitoring()
    watcher = runtime.watcher
    resumes = []
    monkeypatch.setattr(runtime, 'resume_monitoring', lambda: resumes.append(True))

    assert window._save_settings(settings_values(window, startup=True))

    assert runtime.repo.setting('watch_enabled', None) is True
    assert runtime.watcher is watcher and len(FolderWatcher.instances) == 1 and resumes == []
    assert runtime.shutdown()
    window.close()


def test_failed_startup_install_reports_partial_settings_change(qt_app, workbook_workspace):
    startup = FakeStartup(fail_install=True)
    window, runtime = configured_window(workbook_workspace, startup)
    runtime.repo.set_setting('watch_enabled', False)

    assert not window._save_settings(settings_values(window, startup=True))

    assert window.workflow.configured()
    assert startup.install_calls == 1
    assert 'บันทึกโฟลเดอร์แล้ว' in window.settings_page.message.text()
    assert runtime.repo.setting('watch_enabled', None) is False and runtime.watcher is None
    window.close()
