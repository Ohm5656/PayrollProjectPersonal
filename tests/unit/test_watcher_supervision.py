"""Phase B.1 operational watcher supervision and boot reconciliation tests."""
import shutil
import os
from pathlib import Path

import pytest
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtWidgets import QApplication

from app.db.database import Database
from app.db.repositories import Repository
from app.excel.workbook_source import file_hash
from app.services.automation_job_service import AutomationJobState
from app.services.automation_runtime import AutomationRuntime, RuntimeState
from app.services.payroll_service import PayrollService
from app.services.watcher import WatcherHealth


@pytest.fixture(scope='session')
def qt_app():
    return QApplication.instance() or QApplication([])


class HealthWatcher:
    instances = []
    next_health = WatcherHealth.HEALTHY
    next_stop = True

    def __init__(self, folder, process, *, on_result, notify):
        self.folder, self.process, self.on_result, self.notify = folder, process, on_result, notify
        self.health_state = type(self).next_health
        self.stop_outcome = type(self).next_stop
        self.started = self.stopped = False
        type(self).instances.append(self)

    def start(self):
        self.started = True

    def health(self):
        return self.health_state if self.started else WatcherHealth.NOT_STARTED

    def stop(self):
        if self.stop_outcome:
            self.stopped = True
        return self.stop_outcome


def runtime_for(workbook_workspace, label=None):
    HealthWatcher.instances.clear()
    HealthWatcher.next_health, HealthWatcher.next_stop = WatcherHealth.HEALTHY, True
    root = workbook_workspace / label if label else workbook_workspace
    root.mkdir(exist_ok=True)
    attendance, payroll = root / 'attendance', root / 'payroll'
    attendance.mkdir(); payroll.mkdir()
    runtime = AutomationRuntime(PayrollService(Repository(Database(root / 'supervision.db'))),
                                folder_watcher_factory=HealthWatcher)
    runtime.workflow.configure(attendance, payroll)
    assert runtime.resume_monitoring()
    return runtime, attendance


def test_healthy_watcher_remains_watching(qt_app, workbook_workspace):
    runtime, _ = runtime_for(workbook_workspace)
    runtime._supervise_watcher()
    assert runtime.state == RuntimeState.WATCHING
    assert len(HealthWatcher.instances) == 1
    assert runtime.shutdown()


def test_dead_observer_is_reported_once_and_safely_restarted(qt_app, workbook_workspace):
    runtime, _ = runtime_for(workbook_workspace)
    notices = []
    runtime.notification.connect(lambda title, text: notices.append((title, text)))
    first = runtime.watcher
    first.health_state = WatcherHealth.OBSERVER_DEAD
    runtime._supervise_watcher()
    runtime._supervise_watcher()
    assert runtime.state == RuntimeState.ERROR
    assert len(notices) == 1
    assert runtime._attempt_watcher_recovery()
    assert first.stopped and len(HealthWatcher.instances) == 2
    assert runtime.watcher is HealthWatcher.instances[-1]
    assert runtime.state == RuntimeState.WATCHING
    assert runtime.shutdown()


def test_unstoppable_dead_watcher_blocks_replacement(qt_app, workbook_workspace):
    runtime, _ = runtime_for(workbook_workspace)
    first = runtime.watcher
    first.health_state, first.stop_outcome = WatcherHealth.OBSERVER_DEAD, False
    runtime._supervise_watcher()
    assert not runtime._attempt_watcher_recovery()
    assert runtime.state == RuntimeState.ERROR
    assert runtime.watcher is first
    assert len(HealthWatcher.instances) == 1
    first.stop_outcome = True
    assert runtime.shutdown()


def test_missing_folder_leaves_watching_and_recovers_when_it_returns(qt_app, workbook_workspace):
    runtime, folder = runtime_for(workbook_workspace)
    first = runtime.watcher
    folder.rmdir()
    first.health_state = WatcherHealth.PATH_UNAVAILABLE
    runtime._supervise_watcher()
    assert runtime.state == RuntimeState.ERROR
    assert not runtime._attempt_watcher_recovery()
    assert runtime.watcher is first
    folder.mkdir()
    # A live old thread is not trusted after delete/recreate; the path fault
    # remains latched until the old watcher is safely replaced.
    first.health_state = WatcherHealth.HEALTHY
    runtime._supervise_watcher()
    assert runtime.state == RuntimeState.ERROR and runtime.watcher is first
    assert runtime._attempt_watcher_recovery()
    assert first.stopped and runtime.state == RuntimeState.WATCHING
    assert runtime.shutdown()


def test_pause_and_shutdown_suppress_supervisor_restarts(qt_app, workbook_workspace):
    runtime, _ = runtime_for(workbook_workspace)
    runtime.watcher.health_state = WatcherHealth.OBSERVER_DEAD
    assert runtime.pause_monitoring()
    runtime._supervise_watcher()
    assert runtime.state == RuntimeState.DISABLED and len(HealthWatcher.instances) == 1
    assert runtime.resume_monitoring()
    runtime.watcher.health_state = WatcherHealth.OBSERVER_DEAD
    runtime._supervise_watcher()
    generation = runtime._restart_generation
    assert runtime.shutdown()
    assert not runtime._attempt_watcher_recovery(generation)
    assert len(HealthWatcher.instances) == 2


def reconciliation_runtime(copied_reference, workbook_workspace, label):
    runtime, attendance = runtime_for(workbook_workspace, label)
    runtime.pause_monitoring()
    source = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    target = attendance / source.name
    shutil.copy2(source, target)
    # Model a new process reading the persisted enabled preference; do not
    # call resume_monitoring(), which intentionally only starts a watcher.
    runtime.repo.set_setting('watch_enabled', True)
    return runtime, target


def complete_job(runtime, source):
    job, _ = runtime.jobs.create(source, file_hash(source), job_type='FOLDER', context=runtime._job_context('FOLDER'))
    runtime.jobs.claim_pending(job['id'], 'old-worker')
    runtime.jobs.finish(job['id'], payroll_run_id=None, review_required=False)
    return job


def test_startup_offline_changed_file_creates_new_job_but_unchanged_file_does_not(qt_app, copied_reference, workbook_workspace):
    runtime, source = reconciliation_runtime(copied_reference, workbook_workspace, 'changed')
    old = complete_job(runtime, source)
    source.write_bytes(source.read_bytes() + b'\n')  # ZIP permits an inert trailing byte; content identity changes.
    assert runtime.start()
    changed = [job for job in runtime.jobs.latest() if job['source_hash'] == file_hash(source)]
    assert len(changed) == 1 and changed[0]['id'] != old['id']
    assert runtime.shutdown()

    runtime, source = reconciliation_runtime(copied_reference, workbook_workspace, 'unchanged')
    old = complete_job(runtime, source)
    assert runtime.start()
    assert len(runtime.jobs.latest()) == 1 and runtime.jobs.latest()[0]['id'] == old['id']
    assert runtime.shutdown()


def test_startup_pending_matching_changed_and_missing_sources_are_classified(qt_app, copied_reference, workbook_workspace):
    runtime, source = reconciliation_runtime(copied_reference, workbook_workspace, 'matching')
    matching, _ = runtime.jobs.create(source, file_hash(source), job_type='FOLDER', context=runtime._job_context('FOLDER'))
    assert runtime.start()
    assert runtime.jobs.get(matching['id'])['state'] in {AutomationJobState.COMPLETED, AutomationJobState.REVIEW_REQUIRED}
    assert runtime.shutdown()

    runtime, source = reconciliation_runtime(copied_reference, workbook_workspace, 'pending-changed')
    changed, _ = runtime.jobs.create(source, file_hash(source), job_type='FOLDER', context=runtime._job_context('FOLDER'))
    source.write_bytes(source.read_bytes() + b'\n')
    assert runtime.start()
    assert runtime.jobs.get(changed['id'])['failure_code'] == 'SOURCE_CHANGED_OFFLINE'
    assert any(job['id'] != changed['id'] and job['source_hash'] == file_hash(source) for job in runtime.jobs.latest())
    assert runtime.shutdown()

    runtime, source = reconciliation_runtime(copied_reference, workbook_workspace, 'pending-missing')
    missing, _ = runtime.jobs.create(source, file_hash(source), job_type='FOLDER', context=runtime._job_context('FOLDER'))
    source.unlink()
    assert runtime.start()
    assert runtime.jobs.get(missing['id'])['failure_code'] == 'SOURCE_MISSING'
    assert runtime.shutdown()


def test_startup_ignores_temporary_and_unrelated_xlsx_and_race_is_idempotent(qt_app, copied_reference, workbook_workspace):
    runtime, source = reconciliation_runtime(copied_reference, workbook_workspace, 'ignored')
    original = source.read_bytes()
    temporary = source.with_name('~$' + source.name)
    shutil.copy2(source, temporary)
    source.unlink()
    template = Path(runtime.workflow.configuration()['template_path'])
    shutil.copy2(template, source.with_name('unrelated.xlsx'))
    assert runtime.start()
    assert runtime.jobs.latest() == []
    # Simulate a watchdog delivery immediately after startup reconciliation.
    source.write_bytes(original)
    result = runtime._process_folder_attendance(source)
    duplicate = runtime._process_folder_attendance(source)
    assert result['automation_job']['id'] == duplicate['automation_job']['id']
    assert len(runtime.jobs.latest()) == 1
    assert runtime.shutdown()


def test_startup_reconciles_multiple_approved_files_in_name_order(qt_app, copied_reference, workbook_workspace):
    runtime, source = reconciliation_runtime(copied_reference, workbook_workspace, 'multiple')
    # Retain the proven attendance filename period convention while changing
    # the path identity, just as two separately saved approved inputs would.
    second = source.with_name('copy ' + source.name)
    shutil.copy2(source, second)
    assert runtime.start()
    jobs = runtime.jobs.latest()
    assert {Path(job['source_path']).name for job in jobs} == {source.name, second.name}
    assert all(job['state'] in {AutomationJobState.COMPLETED, AutomationJobState.REVIEW_REQUIRED} for job in jobs)
    assert [Path(job['source_path']).name for job in reversed(jobs)] == sorted(
        (source.name, second.name), key=str.casefold)
    assert runtime.shutdown()
