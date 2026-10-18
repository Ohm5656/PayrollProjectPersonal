"""Phase C.1: Windows startup Settings must not change watcher intent."""
import os

import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication, QDialog

from app.db.database import Database
from app.db.repositories import Repository
from app.services.automation_runtime import AutomationRuntime, RuntimeState
from app.services.payroll_service import PayrollService
from app.services.windows_startup import StartupResult, StartupState, StartupStatus
from app.services.workflow_service import WorkflowService
from app.ui.main_window import MainWindow
from app.ui.setup_wizard import SetupWizard
from app.ui.tray import PayrollTray


@pytest.fixture(scope='session')
def qt_app():
    return QApplication.instance() or QApplication([])


class FolderWatcher:
    instances = []

    def __init__(self, folder, process, *, on_result, notify):
        self.folder, self.process, self.on_result, self.notify = folder, process, on_result, notify
        self.started = self.stopped = False
        type(self).instances.append(self)

    def start(self): self.started = True
    def stop(self): self.stopped = True; return True


def configured_runtime(workbook_workspace):
    FolderWatcher.instances.clear()
    workbook_workspace.mkdir(exist_ok=True)
    attendance, payroll = workbook_workspace / 'attendance', workbook_workspace / 'payroll'
    attendance.mkdir(); payroll.mkdir()
    service = PayrollService(Repository(Database(workbook_workspace / 'settings.db')))
    runtime = AutomationRuntime(service, folder_watcher_factory=FolderWatcher)
    runtime.workflow.configure(attendance, payroll)
    return runtime


class AcceptedWizard:
    def __init__(self, workflow, parent=None): self.workflow = workflow
    def exec(self): return QDialog.Accepted


def patch_accepted_wizard(monkeypatch):
    monkeypatch.setattr('app.ui.setup_wizard.SetupWizard', AcceptedWizard)


def test_paused_monitoring_stays_paused_when_settings_enable_windows_startup(qt_app, workbook_workspace, monkeypatch):
    runtime = configured_runtime(workbook_workspace)
    runtime.repo.set_setting('watch_enabled', False)
    window = MainWindow(runtime.service, runtime=runtime)
    patch_accepted_wizard(monkeypatch)
    window.settings()
    assert runtime.repo.setting('watch_enabled') is False
    assert runtime.state == RuntimeState.DISABLED and runtime.watcher is None
    assert FolderWatcher.instances == []
    window.close()


def test_active_monitoring_settings_save_reuses_existing_watcher(qt_app, workbook_workspace, monkeypatch):
    runtime = configured_runtime(workbook_workspace)
    assert runtime.resume_monitoring()
    watcher = runtime.watcher
    window = MainWindow(runtime.service, runtime=runtime)
    patch_accepted_wizard(monkeypatch)
    window.settings()
    assert runtime.repo.setting('watch_enabled') is True
    assert runtime.state == RuntimeState.WATCHING and runtime.watcher is watcher
    assert len(FolderWatcher.instances) == 1
    assert runtime.shutdown()
    window.close()


def test_first_run_respects_explicit_pause_but_preserves_unset_first_run_convenience(qt_app, workbook_workspace):
    paused = configured_runtime(workbook_workspace / 'paused')
    paused.repo.set_setting('watch_enabled', False)
    window = MainWindow(paused.service, runtime=paused)
    assert not window._resume_monitoring_after_first_setup()
    assert paused.watcher is None and paused.repo.setting('watch_enabled') is False
    window.close()

    fresh = configured_runtime(workbook_workspace / 'fresh')
    first_window = MainWindow(fresh.service, runtime=fresh)
    assert first_window._resume_monitoring_after_first_setup()
    assert fresh.monitoring_enabled and fresh.state == RuntimeState.WATCHING
    assert fresh.shutdown()
    first_window.close()


def test_explicit_tray_resume_starts_monitoring_normally(qt_app, workbook_workspace):
    runtime = configured_runtime(workbook_workspace)
    runtime.repo.set_setting('watch_enabled', False)
    tray = PayrollTray(runtime, qt_app, show_main_window=lambda _: None)
    tray.resume_action.trigger()
    assert runtime.monitoring_enabled and runtime.state == RuntimeState.WATCHING
    assert len(FolderWatcher.instances) == 1
    assert runtime.shutdown()
    tray.hide()


class FakeWorkflow:
    def __init__(self): self.configured_values = []
    def configuration(self): return {}
    def configure(self, *values): self.configured_values.append(values); return {}


class FakeStartup:
    def __init__(self, *, fail=False): self.fail, self.installs = fail, 0
    def validate(self):
        return StartupStatus(StartupState.NOT_INSTALLED, 'off')
    def install(self):
        self.installs += 1
        status = StartupStatus(StartupState.ERROR if self.fail else StartupState.VALID, 'failed' if self.fail else 'on')
        return StartupResult(not self.fail, status, not self.fail)


def test_setup_save_enables_windows_startup_without_monitoring_control(qt_app):
    workflow, startup = FakeWorkflow(), FakeStartup()
    wizard = SetupWizard(workflow, startup_service=startup)
    wizard.start_with_windows.setChecked(True)
    wizard.save()
    assert len(workflow.configured_values) == 1 and startup.installs == 1
    assert wizard.result() == QDialog.Accepted
    wizard.close()


def test_startup_install_failure_reports_persisted_workflow_partial_change(qt_app):
    workflow, startup = FakeWorkflow(), FakeStartup(fail=True)
    wizard = SetupWizard(workflow, startup_service=startup)
    wizard.start_with_windows.setChecked(True)
    wizard.save()
    assert len(workflow.configured_values) == 1 and startup.installs == 1
    assert wizard.result() != QDialog.Accepted
    assert 'บันทึกโฟลเดอร์แล้ว' in wizard.error.text()
    wizard.close()


def test_first_run_persists_visible_monitoring_choice_without_overwriting_pause(qt_app):
    class Repo:
        def __init__(self, value=None): self.value = value
        def setting(self, key, default=None): return self.value if key == 'watch_enabled' and self.value is not None else default
        def set_setting(self, key, value): self.value = value

    class Workflow(FakeWorkflow):
        def __init__(self, preference=None):
            super().__init__()
            self.repo = Repo(preference)

    workflow, startup = Workflow(), FakeStartup()
    wizard = SetupWizard(workflow, startup_service=startup)
    wizard.start_monitoring.setChecked(False)
    wizard.save()
    assert workflow.repo.value is False and wizard.monitoring_choice_persisted
    wizard.close()

    paused = Workflow(False)
    paused_wizard = SetupWizard(paused, startup_service=FakeStartup())
    assert not paused_wizard.start_monitoring.isEnabled()
    paused_wizard.save()
    assert paused.repo.value is False and not paused_wizard.monitoring_choice_persisted
    paused_wizard.close()


def test_settings_rejects_non_copy_paths_before_attempting_windows_startup(qt_app, workbook_workspace, tmp_path):
    service = PayrollService(Repository(Database(workbook_workspace / 'safety.db')))
    workflow, startup = WorkflowService(service), FakeStartup()
    outside_attendance, outside_payroll = tmp_path / 'attendance', tmp_path / 'payroll'
    outside_attendance.mkdir(); outside_payroll.mkdir()
    wizard = SetupWizard(workflow, startup_service=startup)
    wizard.attendance.setText(str(outside_attendance))
    wizard.payroll.setText(str(outside_payroll))
    wizard.start_with_windows.setChecked(True)
    wizard.save()
    assert workflow.configuration() is None and startup.installs == 0
    assert wizard.result() != QDialog.Accepted
    wizard.close()
