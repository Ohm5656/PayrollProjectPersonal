from types import SimpleNamespace

from app.services.automation_runtime import RuntimeState
from app.services.windows_startup import StartupState, StartupStatus
from app.ui.overview_model import OverviewViewModel, overview_action, thai_period
from app.ui.overview_page import OverviewPage
from tests.unit.test_draft_engine import calculate, draft_case
from tests.unit.test_ui import qt_app


class FakeService:
    def __init__(self, run=None, draft=None):
        self.run, self.draft = run, draft
        self.calls = []

    def current(self, year, month):
        self.calls.append((year, month))
        return self.run, self.draft


class FakeStartup:
    def __init__(self, state):
        self.state = state
        self.calls = 0

    def validate(self):
        self.calls += 1
        return StartupStatus(self.state, 'fixture')


class FakeJobs:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def latest(self):
        return list(self.rows)


def test_thai_period_uses_buddhist_era_once():
    assert thai_period(2026, 10) == 'ตุลาคม 2569'


def test_overview_empty_snapshot_is_honest_and_read_only():
    service = FakeService()
    startup = FakeStartup(StartupState.UNAVAILABLE)
    runtime = SimpleNamespace(state=RuntimeState.DISABLED, jobs=FakeJobs())
    view = OverviewViewModel(service, runtime=runtime, startup_service=startup)

    snapshot = view.snapshot(2026, 10, selected_sources={'attendance': '', 'payroll': ''})

    assert snapshot.payroll_state == 'NO_DRAFT'
    assert snapshot.employee_count is None and snapshot.review_count is None
    assert snapshot.monitoring_state == RuntimeState.DISABLED
    assert snapshot.startup_state == StartupState.UNAVAILABLE
    assert snapshot.attendance_label == 'ยังไม่ได้เลือกไฟล์สำเนา'
    assert service.calls == [(2026, 10)] and startup.calls == 1


def test_overview_uses_persisted_draft_values_and_matching_job_only(draft_case):
    draft = calculate(draft_case)
    run = {'state': 'NEEDS_REVIEW'}
    runtime = SimpleNamespace(
        state=RuntimeState.REVIEW_REQUIRED,
        jobs=FakeJobs((
            {'period_year': 2026, 'period_month': 8, 'state': 'COMPLETED', 'updated_at': 'old'},
            {'period_year': 2026, 'period_month': 9, 'state': 'REVIEW_REQUIRED', 'updated_at': 'now'},
        )),
    )
    view = OverviewViewModel(FakeService(run, draft), runtime=runtime, writer=object(),
                             startup_service=FakeStartup(StartupState.VALID))

    snapshot = view.snapshot(2026, 9)

    assert snapshot.payroll_state == 'NEEDS_REVIEW'
    assert snapshot.employee_count == 1
    assert snapshot.review_count == len(draft.issues)
    assert snapshot.job_state == 'REVIEW_REQUIRED' and snapshot.job_updated_at == 'now'
    assert snapshot.output_label == 'โหมดเขียนได้เฉพาะไฟล์สำเนา'


def test_overview_output_labels_keep_confirmed_written_and_locked_distinct(draft_case):
    draft = calculate(draft_case)
    view = OverviewViewModel(FakeService({'state': 'CONFIRMED'}, draft), writer=object())
    assert view.snapshot(2026, 9).output_label == 'ยืนยันแล้ว รอเขียนลงไฟล์สำเนา'
    view.service.run = {'state': 'WRITTEN'}
    assert view.snapshot(2026, 9).output_label == 'บันทึกลงไฟล์สำเนาแล้ว'
    view.service.run = {'state': 'LOCKED'}
    assert view.snapshot(2026, 9).payroll_label == 'ปิดรอบเงินเดือนแล้ว'


def test_overview_page_binds_real_snapshot_without_mutating_service(qt_app, draft_case):
    draft = calculate(draft_case)
    service = FakeService({'state': 'NEEDS_REVIEW'}, draft)
    snapshot = OverviewViewModel(service, writer=object()).snapshot(2026, 9)
    page = OverviewPage()
    page.refresh(snapshot)

    assert page.period.text() == 'กันยายน 2569'
    assert page.employee_card.value.text() == '1'
    assert page.review_card.value.text() == f'{len(draft.issues)} รายการ'
    assert page.empty_state.isHidden()
    assert service.calls == [(2026, 9)]


def test_overview_action_maps_each_payroll_state_to_one_safe_explicit_step():
    def action_for(state, **kwargs):
        snapshot = SimpleNamespace(payroll_state=state)
        return overview_action(snapshot, has_sources=True, writer_available=True, busy=False, **kwargs)

    assert action_for('NO_DRAFT').action_id == 'read'
    assert action_for('DRAFT').action_id == 'review'
    assert action_for('NEEDS_REVIEW').action_id == 'review'
    assert action_for('READY').action_id == 'confirm'
    assert action_for('CONFIRMED').action_id == 'write'
    assert action_for('WRITTEN').action_id == 'lock'
    locked = action_for('LOCKED')
    assert locked.action_id is None and not locked.visible


def test_overview_action_disables_missing_sources_writer_and_busy_states():
    snapshot = SimpleNamespace(payroll_state='NO_DRAFT')
    action = overview_action(snapshot, has_sources=False, writer_available=True, busy=False)
    assert not action.enabled and 'เลือกไฟล์สำเนา' in action.detail

    snapshot.payroll_state = 'CONFIRMED'
    action = overview_action(snapshot, has_sources=True, writer_available=False, busy=False)
    assert action.action_id == 'write' and not action.enabled and 'ไม่มีบริการเขียน' in action.detail

    snapshot.payroll_state = 'READY'
    assert not overview_action(snapshot, has_sources=True, writer_available=True, busy=True).enabled
