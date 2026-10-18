import pytest

from app.db.database import Database
from app.db.repositories import Repository
from app.ui.history_model import HistoryViewModel, decode_audit_value, thai_timestamp


def add_audit(repo, action, *, year=2026, month=9, actor='tester', old=None, new=None):
    with repo.db.transaction() as con:
        Repository.audit(con, action, year=year, month=month, actor=actor, old=old, new=new)


@pytest.fixture
def repository(workbook_workspace):
    return Repository(Database(workbook_workspace / 'history.db'))


def test_audit_events_are_bounded_filtered_and_keep_legacy_history(repository):
    add_audit(repository, 'PAYROLL_CONFIRMED', actor='a')
    add_audit(repository, 'MONTH_LOCKED', actor='b')
    add_audit(repository, 'MONTH_REOPENED', year=2027, month=1, actor='a')

    page = repository.audit_events(limit=2, actor='a')
    assert len(page) == 2 and page[0]['id'] > page[1]['id']
    assert repository.audit_event_count(actor='a') == 2
    assert repository.audit_events(year=2027, month=1)[0]['action'] == 'MONTH_REOPENED'
    assert set(repository.audit_history()[0]) == {'timestamp', 'action', 'year', 'month', 'actor'}


def test_history_model_formats_payloads_and_thailand_time_without_mutating(repository):
    add_audit(repository, 'PAYROLL_CONFIRMED', old={'state': 'READY'}, new={'state': 'CONFIRMED'})
    row = repository.audit_events(limit=1)[0]
    event = HistoryViewModel().event(row)
    assert event.action_label == 'ยืนยันเงินเดือน'
    assert event.period_label == 'กันยายน 2569'
    assert event.old_value == {'state': 'READY'} and event.new_value == {'state': 'CONFIRMED'}
    assert thai_timestamp('2026-09-01T00:00:00Z') == '01/09/2569 07:00'
    assert decode_audit_value('{bad') == '{bad' and decode_audit_value(None) is None
