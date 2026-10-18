from app.services.automation_runtime import AutomationRuntime
from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from app.ui.tray import PayrollTray
from tests.unit.test_ui import qt_app, draft_case


def test_main_window_has_thai_first_shell_and_page_host(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))

    assert window.sidebar.objectName() == 'sidebar'
    assert set(window.navigation_buttons) == {'overview', 'review', 'history', 'problems', 'settings'}
    assert window.page_host.count() == 6
    assert window.page_host.currentWidget() is window.overview_page
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


def test_compatibility_controls_remain_in_overview_page(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))

    for control in (
        window.read_button, window.review_button, window.profile_button, window.confirm_button,
        window.write_button, window.slips_button, window.month8_uat_button, window.copy_button,
    ):
        assert control.parentWidget() is not None
        assert window.compatibility_page.isAncestorOf(control)
    assert window.overview_page.employee_section.isAncestorOf(window.table)
    assert window.read_button.property('role') == 'primary'
    window.close()


def test_tray_shortcuts_keep_public_window_entry_points(qt_app, draft_case, monkeypatch):
    runtime = AutomationRuntime(PayrollService(draft_case[0]), qt_app)
    window = MainWindow(runtime.service, runtime=runtime)
    tray = PayrollTray(runtime, qt_app, show_main_window=lambda _: window.show(), get_window=lambda: window)
    calls = []
    monkeypatch.setattr(window, 'review', lambda: calls.append('review'))
    monkeypatch.setattr(window, 'history', lambda: calls.append('history'))
    monkeypatch.setattr(window, 'settings', lambda: calls.append('settings'))
    monkeypatch.setattr(window, 'open_copy', lambda kind: calls.append(kind))

    tray.open_review()
    tray.open_history()
    tray.open_settings()
    tray.open_copy('attendance')
    tray.open_copy('payroll')

    assert calls == ['review', 'history', 'settings', 'attendance', 'payroll']
    assert runtime.watcher is None
    tray.hide()
    window.close()


def test_compatibility_routing_does_not_resume_monitoring(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    runtime = AutomationRuntime(service, qt_app)
    service.repo.set_setting('watch_enabled', False)
    window = MainWindow(service, runtime=runtime)
    resume_calls = []
    monkeypatch.setattr(runtime, 'resume_monitoring', lambda: resume_calls.append(True))

    window.navigate_to('settings')
    window.navigate_to('review')
    window.open_copy('attendance')

    assert resume_calls == []
    assert runtime.watcher is None
    assert service.repo.setting('watch_enabled') is False
    window.close()


def test_shell_keeps_navigation_readable_at_desktop_and_compact_widths(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))
    window.show()

    window.resize(1366, 768)
    qt_app.processEvents()
    assert window.sidebar.minimumWidth() == 220
    assert window.minimumWidth() == 860

    window.resize(1920, 1080)
    qt_app.processEvents()
    assert window.sidebar.minimumWidth() == 220
    assert window.overview_page.primary_action.isVisible()
    window.attendance.setText('attendance-copy.xlsx')
    window.payroll.setText('payroll-copy.xlsx')
    window.refresh_overview()
    assert window.overview_page.primary_action.isEnabled()
    window.overview_page.primary_action.setFocus()
    qt_app.processEvents()
    assert window.overview_page.primary_action.hasFocus()

    window.resize(900, 700)
    qt_app.processEvents()
    assert window.sidebar.minimumWidth() == 180
    assert all(button.text() for button in window.navigation_buttons.values())
    assert all(button.focusPolicy() for button in window.navigation_buttons.values())
    window.close()


def test_legacy_dashboard_cards_are_not_presented_alongside_overview(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))

    assert window._legacy_cards.isHidden()
    assert window._legacy_cards.parentWidget() is window.compatibility_page
    window.close()


def test_overview_primary_action_is_explicit_and_requires_sources(qt_app, draft_case, monkeypatch):
    window = MainWindow(PayrollService(draft_case[0]))
    calls = []
    monkeypatch.setattr(window, 'read_draft', lambda: calls.append('read'))

    window.refresh_overview()
    assert not window.overview_page.primary_action.isEnabled()

    window.attendance.setText('attendance-copy.xlsx')
    window.payroll.setText('payroll-copy.xlsx')
    window.refresh_overview()
    assert window.overview_page.primary_action.isEnabled()
    window.overview_page.primary_action.click()

    assert calls == ['read']
    window.close()


def test_background_result_for_another_period_does_not_replace_selected_context(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    window = MainWindow(service)
    _, _, attendance, payroll = draft_case
    from tests.unit.test_draft_engine import calculate
    result_draft = calculate(draft_case)
    selected_run = {'state': 'READY', 'revision': 3}
    selected_draft = object()
    window.run, window.draft = selected_run, selected_draft
    window.year.setValue(2026)
    window.month.setValue(10)
    monkeypatch.setattr(window.workflow, 'configured', lambda: True)
    monkeypatch.setattr(service, 'current', lambda year, month: ({'state': 'NEEDS_REVIEW', 'revision': 4}, result_draft))

    window.receive_watched_result({'run': {'state': 'NEEDS_REVIEW'}, 'draft': result_draft})

    assert window.run is selected_run and window.draft is selected_draft
    assert '9/2569' in window.statusBar().currentMessage()
    window.close()
