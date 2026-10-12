from dataclasses import replace
from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pytest

from app.db.database import Database
from app.db.repositories import Repository
from app.domain import PayrollState, ReusePolicy, ValueCategory, issue_key
from app.excel.payroll_reader import PayrollCell, PayrollEmployee, PayrollWorkbookAdapter, TemplateError
from app.models import AttendanceDay, AttendanceTotal, AttendanceWorkbook, EmployeeAttendance, SourceCell
from app.payroll.attendance_rules import detect_events
from app.payroll.calculator import DraftCalculator
from app.services.payroll_service import PayrollService, PayrollStateError, draft_difference


@pytest.fixture
def draft_case(workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'draft.db'))
    eid = repo.create_employee('test employee')
    repo.confirm_profile(eid, base_salary='18000', attendance_bonus_default='1200', phone_allowance='500')
    for n in range(1, 31):
        repo.confirm_calendar(f'2026-09-{n:02}', 'WORKING_DAY', 'Explicit test fixture schedule', required_workday=True)
    days = tuple(AttendanceDay(date(2026, 9, n), n+2, date(2026, 9, n), None, 'office', None,
        time(8), time(17), None, None, None, SourceCell(f'H{n+2}', None, 'EMPTY'),
        SourceCell(f'I{n+2}', 150, 'NUMBER', Decimal(150)), SourceCell(f'J{n+2}', 50, 'NUMBER', Decimal(50))) for n in range(1, 31))
    sheet = EmployeeAttendance('test', 'test employee', 'B1', None, 2, {}, None, days, (),
        {'ot': AttendanceTotal(Decimal(0), True, ()), 'allowance': AttendanceTotal(Decimal(4500), True, ()),
         'travel': AttendanceTotal(Decimal(1500), True, ())}, (), ())
    attendance = AttendanceWorkbook('test-source', 'source-hash', 2026, 9, (sheet,))
    fields = {'base': 18000, 'phone': 500, 'bonus': 1200, 'travel': 1200, 'allowance': 4000,
              'advance': 3000, 'normal_ot': 0, 'holiday_ot': 0, 'holiday_days': 0}
    payroll = PayrollWorkbookAdapter(Path('target'), 'target-hash', 'คิดค่าจ้าง ', 5, {},
        (PayrollEmployee('test employee', 9, {k: PayrollCell('P9', Decimal(v), v, None) for k, v in fields.items()}),))
    return repo, eid, attendance, payroll


def calculate(case):
    repo, eid, attendance, payroll = case
    return DraftCalculator(repo).calculate(attendance, payroll)


def test_travel_allowance_and_profile_bonus_are_source_based(draft_case):
    draft = calculate(draft_case)
    values = draft.employees[0].values
    assert values['travel'].final_value == Decimal(1500)
    assert values['allowance'].final_value == Decimal(4500)
    assert values['bonus'].final_value == Decimal(1200)
    assert values['travel'].category == ValueCategory.AUTO_CALCULATED
    assert values['advance'].final_value is None  # No automatic carry from 3000.


def test_late_arrival_does_not_automatically_remove_bonus(draft_case):
    repo, eid, attendance, payroll = draft_case
    day = attendance.employees[0].days[0]
    changed = replace(day, events=detect_events(day.date, 'test', {'M3': 'เช็คอินเกิน 8:30'}))
    sheet = replace(attendance.employees[0], days=(changed, *attendance.employees[0].days[1:]))
    draft = calculate((repo, eid, replace(attendance, employees=(sheet,)), payroll))
    assert draft.employees[0].values['bonus'].final_value == Decimal(1200)


def test_generic_leave_requires_confirmation_and_one_time_decision(draft_case):
    repo, eid, attendance, payroll = draft_case
    day = attendance.employees[0].days[0]
    changed = replace(day, events=detect_events(day.date, 'test', {'D3': 'ลา'}))
    sheet = replace(attendance.employees[0], days=(changed, *attendance.employees[0].days[1:]))
    attendance = replace(attendance, employees=(sheet,))
    before = calculate((repo, eid, attendance, payroll))
    leave = next(i for i in before.issues if i.kind == 'LEAVE')
    assert before.employees[0].values['bonus'].final_value is None
    repo.decide(attendance.source_hash, leave.key, {'leave_type': 'SICK_LEAVE', 'bonus_effect': 'KEEP'}, reason='one occurrence')
    assert calculate((repo, eid, attendance, payroll)).employees[0].values['bonus'].final_value == Decimal(1200)
    changed_source = replace(attendance, source_hash='next-source')
    assert any(i.kind == 'LEAVE' for i in calculate((repo, eid, changed_source, payroll)).issues)
    repo.remember_rule('LEAVE', 'ลา', {'leave_type': 'SICK_LEAVE', 'bonus_effect': 'KEEP'}, scope=eid)
    assert not any(i.kind == 'LEAVE' for i in calculate((repo, eid, changed_source, payroll)).issues)


def test_unknown_calendar_does_not_assume_workdays(draft_case):
    repo, _, _, _ = draft_case
    with repo.db.transaction() as con:
        con.execute("DELETE FROM company_calendar WHERE date='2026-09-26'")
    draft = calculate(draft_case)
    assert any(i.kind == 'CALENDAR' and i.day == '2026-09-26' for i in draft.issues)
    assert draft.employees[0].values['bonus'].final_value is None


def test_nonworking_company_day_does_not_remove_bonus(draft_case):
    repo, _, _, _ = draft_case
    repo.confirm_calendar('2026-09-26', 'EMERGENCY_CLOSURE', 'หยุดน้ำท่วม', required_workday=False)
    assert calculate(draft_case).employees[0].values['bonus'].final_value == Decimal(1200)


def test_confirmed_holiday_rule_supplies_calendar_only_in_its_scope(draft_case):
    repo,eid,attendance,payroll=draft_case
    day=attendance.employees[0].days[0]
    changed=replace(day,events=detect_events(day.date,'test',{'D3':'หยุดน้ำท่วม'}))
    sheet=replace(attendance.employees[0],days=(changed,*attendance.employees[0].days[1:]))
    with repo.db.transaction() as con: con.execute("DELETE FROM company_calendar WHERE date='2026-09-01'")
    repo.remember_rule('HOLIDAY','หยุดน้ำท่วม',{'type':'EMERGENCY_CLOSURE','required_workday':False,'affects_attendance_bonus':False},scope=eid)
    draft=calculate((repo,eid,replace(attendance,employees=(sheet,)),payroll))
    assert draft.employees[0].values['bonus'].final_value==Decimal(1200)
    assert not any(i.kind in {'HOLIDAY','CALENDAR'} and i.day=='2026-09-01' for i in draft.issues)
    assert repo.rule('HOLIDAY','หยุดน้ำท่วม','different employee') is None


def test_ot_category_is_not_guessed(draft_case):
    repo, eid, attendance, payroll = draft_case
    day = attendance.employees[0].days[0]
    from app.models import AttendanceEvent
    event = AttendanceEvent('OT_CLASSIFICATION_REQUIRED', day.date, 'test', 'H3', '2', hours=Decimal(2))
    changed = replace(day, ot=SourceCell('H3', 2, 'NUMBER', Decimal(2)), events=(event,))
    sheet = replace(attendance.employees[0], days=(changed, *attendance.employees[0].days[1:]))
    attendance = replace(attendance, employees=(sheet,))
    draft = calculate((repo, eid, attendance, payroll))
    issue = next(i for i in draft.issues if i.kind == 'OT')
    assert draft.employees[0].ot_cases[0].category is None
    assert draft.employees[0].values['normal_ot'].final_value is None
    repo.decide(attendance.source_hash, issue.key, {'category': 'HOLIDAY_OT', 'hours': '2'}, reason='confirmed category')
    new = calculate((repo, eid, attendance, payroll))
    assert new.employees[0].values['holiday_ot'].final_value == Decimal(2)
    assert new.employees[0].values['normal_ot'].final_value == Decimal(0)


def test_confirmed_ot_rule_is_deterministic(draft_case):
    repo, eid, attendance, payroll = draft_case
    from app.models import AttendanceEvent
    day = attendance.employees[0].days[0]
    event = AttendanceEvent('OT_CLASSIFICATION_REQUIRED', day.date, 'test', 'H3', '2', hours=Decimal(2))
    sheet = replace(attendance.employees[0], days=(replace(day, events=(event,)), *attendance.employees[0].days[1:]))
    repo.remember_rule('OT_BY_DAY_TYPE', 'WORKING_DAY', {'category': 'NORMAL'}, scope=eid)
    assert calculate((repo, eid, replace(attendance, employees=(sheet,)), payroll)).employees[0].values['normal_ot'].final_value == Decimal(2)


def test_overrides_preserve_source_and_previous_evidence(draft_case):
    repo, eid, attendance, _ = draft_case
    repo.decide(attendance.source_hash, issue_key('FIELD', eid, 'travel'), {'value': '1200'}, reason='manual business exception')
    value = calculate(draft_case).employees[0].values['travel']
    assert value.source_value == Decimal(1500)
    assert value.draft_value == Decimal(1500)
    assert value.user_override == value.final_value == Decimal(1200)
    assert value.reason == 'manual business exception'
    assert repo.db.query("SELECT * FROM audit_log WHERE action='REVIEW_DECISION'")


def test_manual_auto_reuse_policy_does_not_carry_one_time_advance(draft_case):
    repo, eid, _, _ = draft_case
    repo.remember_value(eid, 'advance', 3000, '2026-09-01', ReusePolicy.AUTO_REUSE)
    assert calculate(draft_case).employees[0].values['advance'].final_value is None
    repo.remember_value(eid, 'phone', 700, '2026-09-01', ReusePolicy.AUTO_REUSE)
    assert calculate(draft_case).employees[0].values['phone'].final_value == Decimal(700)


def test_text_total_cannot_be_silently_zero(draft_case):
    repo, eid, attendance, payroll = draft_case
    sheet = attendance.employees[0]
    sheet = replace(sheet, totals={**sheet.totals, 'travel': AttendanceTotal(Decimal(1450), False, ())})
    draft = calculate((repo, eid, replace(attendance, employees=(sheet,)), payroll))
    assert draft.employees[0].values['travel'].source_value == Decimal(1450)
    assert draft.employees[0].values['travel'].final_value is None
    assert draft.employees[0].values['travel'].category == ValueCategory.REVIEW_REQUIRED


def test_spike_warning_does_not_change_money(draft_case):
    repo, eid, attendance, _ = draft_case
    with repo.db.transaction() as con:
        con.execute('INSERT INTO payroll_observations VALUES (?,?,?,?,?,?,?,?)',
                    (eid, 2026, 8, 'travel', '100', None, 'test', 'old-hash'))
    draft = calculate(draft_case)
    assert any(i.kind == 'ANOMALY' and not i.critical for i in draft.issues)
    assert draft.employees[0].values['travel'].final_value == Decimal(1500)


@pytest.mark.parametrize('month,net,housing', [(1,30,23),(3,28,22),(8,27,21)])
def test_payroll_adapter_validates_historical_variants(copied_reference, month, net, housing):
    path = next((copied_reference / 'payroll').glob(f'* {month}.xlsx'))
    adapter = PayrollWorkbookAdapter.read(path)
    assert adapter.sheet_name == 'คิดค่าจ้าง '
    assert adapter.columns['net'] == net and adapter.columns['housing'] == housing
    assert len(adapter.employees) >= 10


def test_draft_idempotent_persistence_and_missing_review_blocks_confirmation(copied_reference, workbook_workspace):
    repo = Repository(Database(workbook_workspace / 'service.db'))
    service = PayrollService(repo)
    attendance = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    payroll = next((copied_reference / 'payroll').glob('* 8.xlsx'))
    first = service.prepare(attendance, payroll)
    counts = {table: repo.db.query(f'SELECT COUNT(*) AS n FROM {table}')[0]['n']
              for table in ('monthly_payroll', 'monthly_payroll_items', 'attendance_events')}
    second = service.prepare(attendance, payroll)
    assert second['unchanged'] and first['run']['revision'] == second['run']['revision']
    assert counts == {table: repo.db.query(f'SELECT COUNT(*) AS n FROM {table}')[0]['n'] for table in counts}
    assert any(i.kind == 'IDENTITY' for i in first['draft'].issues)
    with pytest.raises(PayrollStateError, match='ต้องตรวจสอบ'):
        service.confirm(2026, 8)
    restarted = PayrollService(Repository(Database(repo.db.path)))
    assert restarted.current(2026, 8)[1] == first['draft']


def test_payroll_and_attendance_period_must_match(copied_reference,workbook_workspace):
    repo=Repository(Database(workbook_workspace/'period.db'))
    service=PayrollService(repo)
    attendance=next((copied_reference/'attendance').glob('* 9.xlsx'))
    payroll=next((copied_reference/'payroll').glob('* 8.xlsx'))
    with pytest.raises(TemplateError,match='เดือน/ปี'):
        service.prepare(attendance,payroll)
    assert not repo.run(2026,9)


def test_new_payroll_identity_requires_roster_review_after_bootstrap(copied_reference,workbook_workspace):
    repo=Repository(Database(workbook_workspace/'roster.db'))
    repo.create_employee('existing confirmed employee')
    service=PayrollService(repo)
    attendance=next((copied_reference/'attendance').glob('* 8.xlsx'))
    payroll=next((copied_reference/'payroll').glob('* 8.xlsx'))
    draft=service.prepare(attendance,payroll)['draft']
    assert any(i.kind=='UNKNOWN_PAYROLL_EMPLOYEE' for i in draft.issues)
    assert len(repo.employees())==1


def test_diff_keeps_old_and_new_source_not_just_overridden_final(draft_case):
    old = calculate(draft_case)
    repo, eid, attendance, payroll = draft_case
    sheet = replace(attendance.employees[0], totals={**attendance.employees[0].totals,
                  'travel': AttendanceTotal(Decimal(1600), True, ())})
    new = calculate((repo, eid, replace(attendance, source_hash='new', employees=(sheet,)), payroll))
    diff = draft_difference(old, new)
    travel = next(v for v in diff['fields'] if v['field'] == 'travel')
    assert (travel['old_source'], travel['new_source'], travel['source_difference']) == (Decimal(1500),Decimal(1600),Decimal(100))
