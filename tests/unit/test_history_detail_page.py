from app.ui.history_detail_page import HistoryDetailPage, display_value
from app.ui.history_model import HistoryViewModel
from tests.unit.test_history_model import add_audit
from app.db.database import Database
from app.db.repositories import Repository
from tests.unit.test_ui import qt_app


def test_history_detail_preserves_payload_and_only_emits_explicit_period_navigation(qt_app, workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'history-detail.db'))
    add_audit(repo, 'PAYROLL_CONFIRMED', old={'zero': 0}, new={'state': 'CONFIRMED'})
    event = HistoryViewModel().event(repo.audit_events(limit=1)[0])
    page = HistoryDetailPage(); opened = []
    page.period_requested.connect(lambda year, month: opened.append((year, month)))
    page.refresh(event.__dict__)
    assert '0' in page.before.toPlainText() and 'CONFIRMED' in page.after.toPlainText()
    assert opened == []
    page.open_period.click()
    assert opened == [(2026, 9)]
    assert display_value(None) == 'ไม่มีข้อมูลที่บันทึกไว้'
