"""Application-level owner for tray-first monitoring and automation."""
from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import json
import logging
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QObject, Qt, QTimer, Signal, Slot

from app.domain import PayrollState
from app.excel.workbook_source import file_hash
from app.safety import development_target
from app.services.automation_job_service import AutomationJobError, AutomationJobService, AutomationJobState
from app.services.watcher import AttendanceFolderWatcher, AttendanceWatcher, WatcherHealth
from app.services.workflow_service import WorkflowService


class RuntimeState(StrEnum):
    DISABLED = 'DISABLED'
    WATCHING = 'WATCHING'
    PROCESSING = 'PROCESSING'
    REVIEW_REQUIRED = 'REVIEW_REQUIRED'
    ERROR = 'ERROR'


class AutomationRuntime(QObject):
    """Own watcher lifecycle independently from any visible window.

    Watchdog invokes the small callback methods below from its own thread.  Qt
    signals marshal all state changes and consumers back to this QObject's GUI
    thread, so neither the tray nor a later-created MainWindow is touched by a
    watcher thread.
    """
    state_changed = Signal(str)
    processing_started = Signal(str)
    processing_finished = Signal(object)
    review_required = Signal(object)
    runtime_error = Signal(str)
    notification = Signal(str, str)
    configuration_changed = Signal(object)
    shutdown_ready = Signal()

    _processing_requested = Signal(str)
    _watcher_result = Signal(object)
    _watcher_error = Signal(str)

    MANUAL_SETTING = 'manual_watch_configuration'
    # Five seconds is intentionally conservative for local desktop payroll.
    # Recovery is delayed without blocking the Qt event loop.
    HEALTH_CHECK_MS = 5_000
    RESTART_BACKOFF_MS = (2_000, 5_000, 15_000)

    def __init__(self, payroll_service, parent=None, *, folder_watcher_factory=AttendanceFolderWatcher,
                 file_watcher_factory=AttendanceWatcher, qa_mode=False, qa_root=None):
        super().__init__(parent)
        self.service = payroll_service
        self.repo = payroll_service.repo
        self.qa_mode, self.qa_root = bool(qa_mode), Path(qa_root).resolve() if qa_root else None
        self.workflow = WorkflowService(payroll_service, allowed_root=self.qa_root)
        self.jobs = AutomationJobService(self.repo)
        self.worker_instance_id = str(uuid4())
        self.folder_watcher_factory = folder_watcher_factory
        self.file_watcher_factory = file_watcher_factory
        self.watcher = None
        self._watcher_signature = None
        self._watcher_stop_requested = False
        self.state = RuntimeState.DISABLED
        self.current_folder = None
        self.current_file = None
        self.last_result = None
        self.last_job_summary = None
        self.recovery = None
        self.staged_write_recovery = []
        self._recovery_complete = False
        self._shutdown_requested = False
        self._shutdown_participants = []
        self._restart_attempt = 0
        self._restart_scheduled = False
        self._restart_generation = 0
        self._health_fault = None
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(self.HEALTH_CHECK_MS)
        self._health_timer.timeout.connect(self._supervise_watcher)
        self._processing_requested.connect(self._processing_started, Qt.QueuedConnection)
        self._watcher_result.connect(self._processing_finished, Qt.QueuedConnection)
        self._watcher_error.connect(self._runtime_error, Qt.QueuedConnection)

    @property
    def monitoring_enabled(self):
        if self.qa_mode:
            return False
        return bool(self.repo.setting('watch_enabled', False))

    def start(self):
        """Recover durable state, reconcile approved inputs, then watch them.

        Reconciliation precedes watchdog startup, avoiding a startup race.  A
        persistent idempotency key and an atomic PENDING claim remain the final
        protection if an event is nevertheless delivered around that boundary.
        """
        if self.qa_mode:
            self.repo.set_setting('watch_enabled', False)
            self._set_state(RuntimeState.DISABLED)
            return False
        if not self._recovery_complete:
            self.recovery = self.jobs.recover_interrupted()
            self.staged_write_recovery = self.jobs.staged_write_inspection()
            if self.staged_write_recovery:
                logging.getLogger('ntp').warning('Found %s staged Excel write operation(s) requiring review',
                                                 len(self.staged_write_recovery))
            self._recovery_complete = True
        self._start_health_supervisor()
        # PENDING work is deliberately recovered before fresh folder inputs.
        # It is synchronous/serial at boot, before the watcher exists.
        if self.monitoring_enabled:
            self._reconcile_startup()
        started = self.reconfigure()
        self._restore_persisted_job_state()
        return started

    def register_shutdown_participant(self, callback):
        if callback not in self._shutdown_participants:
            self._shutdown_participants.append(callback)

    def unregister_shutdown_participant(self, callback):
        if callback in self._shutdown_participants:
            self._shutdown_participants.remove(callback)

    def configure_manual_sources(self, attendance_path, payroll_path, year, month):
        """Persist the legacy single-file watcher configuration without owning it in UI."""
        if self.qa_mode:
            raise AutomationJobError('Monitoring sources are disabled in QA mode')
        attendance = development_target(Path(attendance_path))
        payroll = development_target(Path(payroll_path))
        value = {'attendance_path': str(attendance), 'payroll_path': str(payroll),
                 'year': int(year), 'month': int(month)}
        self.repo.set_setting(self.MANUAL_SETTING, value)
        self.configuration_changed.emit(value)
        if self.monitoring_enabled:
            self.reconfigure()

    def pause_monitoring(self):
        """Record the user's pause intent, but only report stopped when confirmed."""
        self.repo.set_setting('watch_enabled', False)
        self._cancel_restart()
        stopped, message = self._stop_watcher()
        if not stopped:
            self._runtime_error(message)
            return False
        self._set_state(RuntimeState.DISABLED)
        self._restore_persisted_job_state()
        self.configuration_changed.emit(self.configuration())
        return True

    def resume_monitoring(self):
        if self.qa_mode:
            self.repo.set_setting('watch_enabled', False)
            self._set_state(RuntimeState.DISABLED)
            self._runtime_error('Monitoring is disabled in QA mode')
            return False
        if self._shutdown_requested:
            self._runtime_error('Application shutdown is still waiting for attendance monitoring to stop')
            return False
        self.repo.set_setting('watch_enabled', True)
        self.configuration_changed.emit(self.configuration())
        return self.reconfigure()

    def reconfigure(self):
        if self.qa_mode:
            self._set_state(RuntimeState.DISABLED)
            return True
        return self._reconfigure()

    def _reconfigure(self, *, force_restart=False):
        """Apply the persisted monitoring preference without creating duplicates."""
        if self._shutdown_requested:
            stopped, message = self._stop_watcher()
            if not stopped:
                self._runtime_error(message)
                return False
            self._set_state(RuntimeState.DISABLED)
            return False
        if not self.monitoring_enabled:
            stopped, message = self._stop_watcher()
            if not stopped:
                self._runtime_error(message)
                return False
            self._set_state(RuntimeState.DISABLED)
            self._restore_persisted_job_state()
            return True
        try:
            signature = self._configured_signature()
            # A previous stop timed out or raised.  Do not even construct a
            # replacement until the watcher still owned by this runtime has
            # subsequently confirmed that it is gone.
            if self.watcher is not None and self._watcher_stop_requested:
                stopped, message = self._stop_watcher()
                if not stopped:
                    self._runtime_error(message)
                    return False
            if (self.watcher is not None and not self._watcher_stop_requested
                    and self._watcher_signature == signature and not force_restart):
                if self._watcher_health() != WatcherHealth.HEALTHY:
                    health = self._watcher_health()
                    self._report_health_fault(health, self._health_message(health))
                    self._schedule_recovery(health)
                    return False
                self._clear_health_fault()
                self._restore_persisted_job_state()
                return True
            # A.1 invariant: even construction of a replacement happens only
            # after the old owned watcher has confirmed it stopped.
            if self.watcher is not None:
                stopped, message = self._stop_watcher()
                if not stopped:
                    self._runtime_error(message)
                    return False
            signature, watcher, folder = self._build_watcher()
            self.watcher = watcher
            self._watcher_signature = signature
            self.current_folder = folder
            self._watcher_stop_requested = False
            try:
                watcher.start()
            except Exception:
                # A watcher may have started its worker before watchdog setup
                # fails. Keep ownership until that worker is confirmed stopped.
                stopped, stop_message = self._stop_watcher()
                if not stopped:
                    raise RuntimeError(f'Watcher start failed and its worker did not stop: {stop_message}')
                raise
            if self._watcher_health() != WatcherHealth.HEALTHY:
                health = self._watcher_health()
                stopped, message = self._stop_watcher()
                if not stopped:
                    raise RuntimeError(message)
                raise RuntimeError(f'Attendance monitoring did not become healthy: {health}')
            # A successful, verified replacement resolves a prior lifecycle
            # error (for example, a stop timeout that later completed).
            if self.state == RuntimeState.ERROR:
                self._set_state(RuntimeState.DISABLED)
            self._clear_health_fault()
            self._restore_persisted_job_state()
            return True
        except Exception as exc:
            self._report_health_fault('CONFIGURATION', str(exc))
            return False

    def _configured_signature(self):
        if self.workflow.configured():
            config = self.workflow.configuration()
            return ('folder', str(Path(config['attendance_folder']).resolve()), str(config['payroll_folder']),
                    str(config['template_path']))
        manual = self.repo.setting(self.MANUAL_SETTING)
        if not manual:
            return None
        return ('file', str(Path(manual['attendance_path']).resolve()), str(Path(manual['payroll_path']).resolve()),
                int(manual['year']), int(manual['month']))

    def _build_watcher(self):
        if self.workflow.configured():
            config = self.workflow.configuration()
            folder = Path(config['attendance_folder']).resolve()
            watcher = self.folder_watcher_factory(
                folder, self._process_folder_attendance,
                on_result=self._watcher_result.emit, notify=self._watcher_error.emit,
            )
            return ('folder', str(folder), str(config['payroll_folder']), str(config['template_path'])), watcher, folder
        manual = self.repo.setting(self.MANUAL_SETTING)
        if not manual:
            raise RuntimeError('ยังไม่ได้ตั้งค่าโฟลเดอร์หรือไฟล์สำหรับการเฝ้าดู')
        attendance = development_target(Path(manual['attendance_path']))
        payroll = development_target(Path(manual['payroll_path']))
        initial = None
        run = self.service.repo.run(int(manual['year']), int(manual['month']))
        if run and run['source_path'] == str(attendance) and run['payroll_path'] == str(payroll):
            initial = run['source_hash']
        watcher = self.file_watcher_factory(
            attendance,
            lambda path: self._process_manual_attendance(path, payroll, int(manual['year']), int(manual['month'])),
            initial_hash=initial, on_result=self._watcher_result.emit, notify=self._watcher_error.emit,
        )
        return ('file', str(attendance), str(payroll), int(manual['year']), int(manual['month'])), watcher, attendance.parent

    def _start_health_supervisor(self):
        if self.monitoring_enabled and not self._shutdown_requested and not self._health_timer.isActive():
            self._health_timer.start()

    def _cancel_restart(self):
        """Invalidate queued QTimer callbacks; QTimer.singleShot cannot be cancelled."""
        self._restart_generation += 1
        self._restart_scheduled = False

    def _watcher_health(self):
        watcher = self.watcher
        if watcher is None:
            return WatcherHealth.NOT_STARTED
        health = getattr(watcher, 'health', None)
        if callable(health):
            try:
                return WatcherHealth(health())
            except Exception:
                logging.getLogger('ntp').exception('Attendance watcher health check failed')
                return WatcherHealth.OBSERVER_DEAD
        # Compatibility with small test doubles from Phase A/B.  Production
        # watchers expose health() and never use this fallback.
        if getattr(watcher, 'stopping', False):
            return WatcherHealth.STOPPING
        return WatcherHealth.HEALTHY if getattr(watcher, 'started', False) else WatcherHealth.NOT_STARTED

    def _configured_watch_path_available(self):
        try:
            if self.workflow.configured():
                return Path(self.workflow.configuration()['attendance_folder']).is_dir()
            manual = self.repo.setting(self.MANUAL_SETTING)
            return bool(manual and Path(manual['attendance_path']).parent.is_dir())
        except Exception:
            return False

    def _health_message(self, health):
        if health == WatcherHealth.PATH_UNAVAILABLE:
            return 'ไม่พบโฟลเดอร์ที่กำลังเฝ้าดู หรือไม่สามารถเข้าถึงได้'
        if health == WatcherHealth.STOPPING:
            return 'Attendance monitoring is still stopping; no replacement watcher was started'
        if health == WatcherHealth.NOT_STARTED:
            return 'Attendance monitoring has not started'
        return 'Attendance monitoring observer is no longer running'

    def _report_health_fault(self, code, message):
        """Publish each unresolved operational fault only once."""
        fault = (str(code), str(message))
        self._set_state(RuntimeState.ERROR)
        if self._health_fault == fault:
            return
        self._health_fault = fault
        self.runtime_error.emit(message)
        self.notification.emit('การเฝ้าดูไฟล์บันทึกเวลาผิดพลาด', message)

    def _clear_health_fault(self):
        had_fault = self._health_fault is not None
        if self._health_fault is not None:
            logging.getLogger('ntp').info('Attendance watcher recovered: %s', self._health_fault[0])
            self.notification.emit('การเฝ้าดูไฟล์บันทึกเวลากลับมาทำงานแล้ว', '')
        self._health_fault = None
        self._restart_attempt = 0
        self._cancel_restart()
        if had_fault and self.state == RuntimeState.ERROR:
            self._set_state(RuntimeState.DISABLED)

    @Slot()
    def _supervise_watcher(self):
        """Cheap Qt-loop liveness supervision; never runs from a watchdog thread."""
        if self._shutdown_requested or not self.monitoring_enabled:
            return
        health = self._watcher_health()
        if health == WatcherHealth.HEALTHY:
            # A directory delete/recreate can leave watchdog's old OS watch
            # thread alive but detached from the newly created directory.
            # Keep the path fault latched until a safe replacement succeeds.
            if self._health_fault and self._health_fault[0] == WatcherHealth.PATH_UNAVAILABLE:
                self._restart_attempt = 0
                self._schedule_recovery(WatcherHealth.PATH_UNAVAILABLE)
                return
            self._clear_health_fault()
            self._restore_persisted_job_state()
            return
        # A path that reappears after bounded failures deliberately gets a new
        # bounded recovery window; an observer failure does not retry forever.
        if self._health_fault and self._health_fault[0] == WatcherHealth.PATH_UNAVAILABLE and self._configured_watch_path_available():
            self._restart_attempt = 0
        self._report_health_fault(health, self._health_message(health))
        self._schedule_recovery(health)

    def _schedule_recovery(self, health):
        if self._shutdown_requested or not self.monitoring_enabled or self._restart_scheduled:
            return
        if self._restart_attempt >= len(self.RESTART_BACKOFF_MS):
            return
        delay = self.RESTART_BACKOFF_MS[self._restart_attempt]
        self._restart_attempt += 1
        self._restart_scheduled = True
        generation = self._restart_generation
        QTimer.singleShot(delay, lambda: self._attempt_watcher_recovery(generation))

    def _attempt_watcher_recovery(self, generation=None):
        if generation is not None and generation != self._restart_generation:
            return False
        self._restart_scheduled = False
        if self._shutdown_requested or not self.monitoring_enabled:
            return False
        if not self._configured_watch_path_available():
            self._report_health_fault(WatcherHealth.PATH_UNAVAILABLE,
                                      self._health_message(WatcherHealth.PATH_UNAVAILABLE))
            self._schedule_recovery(WatcherHealth.PATH_UNAVAILABLE)
            return False
        if self._reconfigure(force_restart=True):
            self._reconcile_startup(include_pending=False)
            self._restore_persisted_job_state()
            return True
        self._schedule_recovery(self._watcher_health())
        return False

    def _source_is_settled_xlsx(self, source):
        """Non-blocking startup equivalent of watcher settling/integrity checks."""
        from io import BytesIO
        from zipfile import ZipFile
        from app.excel.workbook_source import WorkbookSnapshot
        source = Path(source)
        try:
            before = source.stat()
            saved = WorkbookSnapshot.read(source)
            after = source.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                return False
            with ZipFile(BytesIO(saved.content)) as package:
                return not package.testzip() and '[Content_Types].xml' in package.namelist()
        except Exception:
            return False

    def _work_for_job(self, job):
        if job['job_type'] == 'FOLDER':
            if not self.workflow.configured() or job['context'] != self._job_context('FOLDER'):
                raise AutomationJobError('Current workflow configuration differs from the pending job')
            source = Path(job['source_path'])
            if not self.workflow.is_approved_attendance_source(source):
                raise AutomationJobError('Pending source is not an approved attendance workbook')
            return source, lambda: self.workflow.process_attendance(source)
        if job['job_type'] == 'MANUAL':
            context = job['context']
            current = self.repo.setting(self.MANUAL_SETTING)
            expected = {**context, 'attendance_path': context.get('attendance_path', job['source_path'])}
            if not current or any(current.get(key) != expected.get(key) for key in ('attendance_path', 'payroll_path', 'year', 'month')):
                raise AutomationJobError('Current manual configuration differs from the pending job')
            source = Path(job['source_path'])
            payroll = development_target(Path(context['payroll_path']))
            return source, lambda: self.service.prepare(source, payroll, year=context['year'], month=context['month'])
        raise AutomationJobError(f"Unsupported automation job type: {job['job_type']}")

    def _reconcile_pending_job(self, job):
        source = Path(job['source_path'])
        if not source.is_file():
            self.jobs.fail(job['id'], 'SOURCE_MISSING', 'Pending attendance source is no longer available at startup')
            return None
        if not self._source_is_settled_xlsx(source):
            self.jobs.fail(job['id'], 'SOURCE_INVALID', 'Pending attendance source was not a settled valid XLSX at startup')
            return None
        current_hash = file_hash(source)
        if current_hash != job['source_hash']:
            self.jobs.fail(job['id'], 'SOURCE_CHANGED_OFFLINE',
                           'Pending source changed while the application was stopped; old bytes were not processed')
            replacement, _ = self.jobs.create(source, current_hash, job_type=job['job_type'], context=job['context'],
                                              year=job['period_year'], month=job['period_month'])
            return replacement
        try:
            source, work = self._work_for_job(job)
        except Exception as exc:
            self.jobs.fail(job['id'], 'CONFIGURATION_CHANGED', str(exc))
            return None
        claimed, success = self.jobs.claim_pending(job['id'], self.worker_instance_id)
        if not success:
            return None
        return self._run_reconciliation_job(claimed, source, work)

    def _run_reconciliation_job(self, job, source, work):
        self._processing_started(str(source))
        try:
            result = self._execute_claimed_job(job, source, work, announce=False)
        except Exception as exc:
            self._runtime_error(str(exc))
            return None
        self._processing_finished(result)
        return result

    def _approved_startup_sources(self):
        if self.workflow.configured():
            folder = Path(self.workflow.configuration()['attendance_folder'])
            if not folder.is_dir():
                return []
            return [source for source in sorted(folder.glob('*.xlsx'), key=lambda p: p.name.casefold())
                    if not source.name.startswith('~$') and self._source_is_settled_xlsx(source)
                    and self.workflow.is_approved_attendance_source(source)]
        manual = self.repo.setting(self.MANUAL_SETTING)
        if not manual:
            return []
        source = Path(manual['attendance_path'])
        return [source] if source.is_file() and self._source_is_settled_xlsx(source) else []

    def _reconcile_startup(self, *, include_pending=True):
        """Serially reconcile only persisted jobs and currently approved sources."""
        if self._shutdown_requested or not self.monitoring_enabled:
            return []
        results = []
        if include_pending:
            for job in self.jobs.by_state(AutomationJobState.PENDING):
                result = self._reconcile_pending_job(job)
                if result:
                    results.append(result)
        for source in self._approved_startup_sources():
            try:
                self._processing_started(str(source))
                if self.workflow.configured():
                    result = self._process_folder_attendance(source, announce=False)
                else:
                    manual = self.repo.setting(self.MANUAL_SETTING)
                    result = self._process_manual_attendance(source, development_target(Path(manual['payroll_path'])),
                                                             int(manual['year']), int(manual['month']), announce=False)
                # New/reused files still receive the same state/result path as a
                # watchdog event, but occur serially before watcher startup.
                self._processing_finished(result)
                results.append(result)
            except AutomationJobError as exc:
                # Existing FAILED jobs are deliberately not retried implicitly.
                logging.getLogger('ntp').info('Startup reconciliation skipped %s: %s', source.name, exc)
            except Exception as exc:
                self._runtime_error(str(exc))
        return results

    def _job_context(self, job_type, **extra):
        value = {'workflow': self.workflow.configuration() if self.workflow.configured() else None, **extra}
        # The source path/hash and this canonical context are the durable
        # identity of an automation attempt; timestamps never participate.
        value['identity'] = sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode('utf-8')).hexdigest()
        return value

    def _existing_job_result(self, job):
        if job['period_year'] is None or job['period_month'] is None:
            raise AutomationJobError(f"Automation job {job['id']} has no persisted payroll period")
        run, draft = self.service.current(job['period_year'], job['period_month'])
        if not run or not draft:
            raise AutomationJobError(f"Automation job {job['id']} has no persisted draft evidence")
        return {'run': run, 'draft': draft, 'unchanged': True,
                'protected': run['state'] in {'CONFIRMED', 'WRITTEN', 'LOCKED'}, 'automation_job': job}

    def _execute_claimed_job(self, job, path, work, *, announce=True):
        if announce:
            self._processing_requested.emit(str(path))
        try:
            result = work()
            draft, run = result['draft'], result['run']
            if draft.source_hash != job['source_hash']:
                raise AutomationJobError('Attendance source changed while this automation job was processing')
            self.jobs.set_period_and_run(job['id'], draft.year, draft.month, run['id'])
            review = bool(result.get('difference')) or draft.state != PayrollState.READY
            result['automation_job'] = self.jobs.finish(job['id'], payroll_run_id=run['id'], review_required=review)
            logging.getLogger('ntp').info('automation job=%s period=%s-%02d state=%s source=%s', job['id'],
                                          draft.year, draft.month, result['automation_job']['state'], Path(path).name)
            return result
        except Exception as exc:
            self.jobs.fail(job['id'], type(exc).__name__, str(exc))
            logging.getLogger('ntp').exception('automation job=%s failed source=%s', job['id'], Path(path).name)
            raise

    def _enqueue_and_process(self, path, *, job_type, context, work, year=None, month=None, announce=True):
        source = Path(path)
        source_hash = file_hash(source)
        job, created = self.jobs.create(source, source_hash, job_type=job_type, context=context, year=year, month=month)
        self.last_job_summary = job
        if not created:
            if job['state'] in {AutomationJobState.COMPLETED, AutomationJobState.REVIEW_REQUIRED}:
                return self._existing_job_result(job)
            if job['state'] == AutomationJobState.FAILED:
                raise AutomationJobError(f"Automation job {job['id']} previously failed; use retry_job")
        job, claimed = self.jobs.claim_pending(job['id'], self.worker_instance_id)
        if not claimed:
            raise AutomationJobError(f"Automation job {job['id']} is already being processed")
        return self._execute_claimed_job(job, source, work, announce=announce)

    def _process_folder_attendance(self, path, *, announce=True):
        return self._enqueue_and_process(path, job_type='FOLDER', context=self._job_context('FOLDER'),
                                         work=lambda: self.workflow.process_attendance(path), announce=announce)

    def _process_manual_attendance(self, path, payroll, year, month, *, announce=True):
        context = self._job_context('MANUAL', attendance_path=str(Path(path).resolve()), payroll_path=str(payroll), year=year, month=month)
        return self._enqueue_and_process(path, job_type='MANUAL', context=context, year=year, month=month,
                                         work=lambda: self.service.prepare(path, payroll, year=year, month=month), announce=announce)

    def retry_job(self, job_id):
        """Retry exactly the failed source, or persist a separate job for changed bytes."""
        if self.qa_mode:
            raise AutomationJobError('Retry is disabled in QA mode')
        persisted = self.jobs.get(job_id)
        if not persisted or not self._retry_source_within_boundary(persisted):
            raise AutomationJobError('Failed job source is outside the currently approved safety boundary')
        job, replacement, _ = self.jobs.retry_source(job_id)
        if replacement:
            self.last_job_summary = replacement
            return {'retried': False, 'changed_source_job': replacement}
        if job['job_type'] == 'FOLDER':
            if job['context'] != self._job_context('FOLDER'):
                self.jobs.fail(job_id, 'CONFIGURATION_CHANGED', 'Current workflow configuration differs from the failed job')
                raise AutomationJobError('Current workflow configuration differs from the failed job')
            work = lambda: self.workflow.process_attendance(job['source_path'])
        elif job['job_type'] == 'MANUAL':
            context = job['context']
            expected = {**context, 'attendance_path': context.get('attendance_path', job['source_path'])}
            current = self.repo.setting(self.MANUAL_SETTING)
            if not current or any(current.get(key) != expected.get(key)
                                  for key in ('attendance_path', 'payroll_path', 'year', 'month')):
                self.jobs.fail(job_id, 'CONFIGURATION_CHANGED',
                               'Current manual configuration differs from the failed job')
                raise AutomationJobError('Current manual configuration differs from the failed job')
            payroll = development_target(Path(context['payroll_path']))
            work = lambda: self.service.prepare(job['source_path'], payroll, year=context['year'], month=context['month'])
        else:
            raise AutomationJobError(f"Unsupported automation job type: {job['job_type']}")
        claimed, success = self.jobs.claim_retry(job_id, self.worker_instance_id)
        if not success:
            raise AutomationJobError(f'Automation job {job_id} could not be claimed for retry')
        return self._execute_claimed_job(claimed, Path(claimed['source_path']), work)

    def retry_eligibility(self, job_id):
        """Read-only UI preflight; retry_job still validates and claims atomically."""
        if self.qa_mode:
            return False, 'Retry is disabled in QA mode'
        job = self.jobs.get(job_id)
        if not job or job['state'] != AutomationJobState.FAILED:
            return False, 'เลือกรายการงานที่ล้มเหลวที่ยังมีอยู่ก่อนลองใหม่'
        if self._shutdown_requested:
            return False, 'ไม่สามารถลองงานใหม่ระหว่างที่โปรแกรมกำลังปิด'
        if self.state == RuntimeState.PROCESSING:
            return False, 'มีงานอื่นกำลังประมวลผลอยู่ กรุณารอให้เสร็จก่อน'
        if not self._retry_source_within_boundary(job):
            return False, 'ไฟล์ต้นทางอยู่นอกขอบเขตที่อนุญาต หรือไม่พร้อมใช้งาน'
        if job['job_type'] == 'FOLDER':
            if not self.workflow.configured() or job['context'] != self._job_context('FOLDER'):
                return False, 'การตั้งค่าโฟลเดอร์ปัจจุบันไม่ตรงกับงานเดิม'
        elif job['job_type'] == 'MANUAL':
            current = self.repo.setting(self.MANUAL_SETTING)
            context = job['context']
            expected = {**context, 'attendance_path': context.get('attendance_path', job['source_path'])}
            if not current or any(current.get(key) != expected.get(key)
                                  for key in ('attendance_path', 'payroll_path', 'year', 'month')):
                return False, 'การตั้งค่าไฟล์ปัจจุบันไม่ตรงกับงานเดิม'
        else:
            return False, 'ประเภทงานนี้ไม่รองรับการลองใหม่'
        return True, ''

    def _retry_source_within_boundary(self, job):
        """Cheap, non-mutating path boundary check before hashing a retry source."""
        source = Path(job['source_path'])
        if not source.is_file():
            return False
        if job['job_type'] == 'FOLDER':
            if not self.workflow.configured():
                return False
            try:
                folder = Path(self.workflow.configuration()['attendance_folder']).resolve()
                resolved = source.resolve()
            except Exception:
                return False
            return (resolved.parent == folder and resolved.suffix.lower() == '.xlsx'
                    and not resolved.name.startswith('~$'))
        if job['job_type'] == 'MANUAL':
            context = job['context']
            try:
                attendance = context.get('attendance_path', job['source_path'])
                return source.resolve() == development_target(Path(attendance))
            except Exception:
                return False
        return False

    def review_resolved(self, run):
        """Synchronize durable review jobs only after persisted payroll evidence is ready."""
        resolved = self.jobs.resolve_reviews_for_run(run)
        if resolved:
            self._restore_persisted_job_state()
        return resolved

    def _restore_persisted_job_state(self):
        recent = self.jobs.latest(1)
        self.last_job_summary = recent[0] if recent else None
        if self.state in {RuntimeState.ERROR, RuntimeState.PROCESSING}:
            return
        if self.jobs.by_state(AutomationJobState.REVIEW_REQUIRED):
            self._set_state(RuntimeState.REVIEW_REQUIRED)
        else:
            self._set_state(RuntimeState.WATCHING if self._watcher_health() == WatcherHealth.HEALTHY
                            else RuntimeState.DISABLED)

    @Slot(str)
    def _processing_started(self, path):
        # A pause/shutdown stop may have been requested after this callback was
        # queued by the watcher thread.  Keep the lifecycle ERROR visible
        # rather than reviving PROCESSING for a watcher that is being drained.
        if self._watcher_stop_requested:
            return
        self.current_file = Path(path)
        self._set_state(RuntimeState.PROCESSING)
        self.processing_started.emit(path)

    @Slot(object)
    def _processing_finished(self, result):
        self.last_result = result
        if result.get('automation_job'):
            self.last_job_summary = result['automation_job']
        draft = result['draft']
        self.current_file = Path(draft.source_path)
        self.processing_finished.emit(result)
        if self._watcher_stop_requested:
            return
        review = bool(result.get('difference')) or draft.state != PayrollState.READY
        if review:
            self._set_state(RuntimeState.REVIEW_REQUIRED)
            self.review_required.emit(result)
            if not result.get('unchanged'):
                self.notification.emit('ต้องตรวจสอบเงินเดือน', 'พบรายการที่ต้องยืนยันก่อนบันทึกไฟล์เงินเดือน')
        else:
            self._restore_persisted_job_state()
            if not result.get('unchanged'):
                self.notification.emit('อ่านบันทึกเวลาที่บันทึกแล้ว', 'ฉบับร่างพร้อมตรวจสอบ')

    @Slot(str)
    def _runtime_error(self, message):
        self._set_state(RuntimeState.ERROR)
        self.runtime_error.emit(message)
        self.notification.emit('อ่านบันทึกเวลาไม่สำเร็จ', message)

    def _set_state(self, state):
        if self.state != state:
            self.state = state
            self.state_changed.emit(state)

    def configuration(self):
        return self.workflow.configuration() if self.workflow.configured() else self.repo.setting(self.MANUAL_SETTING)

    def _stop_watcher(self):
        """Stop the owned watcher without discarding it before confirmation.

        A false/exceptional stop leaves the watcher and its signature attached
        to this runtime.  Callers must treat that as an ERROR and must not
        replace it, otherwise two filesystem workers can overlap.
        """
        watcher = self.watcher
        if watcher is None:
            self._watcher_signature = None
            self._watcher_stop_requested = False
            return True, None
        self._watcher_stop_requested = True
        try:
            stopped = watcher.stop()
        except Exception as exc:
            return False, f'Unable to stop attendance monitoring: {exc}'
        if not stopped:
            return False, 'Attendance monitoring is still stopping; no replacement watcher was started'
        self.watcher = None
        self._watcher_signature = None
        self.current_folder = None
        self._watcher_stop_requested = False
        return True, None

    def shutdown(self):
        """The sole application-level shutdown coordination path."""
        self._shutdown_requested = True
        self._health_timer.stop()
        self._cancel_restart()
        stopped, message = self._stop_watcher()
        if not stopped:
            self._runtime_error(message)
            return False
        self._set_state(RuntimeState.DISABLED)
        for participant in tuple(self._shutdown_participants):
            if not participant():
                return False
        return True

    def notify_shutdown_ready(self):
        if self._shutdown_requested:
            self.shutdown_ready.emit()
