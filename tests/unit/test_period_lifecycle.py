from PySide6.QtWidgets import QCheckBox, QDialog, QLineEdit, QMessageBox

from app.domain import PayrollState
from app.services.payroll_service import PayrollService
from app.ui.main_window import MainWindow
from tests.unit.test_draft_engine import calculate, draft_case
from tests.unit.test_ui import qt_app


def test_reopen_uses_selected_period_and_does_not_recalculate(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    draft = calculate(draft_case)
    selected = {'state': PayrollState.CONFIRMED, 'id': 'selected-period'}
    calls = []

    def current(year, month):
        return (selected, draft) if (year, month) == (2026, 9) else (None, None)

    def reopen(year, month, *, reason, actor):
        calls.append((year, month, reason, actor))
        selected['state'] = PayrollState.DRAFT

    def accept_with_reason(dialog):
        dialog.findChild(QCheckBox).setChecked(True)
        dialog.findChild(QLineEdit).setText('ตรวจสอบส่วนต่างแล้ว')
        return QDialog.Accepted

    monkeypatch.setattr(service, 'current', current)
    monkeypatch.setattr(service, 'reopen', reopen)
    monkeypatch.setattr(service, 'prepare', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must not recalculate')))
    monkeypatch.setattr(QDialog, 'exec', accept_with_reason)
    window = MainWindow(service)
    window.year.setValue(2026)
    window.month.setValue(9)
    window.run, window.draft = {'state': PayrollState.LOCKED, 'id': 'stale-period'}, draft

    window.reopen()

    assert calls == [(2026, 9, 'ตรวจสอบส่วนต่างแล้ว', window.actor.text())]
    assert window.run['state'] == PayrollState.DRAFT
    window.close()


def test_lock_requires_explicit_confirmation_and_uses_selected_period(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    draft = calculate(draft_case)
    selected = {'state': PayrollState.WRITTEN, 'id': 'selected-period'}
    calls = []

    def current(year, month):
        return (selected, draft) if (year, month) == (2026, 9) else (None, None)

    def lock(year, month, *, actor):
        calls.append((year, month, actor))
        selected['state'] = PayrollState.LOCKED

    monkeypatch.setattr(service, 'current', current)
    monkeypatch.setattr(service, 'lock', lock)
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Yes)
    window = MainWindow(service)
    window.year.setValue(2026)
    window.month.setValue(9)
    window.run, window.draft = {'state': PayrollState.WRITTEN, 'id': 'stale-period'}, draft

    window.lock()

    assert calls == [(2026, 9, window.actor.text())]
    assert window.run['state'] == PayrollState.LOCKED
    window.close()


def test_lock_cancel_keeps_period_unchanged(qt_app, draft_case, monkeypatch):
    service = PayrollService(draft_case[0])
    draft = calculate(draft_case)
    selected = {'state': PayrollState.WRITTEN, 'id': 'selected-period'}

    monkeypatch.setattr(service, 'current', lambda year, month: (selected, draft))
    monkeypatch.setattr(service, 'lock', lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('must confirm first')))
    monkeypatch.setattr(QMessageBox, 'question', lambda *args: QMessageBox.Cancel)
    window = MainWindow(service)

    window.lock()

    assert selected['state'] == PayrollState.WRITTEN
    window.close()
