import shutil
from pathlib import Path

import pytest

from app.db.database import Database
from app.db.repositories import Repository
from app.domain import utc_now
from app.excel.workbook_source import file_hash
from app.services.automation_job_service import AutomationJobError, AutomationJobService, AutomationJobState
from app.services.automation_runtime import AutomationRuntime, RuntimeState
from app.services.payroll_service import PayrollService


class FakeFolderWatcher:
    def __init__(self, folder, process, *, on_result, notify):
        self.folder, self.process, self.on_result, self.notify = folder, process, on_result, notify
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        return True


def job_service(workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'jobs.db'))
    return AutomationJobService(repo), repo


def test_durable_job_idempotency_creates_one_job_for_same_content_and_new_one_for_changed_content(workbook_workspace):
    jobs, _ = job_service(workbook_workspace)
    source = workbook_workspace / 'attendance.xlsx'
    source.write_bytes(b'one')
    first, created = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'a'})
    duplicate, duplicate_created = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'a'})
    source.write_bytes(b'two')
    changed, changed_created = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'a'})
    assert created and not duplicate_created and changed_created
    assert first['id'] == duplicate['id']
    assert changed['id'] != first['id']
    assert len(jobs.latest()) == 2


def test_processing_job_recovers_as_failed_after_new_runtime_context(workbook_workspace):
    jobs, _ = job_service(workbook_workspace)
    source = workbook_workspace / 'attendance.xlsx'
    source.write_bytes(b'known bytes')
    job, _ = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'a'})
    claimed, claimed_ok = jobs.claim_pending(job['id'], 'old-process')
    assert claimed_ok and claimed['state'] == AutomationJobState.PROCESSING
    recovered = AutomationJobService(jobs.repo).recover_interrupted()
    saved = jobs.get(job['id'])
    assert recovered['interrupted'] == [job['id']]
    assert saved['state'] == AutomationJobState.FAILED
    assert saved['failure_code'] == 'INTERRUPTED'


def test_pending_jobs_and_completed_idempotency_survive_restart_without_boot_scan(workbook_workspace):
    jobs, _ = job_service(workbook_workspace)
    first_source, second_source = workbook_workspace / 'one.xlsx', workbook_workspace / 'two.xlsx'
    first_source.write_bytes(b'one'); second_source.write_bytes(b'two')
    first, _ = jobs.create(first_source, file_hash(first_source), job_type='FOLDER', context={'workflow': 'a'})
    second, _ = jobs.create(second_source, file_hash(second_source), job_type='FOLDER', context={'workflow': 'a'})
    restarted = AutomationJobService(jobs.repo)
    recovery = restarted.recover_interrupted()
    assert {job['id'] for job in recovery['pending']} == {first['id'], second['id']}
    duplicate, created = restarted.create(first_source, file_hash(first_source), job_type='FOLDER', context={'workflow': 'a'})
    assert not created and duplicate['id'] == first['id']


def test_review_and_failed_jobs_survive_restart_without_window(workbook_workspace):
    jobs, repo = job_service(workbook_workspace)
    source = workbook_workspace / 'attendance.xlsx'
    source.write_bytes(b'known bytes')
    review, _ = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'a'})
    review, _ = jobs.claim_pending(review['id'], 'old-process')
    jobs.finish(review['id'], payroll_run_id=None, review_required=True)
    failed, _ = jobs.create(workbook_workspace / 'failed.xlsx', 'f' * 64, job_type='FOLDER', context={'workflow': 'b'})
    failed, _ = jobs.claim_pending(failed['id'], 'old-process')
    jobs.fail(failed['id'], 'TEST_FAILURE', 'safe failure')
    runtime = AutomationRuntime(PayrollService(repo), folder_watcher_factory=FakeFolderWatcher)
    assert runtime.start()
    assert runtime.state == RuntimeState.REVIEW_REQUIRED
    assert runtime.jobs.get(failed['id'])['state'] == AutomationJobState.FAILED


def test_retry_changed_source_creates_distinct_pending_job_without_processing_new_bytes(workbook_workspace):
    jobs, _ = job_service(workbook_workspace)
    source = workbook_workspace / 'attendance.xlsx'
    source.write_bytes(b'old bytes')
    job, _ = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'a'})
    jobs.claim_pending(job['id'], 'worker')
    jobs.fail(job['id'], 'READ_ERROR', 'safe failure')
    source.write_bytes(b'new bytes')
    original, replacement, created = jobs.retry_source(job['id'])
    assert original is None and created
    assert replacement['state'] == AutomationJobState.PENDING
    assert replacement['source_hash'] == file_hash(source)
    original_saved = jobs.get(job['id'])
    assert original_saved['state'] == AutomationJobState.FAILED
    assert original_saved['attempt_count'] == 2


def test_runtime_retry_claims_same_failed_job_and_persists_attempt_count(copied_reference, workbook_workspace):
    attendance_folder, payroll_folder = workbook_workspace / 'attendance', workbook_workspace / 'payroll'
    attendance_folder.mkdir(); payroll_folder.mkdir()
    source = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    attendance = attendance_folder / source.name
    shutil.copy2(source, attendance)
    service = PayrollService(Repository(Database(workbook_workspace / 'runtime.db')))
    runtime = AutomationRuntime(service, folder_watcher_factory=FakeFolderWatcher)
    runtime.workflow.configure(attendance_folder, payroll_folder)
    job, _ = runtime.jobs.create(attendance, file_hash(attendance), job_type='FOLDER',
                                 context=runtime._job_context('FOLDER'))
    runtime.jobs.claim_pending(job['id'], 'old-process')
    runtime.jobs.fail(job['id'], 'READ_ERROR', 'safe failure')
    result = runtime.retry_job(job['id'])
    saved = runtime.jobs.get(job['id'])
    assert result['automation_job']['id'] == job['id']
    assert saved['attempt_count'] == 2
    assert saved['state'] in {AutomationJobState.COMPLETED, AutomationJobState.REVIEW_REQUIRED}


def test_manual_retry_rejects_changed_manual_configuration_before_claiming(workbook_workspace):
    source, payroll, changed_payroll = (workbook_workspace / name for name in ('manual.xlsx', 'payroll.xlsx', 'changed.xlsx'))
    source.write_bytes(b'known bytes'); payroll.write_bytes(b'payroll'); changed_payroll.write_bytes(b'changed')
    service = PayrollService(Repository(Database(workbook_workspace / 'manual-retry.db')))
    runtime = AutomationRuntime(service, folder_watcher_factory=FakeFolderWatcher)
    runtime.configure_manual_sources(source, payroll, 2026, 9)
    job, _ = runtime.jobs.create(source, file_hash(source), job_type='MANUAL',
                                 context=runtime._job_context('MANUAL', payroll_path=str(payroll), year=2026, month=9),
                                 year=2026, month=9)
    runtime.jobs.claim_pending(job['id'], 'old-worker')
    runtime.jobs.fail(job['id'], 'READ_ERROR', 'safe failure')
    runtime.configure_manual_sources(source, changed_payroll, 2026, 9)

    with pytest.raises(AutomationJobError, match='manual configuration differs'):
        runtime.retry_job(job['id'])

    saved = runtime.jobs.get(job['id'])
    assert saved['state'] == AutomationJobState.FAILED
    assert saved['failure_code'] == 'CONFIGURATION_CHANGED'


def test_review_job_completes_only_after_persisted_ready_run_has_no_pending_source_change(workbook_workspace):
    jobs, repo = job_service(workbook_workspace)
    source = workbook_workspace / 'attendance.xlsx'
    source.write_bytes(b'known bytes')
    with repo.db.transaction() as con:
        con.execute('INSERT INTO payroll_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)',
                    ('run-ready', 2026, 8, 'READY', str(source), file_hash(source), str(source), file_hash(source),
                     1, '{}', utc_now()))
    job, _ = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'a'}, year=2026, month=8)
    jobs.claim_pending(job['id'], 'worker')
    jobs.finish(job['id'], payroll_run_id='run-ready', review_required=True)
    assert jobs.resolve_reviews_for_run(repo.run(2026, 8)) == [job['id']]
    assert jobs.get(job['id'])['state'] == AutomationJobState.COMPLETED
