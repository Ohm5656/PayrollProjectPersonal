import os

import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication

from app.services.windows_startup import StartupState, StartupStatus
from app.ui.settings_model import SettingsViewModel
from app.ui.settings_page import SettingsPage


class Workflow:
    class Repo:
        def __init__(self): self.values = {'watch_enabled': False}
        def setting(self, key, default=None): return self.values.get(key, default)
    def __init__(self): self.repo = self.Repo()
    def configuration(self):
        return {'attendance_folder': '', 'payroll_folder': '', 'template_path': ''}


class Startup:
    def __init__(self): self.calls = 0; self.state = StartupState.NOT_INSTALLED
    def validate(self):
        self.calls += 1
        return StartupStatus(self.state, 'fixture')


@pytest.fixture(scope='session')
def qt_app():
    return QApplication.instance() or QApplication([])


def test_settings_page_keeps_dirty_fields_when_refreshing_status(qt_app):
    startup = Startup()
    page = SettingsPage(SettingsViewModel(Workflow(), startup_service=startup))
    page.load()
    page.attendance.edit.setText('edited-attendance')
    page.start_with_windows.setChecked(True)

    page.refresh_status()

    assert page.attendance.edit.text() == 'edited-attendance'
    assert page.start_with_windows.isChecked()
    assert page.is_dirty() and startup.calls == 2
    page.close()


def test_settings_page_emits_explicit_save_payload_without_mutating_services(qt_app):
    workflow, startup = Workflow(), Startup()
    page = SettingsPage(SettingsViewModel(workflow, startup_service=startup))
    page.load()
    requests = []
    page.save_requested.connect(requests.append)
    page.attendance.edit.setText('attendance')
    page.save.click()

    assert requests == [{'attendance_folder': 'attendance', 'payroll_folder': '', 'template_path': '', 'start_with_windows': False}]
    assert workflow.repo.setting('watch_enabled') is False and startup.calls == 1
    page.close()
