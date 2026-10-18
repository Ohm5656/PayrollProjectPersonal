from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QCheckBox

from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from app.ui.theme import stylesheet
from tests.unit.test_ui import qt_app, draft_case


def test_checkbox_checked_state_has_explicit_checkmark_and_keyboard_toggle(qt_app):
    checkbox = QCheckBox('ยืนยันการตรวจสอบ')
    checkbox.setStyleSheet(stylesheet())
    checkbox.show(); checkbox.setFocus()
    QTest.keyClick(checkbox, Qt.Key_Space)

    assert checkbox.isChecked()
    assert 'checkmark.svg' in stylesheet()
    assert checkbox.focusPolicy() != Qt.NoFocus
    checkbox.close()


def test_empty_and_busy_feedback_remain_honest_and_do_not_mutate_payroll(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    window = MainWindow(service)
    actions = []
    for name in ('prepare', 'confirm', 'lock', 'reopen'):
        monkeypatch.setattr(service, name, lambda *args, _name=name, **kwargs: actions.append(_name))

    window.year.setValue(2037)
    window.month.setValue(2)
    window.navigate_to('review')
    assert 'ยังไม่มีรายการรอตรวจสอบ' in window.review_queue_page.empty.text()
    window.busy = True
    window.refresh_overview()

    assert not window.overview_page.primary_action.isEnabled()
    assert 'กำลังประมวลผล' in window.overview_page.next_action_text.text()
    assert actions == []
    window.close()


def test_navigation_moves_focus_to_current_page_button(qt_app, draft_case):
    window = MainWindow(PayrollService(draft_case[0]))
    window.show()
    window.navigate_to('problems')
    qt_app.processEvents()

    assert window.navigation_buttons['problems'].hasFocus()
    assert window.problems_page.table.focusPolicy() != Qt.NoFocus
    window.close()
