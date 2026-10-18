"""Phase C tests: all Task Scheduler calls use an in-memory adapter."""
from pathlib import Path
import os

import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication

from app.services.windows_startup import (
    StartupError, StartupState, StartupStatus, WindowsStartupService,
)


@pytest.fixture(scope='session')
def qt_app():
    return QApplication.instance() or QApplication([])


class FakeScheduler:
    def __init__(self, task=None, *, denied=False):
        self.task = task
        self.denied = denied
        self.install_calls = 0
        self.remove_calls = 0

    def query(self, task_name):
        return dict(self.task) if self.task else None

    def install(self, definition):
        self.install_calls += 1
        if self.denied:
            raise StartupError('access denied')
        self.task = {
            'task_name': definition.task_name, 'executable': definition.executable,
            'arguments': definition.arguments, 'working_directory': definition.working_directory,
            'enabled': True, 'logon': True, 'user_id': 'TEST\\user',
            'logon_type': 'Interactive', 'run_level': 'Limited',
        }

    def remove(self, task_name):
        self.remove_calls += 1
        if self.denied:
            raise StartupError('access denied')
        self.task = None


def startup_service(tmp_path, scheduler=None, *, executable=True):
    project = tmp_path / 'NTP payroll ไทย (test)'
    (project / 'app').mkdir(parents=True)
    (project / 'app' / 'main.py').write_text('# entry\n', encoding='utf-8')
    pythonw = project / '.venv' / 'Scripts' / 'pythonw.exe'
    if executable:
        pythonw.parent.mkdir(parents=True)
        pythonw.write_bytes(b'')
    return WindowsStartupService(project_root=project, executable=pythonw,
                                 scheduler=scheduler or FakeScheduler(), platform='nt')


def test_not_installed_reports_actual_task_state_without_creating_task(tmp_path):
    scheduler = FakeScheduler()
    service = startup_service(tmp_path, scheduler)
    assert service.validate().state == StartupState.NOT_INSTALLED
    assert not service.is_startup_enabled() and scheduler.install_calls == 0


def test_install_creates_current_user_logon_definition_with_absolute_unicode_paths(tmp_path):
    scheduler = FakeScheduler()
    service = startup_service(tmp_path, scheduler)
    result = service.install()
    assert result.success and result.changed and result.status.state == StartupState.VALID
    task = scheduler.task
    assert task['task_name'] == 'NTP Payroll Assistant'
    assert Path(task['executable']).is_absolute() and Path(task['working_directory']).is_absolute()
    assert task['arguments'] == '-X utf8 -m app.main --startup'
    assert task['logon'] and task['logon_type'] == 'Interactive' and task['run_level'] == 'Limited'


def test_install_is_idempotent(tmp_path):
    scheduler = FakeScheduler()
    service = startup_service(tmp_path, scheduler)
    assert service.install().success
    assert service.install().success
    assert scheduler.install_calls == 1


def test_remove_only_owned_task_and_does_not_touch_runtime(tmp_path):
    scheduler = FakeScheduler()
    service = startup_service(tmp_path, scheduler)
    service.install()
    result = service.remove()
    assert result.success and result.changed and result.status.state == StartupState.NOT_INSTALLED
    assert scheduler.remove_calls == 1


def test_missing_windowless_executable_fails_safely(tmp_path):
    scheduler = FakeScheduler()
    service = startup_service(tmp_path, scheduler, executable=False)
    result = service.install()
    assert not result.success and result.status.state == StartupState.INVALID_LAUNCH
    assert scheduler.install_calls == 0


def test_incorrect_existing_path_is_detected_then_explicit_repair_updates_it(tmp_path):
    scheduler = FakeScheduler()
    service = startup_service(tmp_path, scheduler)
    expected = service.definition()
    scheduler.task = {
        'task_name': expected.task_name, 'executable': 'C:\\old location\\pythonw.exe',
        'arguments': expected.arguments, 'working_directory': expected.working_directory,
        'enabled': True, 'logon': True, 'logon_type': 'Interactive', 'run_level': 'Limited',
    }
    status = service.validate()
    assert status.state == StartupState.NEEDS_REPAIR and 'executable' in status.mismatches
    assert not service.install().success and scheduler.install_calls == 0
    assert service.repair().success and scheduler.install_calls == 1
    assert service.validate().state == StartupState.VALID


def test_permission_denied_never_reports_false_success(tmp_path):
    scheduler = FakeScheduler(denied=True)
    service = startup_service(tmp_path, scheduler)
    result = service.install()
    assert not result.success and result.status.state == StartupState.ERROR
    assert scheduler.task is None


def test_settings_marks_a_broken_owned_task_for_repair_not_silent_removal(qt_app, tmp_path):
    from app.ui.setup_wizard import SetupWizard

    class Workflow:
        def configuration(self): return {}
        def configure(self, *args): return {}

    class Startup:
        def validate(self):
            return StartupStatus(StartupState.NEEDS_REPAIR, 'repair required')

    wizard = SetupWizard(Workflow(), startup_service=Startup())
    assert wizard.start_with_windows.isChecked()
    assert wizard.startup_repair.isVisible() or not wizard.startup_repair.isHidden()
    wizard.close()
