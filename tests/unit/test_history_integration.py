from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from tests.unit.test_history_model import add_audit
from tests.unit.test_ui import qt_app, draft_case


def test_history_navigation_is_read_only_until_explicit_period_open(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    service.repo.set_setting('watch_enabled', False)
    add_audit(service.repo, 'PAYROLL_CONFIRMED', actor='auditor')
    add_audit(service.repo, 'MONTH_LOCKED', actor='auditor')
    audit_ids_before = [row['id'] for row in service.repo.audit_events(limit=10)]
    mutations = []
    for name in ('prepare', 'confirm', 'reopen', 'lock'):
        monkeypatch.setattr(service, name, lambda *args, _name=name, **kwargs: mutations.append(_name))
    window = MainWindow(service)
    selected_before = (window.year.value(), window.month.value())

    window.history()
    assert window.page_host.currentWidget() is window.history_page
    window.history_page.table.selectRow(0)
    window.history_page.table.setFocus()
    QTest.keyClick(window.history_page.table, Qt.Key_Return)

    assert window.page_host.currentWidget() is window.history_detail_page
    assert (window.year.value(), window.month.value()) == selected_before
    assert window.history_detail_page.timeline.toPlainText().count('\n') == 1
    assert mutations == []
    window.history_detail_page.open_period.click()

    assert (window.year.value(), window.month.value()) == (2026, 9)
    assert window.page_host.currentWidget() is window.overview_page
    assert mutations == []
    assert audit_ids_before == [row['id'] for row in service.repo.audit_events(limit=10)]
    assert service.repo.setting('watch_enabled') is False
    window.close()


def test_history_page_keeps_layout_usable_at_required_offscreen_sizes(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))
    window.show()
    window.history()

    for width, height in ((1366, 768), (1920, 1080), (900, 700)):
        window.resize(width, height)
        qt_app.processEvents()
        assert window.history_page.table.isVisible()
        assert window.history_page.table.width() > 0
        assert window.history_page.inspect.focusPolicy() != Qt.NoFocus

    window.close()
