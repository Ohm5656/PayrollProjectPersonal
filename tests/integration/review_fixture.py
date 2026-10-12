"""Explicit TEST-ONLY approvals. These are not NTP payroll business rules."""
from decimal import Decimal
from app.domain import issue_key
from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.excel.attendance_reader import read_attendance


def approve_month8(service, attendance_path, payroll_path):
    repo = service.repo
    attendance = read_attendance(attendance_path, year=2026, month=8)
    payroll = PayrollWorkbookAdapter.read(payroll_path)
    with repo.db.transaction():
        _initial_review(repo,attendance,payroll)
    result = service.prepare(attendance_path, payroll_path, force=True, year=2026, month=8)
    for _ in range(4):
        with repo.db.transaction():
            _approve_round(repo,attendance,payroll,result['draft'])
        result = service.prepare(attendance_path, payroll_path, force=True, year=2026, month=8)
        if result['draft'].state == 'READY': return result
    issues = [(i.kind, i.sheet, i.field, i.message) for i in result['draft'].issues if i.critical]
    raise AssertionError(f'Fixture did not resolve critical reviews: {issues}')


def _initial_review(repo,attendance,payroll):
    # Canonical names come from payroll evidence; these test decisions are
    # recorded with reasons, not encoded into the application.
    for person in payroll.employees:
        eid = repo.create_employee(person.name)
        repo.confirm_profile(eid, attendance_required=False, actor='TEST FIXTURE')
    for sheet in attendance.employees:
        if sheet.sheet_name in {'-', '--'}:
            decision = {'exclude': True}
        else:
            full = {'ภานุวัฒน์':'ภาณุวัฒน์ มูลที', 'อดิศักดิ์':'อดิศักดิ์ สาคำตา'}.get(sheet.sheet_name, sheet.full_name)
            eid = repo.resolve(full, 'payroll_full')
            if eid is None:
                raise AssertionError(f'Test fixture identity requires explicit mapping: {sheet.sheet_name} {full}')
            decision = {'employee_id': eid}
        repo.decide(attendance.source_hash, issue_key('IDENTITY', sheet.sheet_name), decision,
                    reason='TEST ONLY: human identity review simulation', actor='TEST FIXTURE')
    for n in range(1, 32):
        repo.confirm_calendar(f'2026-08-{n:02}', 'WORKING_DAY', 'TEST ONLY schedule: not an NTP rule',
                              required_workday=True, actor='TEST FIXTURE')


def _approve_round(repo,attendance,payroll,draft):
    for employee in draft.employees:
        if not employee.employee_id: continue
        person = payroll.employee(employee.name)
        for field, value in employee.values.items():
            if field in {'normal_money','holiday_money','holiday_ot_money','income','net'}: continue
            # Complete attendance totals continue to calculate themselves.
            if field in {'travel','allowance'} and value.final_value is not None: continue
            desired = value.source_value if field in {'travel','allowance'} else person.cells[field].value
            if desired is None: desired = Decimal(0)
            repo.decide(attendance.source_hash, issue_key('FIELD', employee.employee_id, field), {'value': str(desired)},
                reason='TEST ONLY: explicitly approved monthly fixture amount; never reuse', actor='TEST FIXTURE')
    for issue in draft.issues:
        if issue.kind == 'LEAVE':
            decision = {'leave_type':'OTHER', 'bonus_effect':'KEEP'}
        elif issue.kind == 'OT':
            event = next(c for e in draft.employees for c in e.ot_cases if e.employee_id == issue.employee_id and c.date == issue.day and c.cell == issue.cell)
            decision = {'category':'NORMAL', 'hours':str(event.hours)}
        elif issue.kind == 'HOLIDAY_WORK': decision = {'holiday_days':'0'}
        elif issue.kind == 'EVENT' or not issue.critical: decision = {'acknowledged': True}
        elif issue.kind == 'PAYSLIP_MAPPING' and issue.sheet == 'อดิศักดิ์':
            decision = {'assignments':{'I9':['tool_loss']}}
        else: continue
        repo.decide(attendance.source_hash, issue.key, decision,
                    reason='TEST ONLY: explicit event/layout approval simulation, not company policy', actor='TEST FIXTURE')
