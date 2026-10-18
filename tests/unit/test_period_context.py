from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from app.ui.overview_model import thai_period
from tests.unit.test_ui import qt_app, draft_case


def test_shared_period_context_uses_authoritative_controls_and_buddhist_era(qt_app, draft_case):
    service = PayrollService(draft_case[0])
    service.repo.set_setting('watch_enabled', False)
    window = MainWindow(service)
    before = service.current(2026, 10)

    window.year.setValue(2026)
    window.month.setValue(9)

    assert window.period_context.parentWidget() is not window.compatibility_page
    assert window.period_context_label.text() == thai_period(2026, 9)
    assert window.overview_page.period.text() == thai_period(2026, 9)
    assert window.review_queue_page.period.text() == thai_period(2026, 9)
    assert service.current(2026, 10) == before
    assert service.repo.setting('watch_enabled', None) is False
    window.close()


def test_navigation_metadata_is_current_and_legacy_page_has_honest_parent(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))

    assert all('Phase D.' not in subtitle for _, subtitle in window.page_metadata.values())
    window.show_legacy_workflow()

    assert window.navigation_buttons['overview'].isChecked()
    assert window.page_header.title.text() == 'เครื่องมือเพิ่มเติม'
    window.close()


def test_no_draft_period_refresh_is_read_only(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    window = MainWindow(service)
    calls = []
    for name in ('prepare', 'confirm', 'lock', 'reopen'):
        monkeypatch.setattr(service, name, lambda *args, _name=name, **kwargs: calls.append(_name))

    window.year.setValue(2035)
    window.month.setValue(1)

    assert not window.overview_page.empty_state.isHidden()
    assert window.review_queue_page.period.text() == thai_period(2035, 1)
    assert calls == [] and window.runtime is None
    window.close()
