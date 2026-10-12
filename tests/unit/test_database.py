from pathlib import Path
import sqlite3

import pytest

from app.db.database import Database
from app.db.repositories import Repository
from app.domain import ReusePolicy
from app.safety import SafetyError
from app.services.history_service import import_history


@pytest.fixture
def repository(workbook_workspace):
    return Repository(Database(workbook_workspace / 'payroll.db'))


def test_all_required_entities_and_repeat_migrations(repository):
    tables = {r['name'] for r in repository.db.query("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {'employees', 'employee_aliases', 'payroll_profiles', 'company_calendar', 'attendance_events',
            'monthly_payroll', 'monthly_payroll_items', 'remembered_values', 'audit_log', 'processed_files'} <= tables
    repository.db.migrate()
    assert repository.db.query('SELECT COUNT(*) AS n FROM schema_migrations')[0]['n'] == 1


def test_stable_identity_and_alias_survive_restart(repository):
    eid = repository.create_employee('นายภาณุวัฒน์ มูลที')
    assert eid != 'ภาณุวัฒน์ มูลที' and len(eid) == 36
    assert repository.resolve('ภานุวัฒน์') is None
    repository.confirm_alias(eid, 'ภานุวัฒน์', 'attendance_full', actor='accounting', reason='Name verified by user')
    restarted = Repository(Database(repository.db.path))
    assert restarted.resolve('ภานุวัฒน์') == eid
    assert restarted.create_employee('ภาณุวัฒน์  มูลที') == eid


def test_alias_conflict_does_not_merge_people(repository):
    first = repository.create_employee('บรรจง มูลที')
    second = repository.create_employee('อดิศักดิ์ สาคำตา')
    repository.confirm_alias(first, 'บรรจง', 'attendance_full', actor='user', reason='checked')
    with pytest.raises(ValueError, match='conflicts'):
        repository.confirm_alias(second, 'บรรจง', 'attendance_full', actor='user', reason='unsafe merge')
    assert len(repository.employees()) == 2
    assert repository.resolve('บรรจง') == first


def test_decisions_are_one_source_only_unless_rule_explicitly_saved(repository):
    eid = repository.create_employee('test employee')
    repository.decide('hash1', 'leave-key', {'leave_type': 'SICK_LEAVE', 'bonus_effect': 'KEEP'}, reason='one occurrence')
    assert repository.decisions('hash1')['leave-key']['bonus_effect'] == 'KEEP'
    assert not repository.decisions('hash2')
    assert repository.rule('LEAVE', 'ลา', eid) is None
    repository.remember_rule('LEAVE', 'ลา', {'leave_type': 'SICK_LEAVE', 'bonus_effect': 'KEEP'}, scope=eid)
    restarted = Repository(Database(repository.db.path))
    assert restarted.rule('LEAVE', 'ลา', eid)['bonus_effect'] == 'KEEP'
    other = repository.create_employee('other employee')
    assert restarted.rule('LEAVE', 'ลา', other) is None


def test_calendar_employee_scope_takes_priority(repository):
    eid = repository.create_employee('test employee')
    repository.confirm_calendar('2026-09-26', 'EMERGENCY_CLOSURE', 'หยุดน้ำท่วม', required_workday=False)
    repository.confirm_calendar('2026-09-26', 'WORKING_DAY', 'employee scheduled', required_workday=True, scope=eid)
    assert repository.calendar(eid, '2026-09-26')['required_workday'] == 1
    assert repository.calendar('another', '2026-09-26')['type'] == 'EMERGENCY_CLOSURE'
    with pytest.raises(ValueError, match='UNKNOWN'):
        repository.confirm_calendar('2026-09-27', 'UNKNOWN', 'unknown', required_workday=False)


def test_profile_bonus_is_configured_per_employee_not_global(repository):
    first = repository.create_employee('first employee')
    second = repository.create_employee('second employee')
    assert repository.profile(first)['attendance_bonus_default'] is None
    repository.confirm_profile(first, attendance_bonus_default='1200', base_salary='18000')
    assert repository.profile(first)['attendance_bonus_default'] == '1200'
    assert repository.profile(second)['attendance_bonus_default'] is None


def test_remembered_values_validity_and_policy(repository):
    eid = repository.create_employee('test employee')
    repository.remember_value(eid, 'phone', '500', '2026-08-01', ReusePolicy.AUTO_REUSE, valid_to='2026-09-30')
    assert repository.remembered(eid, 'phone', '2026-09-01')['value'] == '500'
    assert repository.remembered(eid, 'phone', '2026-10-01') is None
    with pytest.raises(sqlite3.IntegrityError):
        repository.remember_value(eid, 'phone', '500', '2026-10-01', valid_to='2026-09-01')


def test_transaction_rolls_back_data_and_audit(repository):
    with pytest.raises(RuntimeError):
        with repository.db.transaction() as con:
            con.execute("INSERT INTO app_settings VALUES ('a','1')")
            repository.audit(con, 'SHOULD_ROLL_BACK')
            raise RuntimeError('fail')
    assert not repository.db.query("SELECT * FROM app_settings WHERE key='a'")
    assert not repository.db.query("SELECT * FROM audit_log WHERE action='SHOULD_ROLL_BACK'")


def test_db_cannot_be_created_in_reference_or_outside_workspace():
    with pytest.raises(SafetyError):
        Database(Path('reference_data/unsafe.db'))
    with pytest.raises(SafetyError):
        Database(Path('data/unsafe_development.db'))


def test_history_import_is_idempotent_and_does_not_approve_rules(repository, historical_data, copied_reference):
    assert import_history(repository, historical_data, copied_reference) == 9
    ids = {e['canonical_name']: e['id'] for e in repository.employees()}
    assert import_history(repository, historical_data, copied_reference) == 0
    assert ids == {e['canonical_name']: e['id'] for e in repository.employees()}
    assert repository.resolve('ภานุวัฒน์') is None
    assert repository.profile(repository.resolve('ภาณุวัฒน์ มูลที'))['confirmed'] == 0
    assert not repository.db.query('SELECT * FROM business_rules')
    assert not repository.db.query('SELECT * FROM remembered_values')
