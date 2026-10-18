from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from tests.unit.test_ui import qt_app, draft_case


def test_main_window_has_thai_first_shell_and_page_host(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))

    assert window.sidebar.objectName() == 'sidebar'
    assert set(window.navigation_buttons) == {'overview', 'review', 'history', 'problems', 'settings'}
    assert window.page_host.count() == 5
    assert window.page_host.currentWidget() is window.compatibility_scroll
    assert window.navigation_buttons['overview'].isChecked()
    assert window.page_header.title.text() == 'ภาพรวม'
    window.close()


def test_navigation_changes_only_presentation_state(qt_app, draft_case):
    service = PayrollService(draft_case[0])
    service.repo.set_setting('watch_enabled', False)
    window = MainWindow(service)

    for page_id, title in (
        ('review', 'รอตรวจสอบ'), ('history', 'ประวัติ'), ('problems', 'ปัญหาและการกู้คืน'),
        ('settings', 'ตั้งค่า'), ('overview', 'ภาพรวม'),
    ):
        window.navigate_to(page_id)
        assert window.page_header.title.text() == title
        assert window.navigation_buttons[page_id].isChecked()
        assert window.page_host.currentIndex() == window._page_indexes[page_id]
        assert service.repo.setting('watch_enabled') is False
    window.close()
