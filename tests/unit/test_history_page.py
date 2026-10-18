from app.db.database import Database
from app.db.repositories import Repository
from app.ui.history_page import HistoryPage
from PySide6.QtWidgets import QHeaderView
from tests.unit.test_history_model import add_audit
from tests.unit.test_ui import qt_app


def test_history_page_filters_database_backed_pages(qt_app, workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'history-page.db'))
    for actor in ('a', 'b', 'a'): add_audit(repo, 'PAYROLL_CONFIRMED', actor=actor)
    page = HistoryPage(repo, page_size=2)
    assert page.table.rowCount() == 2 and page.next.isEnabled()
    page.actor.setCurrentIndex(page.actor.findData('a'))
    assert page.table.rowCount() == 2 and 'จาก 2' in page.state.text()


def test_history_page_empty_and_stable_selection(qt_app, workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'history-empty.db'))
    page = HistoryPage(repo)
    assert 'ยังไม่มี' in page.state.text()
    add_audit(repo, 'MONTH_LOCKED')
    page.refresh(); page.table.selectRow(0)
    selected = []
    page.event_activated.connect(selected.append)
    page.activate_current()
    assert selected == [repo.audit_events(limit=1)[0]['id']]


def test_history_table_stretches_detail_column_without_changing_paged_query(qt_app, workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'history-width.db'))
    add_audit(repo, 'MONTH_LOCKED')
    page = HistoryPage(repo)

    header = page.table.horizontalHeader()
    assert header.sectionResizeMode(1) is QHeaderView.Stretch
    assert header.minimumSectionSize() >= 96
