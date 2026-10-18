from types import SimpleNamespace

from app.services.automation_runtime import RuntimeState
from app.services.windows_startup import StartupState, StartupStatus
from app.ui.overview_model import OverviewViewModel, thai_period
from tests.unit.test_draft_engine import calculate, draft_case


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
