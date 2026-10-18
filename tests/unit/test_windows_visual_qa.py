from PySide6.QtWidgets import QMessageBox

from app.services.payroll_service import PayrollService
from app.services.windows_startup import StartupState, StartupStatus
from app.ui.main_window import MainWindow
from tests.unit.test_ui import qt_app, draft_case


class FakeStartup:
    def validate(self):
        return StartupStatus(StartupState.NOT_INSTALLED, 'synthetic QA fixture')


def test_all_primary_pages_render_at_safe_offscreen_windows_viewports(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]), startup_service=FakeStartup())
    window.show()
    for width, height in ((1920, 1080), (1366, 768), (1024, 768), (900, 700)):
        window.resize(width, height)
        for page_id in ('overview', 'review', 'history', 'problems', 'settings'):
            assert window.navigate_to(page_id)
            qt_app.processEvents()
            assert window.page_host.currentWidget().isVisible()
            assert window.page_header.title.text()
            assert window.period_context.isVisible()
    window.close()


def test_cancelled_settings_navigation_restores_accurate_sidebar_state(qt_app, draft_case, monkeypatch):
    window = MainWindow(PayrollService(draft_case[0]), startup_service=FakeStartup())
    window.navigate_to('settings')
    window.settings_page.attendance.edit.setText('unsaved synthetic path')
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.No)

    assert not window.navigate_to('history')
    assert window.page_host.currentWidget() is window.settings_page
    assert window.navigation_buttons['settings'].isChecked()
    assert not window.navigation_buttons['history'].isChecked()
    window.close()
