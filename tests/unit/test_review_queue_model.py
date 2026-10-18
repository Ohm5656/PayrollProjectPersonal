from dataclasses import replace

from app.domain import ReviewIssue
from app.ui.review_queue_model import ReviewQueueModel, thai_date
from tests.unit.test_draft_engine import calculate, draft_case


def test_review_queue_empty_is_period_scoped_and_read_only(draft_case):
    draft = replace(calculate(draft_case), global_issues=(), employees=())

    snapshot = ReviewQueueModel().snapshot(draft, year=2026, month=9)

    assert snapshot.period_label == 'กันยายน 2569'
    assert snapshot.items == () and snapshot.critical_count == snapshot.warning_count == 0


def test_review_queue_classifies_orders_and_preserves_evidence(draft_case):
    draft = calculate(draft_case)
    employee = draft.employees[0]
    issues = (
        ReviewIssue('warning', 'FIELD', employee.employee_id, employee.sheet, '2026-09-02', 'P2', 'field',
                    raw_text='10', critical=False, field='bonus'),
        ReviewIssue('source', 'SOURCE_PARSE', None, 'Attendance', None, 'A1', 'source', raw_text='bad'),
        ReviewIssue('leave', 'LEAVE', employee.employee_id, employee.sheet, '2026-09-01', 'D3', 'leave', raw_text='ลา'),
    )
    draft = replace(draft, global_issues=(issues[1],), employees=(replace(employee, issues=(issues[0], issues[2])),))

    snapshot = ReviewQueueModel().snapshot(draft, year=2026, month=9)

    assert [item.issue.key for item in snapshot.items] == ['leave', 'source', 'warning']
    assert snapshot.critical_count == 2 and snapshot.warning_count == 1
    assert snapshot.items[0].employee_name == employee.name
    assert snapshot.items[1].action_kind == 'source_correction'
    assert snapshot.items[2].category == 'FINANCIAL'
    assert snapshot.items[2].source_reference == f'{employee.sheet} / P2'


def test_review_queue_represents_unknown_employee_global_and_missing_evidence(draft_case):
    draft = calculate(draft_case)
    unknown = ReviewIssue('identity', 'IDENTITY', 'missing-id', None, None, None, 'identity', critical=True)
    global_issue = ReviewIssue('global', 'PAYSLIP_MAPPING', None, None, None, None, 'mapping', critical=False)
    draft = replace(draft, global_issues=(unknown, global_issue), employees=())

    snapshot = ReviewQueueModel().snapshot(draft, year=2026, month=9)

    assert snapshot.items[0].employee_name == 'ไม่พบข้อมูลพนักงาน'
    assert snapshot.items[1].employee_name == 'ข้อมูลส่วนกลาง'
    assert snapshot.items[1].action_kind == 'payslip'
    assert thai_date(None) == '' and thai_date('not-a-date') == 'not-a-date'
