from dataclasses import replace

from app.domain import ReviewIssue
from app.ui.review_queue_model import ReviewQueueModel
from app.ui.review_queue_page import ReviewQueuePage
from tests.unit.test_draft_engine import calculate, draft_case
from tests.unit.test_ui import qt_app


def queue_snapshot(draft_case):
    draft = calculate(draft_case)
    employee = draft.employees[0]
    issues = (
        ReviewIssue('leave', 'LEAVE', employee.employee_id, employee.sheet, '2026-09-02', 'D2', 'leave', critical=True),
        ReviewIssue('field', 'FIELD', employee.employee_id, employee.sheet, None, 'P2', 'field', critical=False, field='bonus'),
    )
    draft = replace(draft, global_issues=(), employees=(replace(employee, issues=issues),))
    return ReviewQueueModel().snapshot(draft, year=2026, month=9)


def test_review_queue_renders_real_summary_and_filters(qt_app, draft_case):
    page = ReviewQueuePage()
    page.refresh(queue_snapshot(draft_case))

    assert page.table.rowCount() == 2
    assert not page.table.isHidden() and page.empty_state.isHidden()
    assert page.critical_card.value.text() == '1 รายการ'
    assert page.warning_card.value.text() == '1 รายการ'
    page.severity.setCurrentIndex(page.severity.findData('CRITICAL'))
    assert page.table.rowCount() == 1
    page.search.setText('no match')
    assert page.table.rowCount() == 0 and 'ไม่พบรายการ' in page.empty.text()
    assert page.table.isHidden() and not page.empty_state.isHidden()


def test_review_queue_selection_and_empty_state_are_non_mutating(qt_app, draft_case):
    page = ReviewQueuePage()
    activated = []
    page.issue_activated.connect(lambda issue: activated.append(issue.key))
    page.refresh(queue_snapshot(draft_case))
    page.table.selectRow(0)
    page.activate_current()
    assert activated == ['leave']

    page.refresh(ReviewQueueModel().snapshot(None, year=2026, month=9))
    assert page.table.rowCount() == 0 and not page.to_overview_button.isHidden()
    assert page.table.isHidden() and not page.empty_state.isHidden()
