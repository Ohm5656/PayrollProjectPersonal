"""Durable, SQLite-backed lifecycle for background attendance automation."""
from __future__ import annotations

from enum import StrEnum
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from app.domain import PayrollState, utc_now
from app.excel.workbook_source import file_hash


class AutomationJobState(StrEnum):
    PENDING = 'PENDING'
    PROCESSING = 'PROCESSING'
    REVIEW_REQUIRED = 'REVIEW_REQUIRED'
    COMPLETED = 'COMPLETED'
    FAILED = 'FAILED'


class AutomationJobError(RuntimeError):
    pass


def _context(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class AutomationJobService:
    """Small repository-style service; payroll evidence remains in existing tables."""
    def __init__(self, repository):
        self.repo = repository

    @staticmethod
    def idempotency_key(source_path, source_hash, job_type, context):
        identity = {'path': str(Path(source_path).resolve()), 'hash': source_hash,
                    'type': job_type, 'context': context}
        return sha256(_context(identity).encode('utf-8')).hexdigest()

    @staticmethod
    def _decode(row):
        if not row:
            return None
        item = dict(row)
        item['context'] = json.loads(item['context'])
        item['review_required'] = bool(item['review_required'])
        return item

    def get(self, job_id):
        rows = self.repo.db.query('SELECT * FROM automation_jobs WHERE id=?', (job_id,))
        return self._decode(rows[0]) if rows else None

    def latest(self, limit=50):
        return [self._decode(row) for row in self.repo.db.query(
            'SELECT * FROM automation_jobs ORDER BY updated_at DESC,id DESC LIMIT ?', (limit,))]

    def by_state(self, *states):
        if not states:
            return []
        marks = ','.join('?' for _ in states)
        return [self._decode(row) for row in self.repo.db.query(
            f'SELECT * FROM automation_jobs WHERE state IN ({marks}) ORDER BY updated_at,id', tuple(map(str, states)))]

    def create(self, source_path, source_hash, *, job_type, context, year=None, month=None):
        source = str(Path(source_path).resolve())
        encoded_context = _context(context)
        key = self.idempotency_key(source, source_hash, job_type, context)
        now, job_id = utc_now(), str(uuid4())
        with self.repo.db.transaction() as con:
            existing = con.execute('SELECT * FROM automation_jobs WHERE idempotency_key=?', (key,)).fetchone()
            if existing:
                return self._decode(existing), False
            con.execute('INSERT INTO automation_jobs('
                        'id,source_path,source_hash,period_year,period_month,job_type,context,state,created_at,'
                        'attempt_count,review_required,idempotency_key,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                        (job_id, source, source_hash, year, month, job_type, encoded_context,
                         AutomationJobState.PENDING, now, 0, 0, key, now))
            row = con.execute('SELECT * FROM automation_jobs WHERE id=?', (job_id,)).fetchone()
        return self._decode(row), True

    def claim_pending(self, job_id, worker_instance_id):
        now = utc_now()
        with self.repo.db.transaction() as con:
            changed = con.execute('UPDATE automation_jobs SET state=?,started_at=?,finished_at=NULL,attempt_count=attempt_count+1,'
                                  'worker_instance_id=?,claimed_at=?,updated_at=? WHERE id=? AND state=?',
                                  (AutomationJobState.PROCESSING, now, worker_instance_id, now, now, job_id,
                                   AutomationJobState.PENDING)).rowcount
            row = con.execute('SELECT * FROM automation_jobs WHERE id=?', (job_id,)).fetchone()
        return self._decode(row), bool(changed)

    def claim_retry(self, job_id, worker_instance_id):
        now = utc_now()
        with self.repo.db.transaction() as con:
            changed = con.execute('UPDATE automation_jobs SET state=?,started_at=?,finished_at=NULL,attempt_count=attempt_count+1,'
                                  'failure_code=NULL,failure_message=NULL,worker_instance_id=?,claimed_at=?,updated_at=? '
                                  'WHERE id=? AND state=?',
                                  (AutomationJobState.PROCESSING, now, worker_instance_id, now, now, job_id,
                                   AutomationJobState.FAILED)).rowcount
            row = con.execute('SELECT * FROM automation_jobs WHERE id=?', (job_id,)).fetchone()
        return self._decode(row), bool(changed)

    def set_period_and_run(self, job_id, year, month, run_id=None):
        with self.repo.db.transaction() as con:
            con.execute('UPDATE automation_jobs SET period_year=?,period_month=?,payroll_run_id=COALESCE(?,payroll_run_id),'
                        'updated_at=? WHERE id=?', (year, month, run_id, utc_now(), job_id))

    def finish(self, job_id, *, payroll_run_id, review_required):
        state = AutomationJobState.REVIEW_REQUIRED if review_required else AutomationJobState.COMPLETED
        now = utc_now()
        with self.repo.db.transaction() as con:
            changed = con.execute('UPDATE automation_jobs SET state=?,finished_at=?,payroll_run_id=?,review_required=?,'
                                  'worker_instance_id=NULL,updated_at=? WHERE id=? AND state=?',
                                  (state, now, payroll_run_id, int(review_required), now, job_id,
                                   AutomationJobState.PROCESSING)).rowcount
            row = con.execute('SELECT * FROM automation_jobs WHERE id=?', (job_id,)).fetchone()
        if not changed:
            raise AutomationJobError(f'Job {job_id} was not processing when completion was recorded')
        return self._decode(row)

    def fail(self, job_id, code, message):
        safe_message = str(message)[:1000]
        now = utc_now()
        with self.repo.db.transaction() as con:
            row = con.execute('SELECT * FROM automation_jobs WHERE id=?', (job_id,)).fetchone()
            if not row:
                return None
            con.execute('UPDATE automation_jobs SET state=?,finished_at=?,failure_code=?,failure_message=?,'
                        'worker_instance_id=NULL,updated_at=? WHERE id=?',
                        (AutomationJobState.FAILED, now, code, safe_message, now, job_id))
            con.execute('INSERT INTO automation_job_failures(job_id,attempt_count,code,message,created_at) VALUES (?,?,?,?,?)',
                        (job_id, row['attempt_count'], code, safe_message, now))
            result = con.execute('SELECT * FROM automation_jobs WHERE id=?', (job_id,)).fetchone()
        return self._decode(result)

    def recover_interrupted(self):
        """Conservatively mark prior-process claims failed; never infer success."""
        interrupted = self.by_state(AutomationJobState.PROCESSING)
        for job in interrupted:
            self.fail(job['id'], 'INTERRUPTED', 'Automation stopped before this job finished; retry is required')
        return {'interrupted': [job['id'] for job in interrupted],
                'pending': self.by_state(AutomationJobState.PENDING),
                'review': self.by_state(AutomationJobState.REVIEW_REQUIRED),
                'failed': self.by_state(AutomationJobState.FAILED)}

    def resolve_reviews_for_run(self, run):
        if not run or run['state'] != PayrollState.READY:
            return []
        if self.repo.pending_changes(run['id']):
            return []
        now = utc_now()
        with self.repo.db.transaction() as con:
            rows = con.execute('SELECT id FROM automation_jobs WHERE payroll_run_id=? AND state=?',
                               (run['id'], AutomationJobState.REVIEW_REQUIRED)).fetchall()
            con.execute('UPDATE automation_jobs SET state=?,review_required=0,finished_at=?,updated_at=? '
                        'WHERE payroll_run_id=? AND state=?',
                        (AutomationJobState.COMPLETED, now, now, run['id'], AutomationJobState.REVIEW_REQUIRED))
        return [row['id'] for row in rows]

    def retry_source(self, job_id):
        """Return a retryable job or create a distinct pending job for changed content."""
        job = self.get(job_id)
        if not job or job['state'] != AutomationJobState.FAILED:
            raise AutomationJobError('Only failed automation jobs can be retried')
        def rejected(code, message):
            with self.repo.db.transaction() as con:
                con.execute('UPDATE automation_jobs SET attempt_count=attempt_count+1,updated_at=? WHERE id=?',
                            (utc_now(), job_id))
            self.fail(job_id, code, message)
        source = Path(job['source_path'])
        if not source.is_file():
            rejected('SOURCE_MISSING', 'The original attendance file is no longer available')
            raise AutomationJobError('The original attendance file is no longer available')
        current_hash = file_hash(source)
        if current_hash != job['source_hash']:
            replacement, created = self.create(source, current_hash, job_type=job['job_type'], context=job['context'],
                                               year=job['period_year'], month=job['period_month'])
            rejected('SOURCE_CHANGED', 'Source content changed; a new pending job was created for the new file')
            return None, replacement, created
        return job, None, False

    def staged_write_inspection(self):
        rows = self.repo.db.query("SELECT * FROM write_operations WHERE status='STAGED' ORDER BY created_at")
        inspection = []
        for row in rows:
            target, backup = Path(row['target']), Path(row['backup_path'])
            backup_ok = backup.is_file() and file_hash(backup) == row['backup_hash']
            inspection.append({'operation_id': row['id'], 'target_exists': target.is_file(),
                               'backup_valid': backup_ok, 'classification': 'STAGED_REQUIRES_REVIEW'})
        return inspection
