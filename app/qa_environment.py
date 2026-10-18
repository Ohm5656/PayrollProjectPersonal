"""Explicit, synthetic-only environment for manual desktop QA.

This module deliberately has no production fallback.  ``--qa-ui`` always
uses the fixed session below, which is validated as a descendant of the
development test workspace before anything persistent is created.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from app.db.repositories import Repository
from app.domain import PayrollDraft, PayrollState, PayrollValue, EmployeeDraft, ReviewIssue, ValueCategory, encode, utc_now
from app.safety import TEST_ROOT, SafetyError, development_target
from app.services.automation_job_service import AutomationJobService
from app.services.windows_startup import StartupResult, StartupState, StartupStatus


QA_SESSIONS_ROOT = TEST_ROOT / 'qa_sessions'
QA_SESSION_NAME = 'manual_ui'
QA_FIXTURE_VERSION = 1


def _inside(path: Path, root: Path) -> bool:
    path, root = path.resolve(), root.resolve()
    return path == root or root in path.parents


@dataclass(frozen=True)
class QAEnvironment:
    root: Path

    @classmethod
    def create(cls, *, sessions_root: Path | None = None):
        sessions = Path(sessions_root or QA_SESSIONS_ROOT).resolve()
        if not _inside(sessions, TEST_ROOT):
            raise SafetyError('QA sessions must remain inside test_workspace')
        root = sessions / QA_SESSION_NAME
        # All leaf paths are sent through the existing development boundary.
        development_target(root / 'state' / 'placeholder')
        for folder in ('data', 'logs', 'ipc', 'fixtures', 'input', 'output'):
            (root / folder).mkdir(parents=True, exist_ok=True)
        return cls(root)

    @property
    def database_path(self): return development_target(self.root / 'data' / 'ntp_payroll_qa.db')
    @property
    def log_path(self): return development_target(self.root / 'logs' / 'app.log')
    @property
    def instance_directory(self): return self.root / 'ipc'
    @property
    def fixtures_directory(self): return self.root / 'fixtures'

    def contains(self, path: Path) -> bool:
        return _inside(Path(path), self.root)

    def require_path(self, path: Path) -> Path:
        value = development_target(Path(path))
        if not self.contains(value):
            raise SafetyError('QA mode accepts files only inside its QA session')
        return value


class QAStartupService:
    """Inert replacement for Task Scheduler; it never reaches Windows APIs."""
    message = 'โหมดทดสอบ: ปิดการตั้งค่าเริ่มพร้อม Windows'

    def validate(self):
        return StartupStatus(StartupState.UNAVAILABLE, self.message)

    def _blocked(self):
        return StartupResult(False, self.validate(), False)

    install = repair = remove = _blocked


def _value(field, amount):
    return PayrollValue(field, ValueCategory.AUTO_CALCULATED, Decimal(str(amount)), None,
                        Decimal(str(amount)), None, Decimal(str(amount)), 'synthetic QA value', 'QA fixture')


def _employee(key, employee_id, name, *, base, allowance, review=False):
    issue = (ReviewIssue(f'QA-{key}-REVIEW', 'QA_REVIEW', employee_id, 'QA', None, None,
                         'Synthetic QA review item', critical=False),) if review else ()
    values = {
        'base': _value('base', base), 'allowance': _value('allowance', allowance),
        'income': _value('income', Decimal(str(base)) + Decimal(str(allowance))),
        'net': _value('net', Decimal(str(base)) + Decimal(str(allowance))),
    }
    return EmployeeDraft(key, employee_id, name, 'QA', values, issue)


def _persist_draft(repo, draft):
    run_id = str(uuid4())
    with repo.db.transaction() as con:
        con.execute('INSERT INTO payroll_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL)', (
            run_id, draft.year, draft.month, draft.state.value, draft.source_path, draft.source_hash,
            draft.payroll_path, draft.payroll_hash, 1, encode(draft.evidence()), utc_now(),
        ))
        for employee in draft.employees:
            payroll_id = str(uuid4())
            con.execute('INSERT INTO monthly_payroll VALUES (?,?,?,?,?,?,?,?,NULL)', (
                payroll_id, run_id, employee.employee_id, employee.key, draft.year, draft.month,
                'READY', utc_now(),
            ))
            for field, value in employee.values.items():
                con.execute('INSERT INTO monthly_payroll_items VALUES (?,?,?,?,?,?,?,?,?,?,?)', (
                    payroll_id, field, str(value.final_value), value.category.value, value.source_reference,
                    str(value.source_value), None, str(value.draft_value), None, 0, value.reason,
                ))
            for issue in employee.issues:
                con.execute('INSERT INTO review_issues VALUES (?,?,?,?,?,?)', (
                    run_id, issue.key, issue.employee_id, issue.kind, int(issue.critical), encode(issue.__dict__),
                ))
        Repository.audit(con, 'QA_SYNTHETIC_PERIOD_CREATED', year=draft.year, month=draft.month,
                         new={'employees': len(draft.employees), 'synthetic': True}, source='qa-fixture', actor='qa-fixture')
    return run_id


def seed_synthetic_fixture(repo: Repository, environment: QAEnvironment):
    """Populate only a new QA database; repeated launches retain the same fixture."""
    if repo.setting('qa_fixture_version') == QA_FIXTURE_VERSION:
        return
    if repo.employees() or repo.db.query('SELECT id FROM payroll_runs LIMIT 1'):
        raise SafetyError('QA fixture database is not empty; refusing to mix data')
    employee_ids = {name: repo.create_employee(name, actor='qa-fixture') for name in (
        'Avery Sample', 'Blair Example', 'Casey Demo',
    )}
    fixture = environment.fixtures_directory
    # Marker files are intentionally not workbooks: QA presentation never reads
    # or copies reference Excel sources.
    for name in ('september-attendance.synthetic', 'september-payroll.synthetic',
                 'october-attendance.synthetic', 'october-payroll.synthetic'):
        target = environment.require_path(fixture / name)
        target.write_text('synthetic QA fixture only\n', encoding='utf-8')
    september = PayrollDraft(2026, 9, str(fixture / 'september-attendance.synthetic'), 'qa-sept-attendance',
        str(fixture / 'september-payroll.synthetic'), 'qa-sept-payroll', (
            _employee('qa-avery-sep', employee_ids['Avery Sample'], 'Avery Sample', base=22000, allowance=1200, review=True),
            _employee('qa-blair-sep', employee_ids['Blair Example'], 'Blair Example', base=18500, allowance=700),
        ))
    october = PayrollDraft(2026, 10, str(fixture / 'october-attendance.synthetic'), 'qa-oct-attendance',
        str(fixture / 'october-payroll.synthetic'), 'qa-oct-payroll', (
            _employee('qa-avery-oct', employee_ids['Avery Sample'], 'Avery Sample', base=22000, allowance=1900),
            _employee('qa-casey-oct', employee_ids['Casey Demo'], 'Casey Demo', base=20100, allowance=500),
        ))
    september_run, october_run = _persist_draft(repo, september), _persist_draft(repo, october)
    jobs = AutomationJobService(repo)
    completed, _ = jobs.create(fixture / 'september-attendance.synthetic', 'qa-job-completed',
                               job_type='QA_SYNTHETIC', context={'qa': True}, year=2026, month=9)
    jobs.claim_pending(completed['id'], 'qa-fixture')
    jobs.finish(completed['id'], payroll_run_id=september_run, review_required=False)
    failed, _ = jobs.create(fixture / 'october-attendance.synthetic', 'qa-job-failed',
                            job_type='QA_SYNTHETIC', context={'qa': True}, year=2026, month=10)
    jobs.fail(failed['id'], 'QA_SYNTHETIC_FAILURE', 'Synthetic failed job for Problems page')
    repo.set_setting('watch_enabled', False)
    repo.set_setting('qa_fixture_version', QA_FIXTURE_VERSION)
    repo.set_setting('qa_mode', True)
