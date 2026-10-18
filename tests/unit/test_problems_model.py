from app.db.database import Database
from app.db.repositories import Repository
from app.domain import utc_now
from app.excel.workbook_source import file_hash
from app.services.automation_job_service import AutomationJobService
from app.services.automation_runtime import AutomationRuntime, RuntimeState
from app.services.payroll_service import PayrollService
from app.ui.problems_model import ProblemsViewModel


def _jobs(workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'problems.db'))
    return AutomationJobService(repo), PayrollService(repo)


def _failed(jobs, source, *, code='SOURCE_MISSING', message='safe test failure'):
    source.write_bytes(b'synthetic source')
    job, _ = jobs.create(source, file_hash(source), job_type='FOLDER', context={'workflow': 'synthetic'}, year=2026, month=9)
    jobs.claim_pending(job['id'], 'test-worker')
    return jobs.fail(job['id'], code, message)


def test_problems_model_reports_paused_monitoring_and_empty_bounded_history_without_mutation(workbook_workspace):
    jobs, service = _jobs(workbook_workspace)
    service.repo.set_setting('watch_enabled', False)

    snapshot = ProblemsViewModel(service).snapshot()

    assert snapshot.monitoring.state == 'PAUSED'
    assert snapshot.monitoring.requires_action is False
    assert snapshot.jobs.state == 'CLEAR'
    assert snapshot.configuration.state == 'UNAVAILABLE'
    assert snapshot.recent_jobs == () and snapshot.attention == ()
    assert jobs.latest() == []


def test_problems_model_classifies_persisted_jobs_and_preserves_identity(workbook_workspace):
    jobs, service = _jobs(workbook_workspace)
    known = _failed(jobs, workbook_workspace / 'known.xlsx')
    unknown = _failed(jobs, workbook_workspace / 'unknown.xlsx', code='UNMAPPED_FAILURE', message='opaque safe message')
    pending_source = workbook_workspace / 'pending.xlsx'; pending_source.write_bytes(b'pending')
    jobs.create(pending_source, file_hash(pending_source), job_type='FOLDER', context={'workflow': 'pending'})
    before = jobs.get(known['id'])

    snapshot = ProblemsViewModel(service).snapshot(limit=50)
    by_id = {job.id: job for job in snapshot.recent_jobs}

    assert by_id[known['id']].title == 'ไม่พบไฟล์ต้นทาง'
    assert by_id[known['id']].retryable
    assert by_id[unknown['id']].title == 'งานเบื้องหลังไม่สำเร็จ'
    assert by_id[unknown['id']].detail == 'opaque safe message'
    assert snapshot.jobs.state == 'FAILED'
    assert jobs.get(known['id']) == before


def test_problems_model_keeps_runtime_error_separate_from_job_and_write_health(workbook_workspace):
    jobs, service = _jobs(workbook_workspace)
    backup = workbook_workspace / 'backup.xlsx'; backup.write_bytes(b'backup')
    target = workbook_workspace / 'target.xlsx'
    with service.repo.db.transaction() as con:
        con.execute('INSERT INTO payroll_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)',
                    ('run', 2026, 9, 'CONFIRMED', str(target), 'a' * 64, str(target), 'b' * 64, 1, '{}', utc_now()))
        con.execute('INSERT INTO write_operations VALUES (?,?,?,?,?,?,?,?,?,?)',
                    ('write', 'run', 'STAGED', str(target), str(backup), file_hash(backup), None, None, utc_now(), None))
    runtime = AutomationRuntime(service)
    runtime.state = RuntimeState.ERROR
    runtime._health_fault = ('PATH_UNAVAILABLE', 'configured folder is unavailable')

    snapshot = ProblemsViewModel(service, runtime=runtime).snapshot()

    assert snapshot.monitoring.state == RuntimeState.ERROR
    assert snapshot.jobs.state == 'CLEAR'
    assert snapshot.writes.state == 'STAGED_REQUIRES_REVIEW'
    assert snapshot.staged_writes[0]['operation_id'] == 'write'
    assert runtime.watcher is None
