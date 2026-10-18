from app.domain import ReviewIssue
from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from tests.unit.test_draft_engine import calculate, draft_case
from tests.unit.test_ui import qt_app


def test_critical_source_issue_explains_correction_without_opening_decision(qt_app, draft_case, monkeypatch):
    window = MainWindow(PayrollService(draft_case[0]))
    messages = []
    monkeypatch.setattr('app.ui.main_window.QMessageBox.information', lambda *args: messages.append(args[2]))
    issue = ReviewIssue('source', 'SOURCE_PARSE', None, 'Attendance', None, 'A1', 'bad', critical=True)

    window._review_issue_selected(issue)

    assert messages and 'แก้ไขไฟล์สำเนา' in messages[0]
    window.close()


def test_queue_decision_uses_existing_dialog_then_authoritative_recalculation(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    window = MainWindow(service)
    draft = calculate(draft_case)
    issue = draft.issues[0]
    calls = []
    monkeypatch.setattr(service, 'current', lambda year, month: ({'state': 'NEEDS_REVIEW'}, draft))

    class AcceptedDialog:
        def __init__(self, *args, **kwargs):
            calls.append('dialog')
        def exec(self):
            from PySide6.QtWidgets import QDialog
            return QDialog.Accepted

    monkeypatch.setattr('app.ui.main_window.DecisionDialog', AcceptedDialog)
    monkeypatch.setattr(window, '_recalculate_after_review', lambda selected: calls.append(('recalculate', selected.source_hash)))
    window._review_issue_selected(issue)

    assert calls == ['dialog', ('recalculate', draft.source_hash)]
    window.close()
