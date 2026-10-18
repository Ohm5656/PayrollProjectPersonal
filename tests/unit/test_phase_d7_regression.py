from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.services.automation_runtime import AutomationRuntime
from app.services.payroll_service import PayrollService
from app.services.windows_startup import StartupState, StartupStatus
from app.ui.main_window import MainWindow
from app.ui.tray import PayrollTray
from tests.unit.test_ui import qt_app, draft_case


class FakeStartup:
    def validate(self):
        return StartupStatus(StartupState.NOT_INSTALLED, 'synthetic fixture')


def test_phase_d7_navigation_and_period_context_do_not_mutate_runtime(qt_app, draft_case):
    service = PayrollService(draft_case[0])
    service.repo.set_setting('watch_enabled', False)
    runtime = AutomationRuntime(service, qt_app)
    window = MainWindow(service, runtime=runtime, startup_service=FakeStartup())
    initial = (window.year.value(), window.month.value())

    for page_id in ('overview', 'review', 'history', 'problems', 'settings'):
        assert window.navigate_to(page_id)
    window.year.setValue(2028)
    window.month.setValue(4)

    assert initial != (window.year.value(), window.month.value())
    assert runtime.watcher is None
    assert service.repo.setting('watch_enabled', None) is False
    window.close()


def test_phase_d7_tray_navigation_keeps_monitoring_paused(qt_app, draft_case):
    service = PayrollService(draft_case[0])
    service.repo.set_setting('watch_enabled', False)
    runtime = AutomationRuntime(service, qt_app)
    window = MainWindow(service, runtime=runtime, startup_service=FakeStartup())
    tray = PayrollTray(runtime, qt_app, show_main_window=lambda _: window.show(), get_window=lambda: window)

    tray.open_review(); tray.open_history(); tray.open_settings()

    assert window.page_host.currentWidget() is window.settings_page
    assert runtime.watcher is None and service.repo.setting('watch_enabled', None) is False
    tray.hide(); window.close()


def test_phase_d7_keyboard_table_selection_is_read_only(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]), startup_service=FakeStartup())
    window.navigate_to('history')
    window.history_page.table.setFocus()
    QTest.keyClick(window.history_page.table, Qt.Key_Down)

    assert window.history_page.table.focusPolicy() != Qt.NoFocus
    assert window.page_host.currentWidget() is window.history_page
    window.close()
