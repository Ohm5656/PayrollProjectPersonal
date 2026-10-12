"""Draft calculations only. Every override preserves original source evidence."""
from calendar import monthrange
from datetime import date
from decimal import Decimal
import json

from app.domain import (
    EmployeeDraft, MANUAL_FIELDS, OTCase, PayrollDraft, PayrollValue, RECURRING_FIELDS,
    ReviewIssue, ReusePolicy, ValueCategory, decimal_value, issue_key, normalized_name,
)
from app.models import DayType, Severity
from app.excel.formulas import FormulaUnsupported, arithmetic, row_values
from app.payroll.anomaly import amount_warning

IDENTITY_CODES = {'UNKNOWN_EMPLOYEE', 'INCOMPLETE_EMPLOYEE_NAME', 'IDENTITY_CONFLICT',
                  'DUPLICATE_EMPLOYEE_LABEL', 'PLACEHOLDER_SHEET'}
OUTPUT_FIELDS = {'base', 'bonus', 'travel', 'allowance', 'normal_ot', 'holiday_ot', 'holiday_days',
                 *RECURRING_FIELDS, *MANUAL_FIELDS}


class DraftCalculator:
    def __init__(self, repository):
        self.repo = repository

    def calculate(self, attendance, payroll):
        with self.repo.db.read_snapshot():
            return self._calculate(attendance, payroll)

    def _calculate(self, attendance, payroll):
        decisions = self.repo.decisions(attendance.source_hash)
        payroll_people = {}
        globals_ = []
        for person in payroll.employees:
            eid = self.repo.resolve(person.name, 'payroll_full')
            if eid:
                payroll_people[eid] = person
            else:
                globals_.append(ReviewIssue(issue_key('UNKNOWN_PAYROLL_EMPLOYEE', person.name), 'UNKNOWN_PAYROLL_EMPLOYEE',
                    None, payroll.sheet_name, None, None, 'ต้องสร้างหรือจับคู่พนักงานในไฟล์เงินเดือน', person.name))
        assignments = {}
        unknown_drafts = []
        for sheet in attendance.employees:
            key = issue_key('IDENTITY', sheet.sheet_name)
            decision = decisions.get(key)
            if decision and decision.get('exclude'):
                continue
            conflict = any(i.code in IDENTITY_CODES - {'INCOMPLETE_EMPLOYEE_NAME'} for i in sheet.issues)
            eid = decision.get('employee_id') if decision else (None if conflict else self.repo.resolve(sheet.full_name))
            if decision and eid not in {e['id'] for e in self.repo.employees()}:
                eid = None
            if not eid or eid not in payroll_people:
                issue = ReviewIssue(key, 'IDENTITY', eid, sheet.sheet_name, None, sheet.name_cell,
                    'ต้องจับคู่พนักงาน หรือยืนยันไม่ใช้ชีตนี้ในเดือนนี้', sheet.full_name or sheet.sheet_name)
                unknown_drafts.append(EmployeeDraft('unmapped:' + sheet.sheet_name, None,
                    sheet.full_name or sheet.sheet_name, sheet.sheet_name, {}, (issue,)))
                continue
            assignments.setdefault(eid, []).append(sheet)
        employees = []
        for eid, person in payroll_people.items():
            sources = assignments.get(eid, [])
            if len(sources) > 1:
                globals_.append(ReviewIssue(issue_key('DUPLICATE_ATTENDANCE', eid), 'DUPLICATE_ATTENDANCE', eid,
                    None, None, None, 'มีหลายชีตอ้างถึงพนักงานคนเดียวกัน ห้ามรวมเงินโดยอัตโนมัติ'))
            sheet = sources[0] if len(sources) == 1 else None
            employees.append(self._employee(attendance, person, sheet, eid, decisions))
        return PayrollDraft(attendance.year, attendance.month, attendance.source_path, attendance.source_hash,
                            str(payroll.path), payroll.source_hash, tuple((*employees, *unknown_drafts)), tuple(globals_))

    def _employee(self, attendance, payroll_person, sheet, eid, decisions):
        issues = []
        values = {}
        profile = self.repo.profile(eid)
        period = f'{attendance.year:04}-{attendance.month:02}-01'
        sheet_name = sheet.sheet_name if sheet else None
        def add(kind, message, *, key=None, day=None, cell=None, raw='', field=None, critical=True, suggested=None):
            item = ReviewIssue(key or issue_key(kind, eid, sheet_name, day, cell, field, raw), kind,
                eid, sheet_name, day, cell, message, raw, critical, field, suggested)
            acknowledgement = decisions.get(item.key)
            if not (not critical and acknowledgement and acknowledgement.get('acknowledged')):
                issues.append(item)
            return item.key
        def field_value(field, category, source, draft, reason, *, complete=True):
            key = issue_key('FIELD', eid, field)
            decision = decisions.get(key)
            previous = self.repo.previous_value(eid, field, attendance.year, attendance.month)
            override = decimal_value(decision.get('value')) if decision and 'value' in decision else None
            final = override if override is not None else draft if complete else None
            if final is None:
                add('FIELD', 'ต้องยืนยันจำนวนเงิน/จำนวนหน่วย', key=key, field=field,
                    raw=str(source) if source is not None else '')
            values[field] = PayrollValue(field, category if complete else ValueCategory.REVIEW_REQUIRED,
                source, previous, draft, override, final, decision['_reason'] if override is not None else reason,
                f'{attendance.source_hash}:{sheet_name}' if field in ('travel', 'allowance', 'bonus', 'normal_ot', 'holiday_ot', 'holiday_days')
                else f'{payroll_person.name}:{payroll_person.cells[field].coordinate}', override is not None)
            warning = amount_warning(eid, sheet_name, field, final, previous)
            if warning and not decisions.get(warning.key, {}).get('acknowledged'):
                issues.append(warning)
        if not sheet and profile.get('attendance_required', 1):
            add('MISSING_ATTENDANCE', 'ไม่พบข้อมูลเวลาของพนักงานในเดือนนี้')
        if sheet:
            for parse_issue in sheet.issues:
                if parse_issue.code in IDENTITY_CODES:
                    continue  # An exact source-specific identity decision already resolved these.
                add('SOURCE_' + parse_issue.code, parse_issue.message, cell=parse_issue.cell,
                    critical=parse_issue.severity == Severity.ERROR)
        for field in ('travel', 'allowance'):
            total = sheet.totals.get(field) if sheet else None
            if not sheet and not profile.get('attendance_required', 1):
                source = payroll_person.cells[field].value
                field_value(field, ValueCategory.MANUAL, source, None, 'No attendance required; confirm this monthly amount')
            else:
                field_value(field, ValueCategory.AUTO_CALCULATED,
                    total.numeric_subtotal if total else None, total.source_sum if total else None,
                    'Sum of validated numeric daily attendance values', complete=bool(total and total.complete))
        for field in sorted((set(payroll_person.cells) & OUTPUT_FIELDS) - {'travel', 'allowance', 'bonus', 'normal_ot', 'holiday_ot', 'holiday_days'}):
            source = payroll_person.cells[field].value
            if field in RECURRING_FIELDS:
                remembered = self.repo.remembered(eid, field, period)
                configured = {'base': 'base_salary', 'phone': 'phone_allowance', 'position': 'position_allowance', 'housing': 'housing'}[field]
                draft, reason = None, 'Previous month is a suggestion only'
                if remembered and remembered['reuse_policy'] == ReusePolicy.AUTO_REUSE:
                    draft, reason = decimal_value(remembered['value']), 'Explicit AUTO_REUSE policy'
                elif profile.get('confirmed') and profile.get(configured) is not None:
                    draft, reason = decimal_value(profile[configured]), 'Confirmed employee recurring profile'
                field_value(field, ValueCategory.RECURRING, source, draft, reason)
            else:
                field_value(field, ValueCategory.MANUAL, source, None, 'Monthly manual value; never automatically carried forward')
        ot_cases, totals, work_days, uncertain_ot = [], {'normal_ot': Decimal(0), 'holiday_ot': Decimal(0)}, Decimal(0), False
        bonus_uncertain, bonus_cut, custom_bonus = False, False, None
        calendars = {}
        def day_calendar(day):
            if day not in calendars:
                calendar = self.repo.calendar(eid, day)
                if calendar is None and sheet:
                    record = next((r for r in sheet.days if r.date == day), None)
                    rules = [self.repo.rule('HOLIDAY', e.raw_text, eid) for e in record.events
                             if e.event_type == 'HOLIDAY_SUGGESTION'] if record else []
                    rules = [r for r in rules if r and r.get('type') in {t.value for t in DayType if t != DayType.UNKNOWN}]
                    if rules and all(r == rules[0] for r in rules):
                        calendar = {'type': rules[0]['type'], 'required_workday': bool(rules[0].get('required_workday')),
                                    'affects_attendance_bonus': bool(rules[0].get('affects_attendance_bonus'))}
                calendars[day] = calendar
            return calendars[day]
        if sheet:
            for day in sheet.days:
                calendar = day_calendar(day.date)
                for event in day.events:
                    key = issue_key(event.event_type, eid, sheet_name, day.date.isoformat(), event.cell, event.raw_text)
                    decision = decisions.get(key)
                    if event.event_type == 'LEAVE':
                        decision = decision or self.repo.rule('LEAVE', event.raw_text, eid)
                        if not decision or decision.get('leave_type') not in {'SICK_LEAVE', 'PERSONAL_LEAVE', 'ANNUAL_LEAVE', 'UNPAID_LEAVE', 'OTHER'} or decision.get('bonus_effect') not in {'KEEP', 'CUT', 'CUSTOM'}:
                            bonus_uncertain = True
                            add('LEAVE', 'โปรดระบุประเภทลาและผลต่อเบี้ยขยัน', key=key, day=str(day.date), cell=event.cell, raw=event.raw_text)
                        else:
                            bonus_cut |= decision['bonus_effect'] == 'CUT'
                            if decision['bonus_effect'] == 'CUSTOM':
                                approved_bonus = decimal_value(decision.get('bonus_value'))
                                if custom_bonus is not None and approved_bonus != custom_bonus:
                                    bonus_uncertain = True
                                    add('BONUS_CONFLICT', 'มีจำนวนเบี้ยขยันที่กำหนดเองขัดแย้งกัน โปรดแก้รายการลาให้สอดคล้องกัน', day=str(day.date))
                                custom_bonus = approved_bonus
                                bonus_uncertain |= approved_bonus is None
                    elif event.event_type == 'OT_CLASSIFICATION_REQUIRED':
                        category = decision.get('category') if decision else None
                        if not category and calendar:
                            rule = self.repo.rule('OT_BY_DAY_TYPE', calendar['type'], eid)
                            category = rule.get('category') if rule else None
                        hours = decimal_value(decision.get('hours')) if decision and 'hours' in decision else event.hours
                        valid = category in ('NORMAL', 'HOLIDAY_OT') and hours is not None and hours >= 0
                        ot_cases.append(OTCase(str(day.date), event.cell, event.raw_text, event.hours,
                            calendar['type'] if calendar else DayType.UNKNOWN,
                            category if valid else None, category if valid else None,
                            'CONFIRMED' if valid else 'UNCONFIRMED',
                            'Explicit user decision or confirmed rule/calendar' if valid else 'No deterministic OT category'))
                        if valid:
                            totals['normal_ot' if category == 'NORMAL' else 'holiday_ot'] += hours
                        else:
                            uncertain_ot = True
                            add('OT', 'ต้องจัดประเภท OT ปกติ/OT วันหยุด', key=key, day=str(day.date), cell=event.cell, raw=event.raw_text)
                    elif event.event_type == 'WORK_ON_HOLIDAY_CANDIDATE':
                        if calendar and calendar['required_workday']:
                            continue
                        if decision and 'holiday_days' in decision:
                            work_days += decimal_value(decision['holiday_days'])
                        else:
                            uncertain_ot = True
                            add('HOLIDAY_WORK', 'โปรดยืนยันจำนวนวันทำงานในวันหยุด', key=key, day=str(day.date), cell=event.cell, raw=event.raw_text)
                    elif event.event_type == 'HOLIDAY_SUGGESTION':
                        rule = self.repo.rule('HOLIDAY', event.raw_text, eid)
                        if not calendar and not rule:
                            bonus_uncertain = True
                            add('HOLIDAY', 'โปรดยืนยันสถานะวันหยุดและขอบเขตพนักงาน', key=key, day=str(day.date), cell=event.cell, raw=event.raw_text, suggested=event.suggested_type)
                    else:
                        critical = event.event_type in {'ALLOWANCE_CUT_NOTE', 'ATTENDANCE_BONUS_CUT_NOTE', 'MISSING_CLOCK_NOTE'}
                        if not decision or not decision.get('acknowledged'):
                            add('EVENT', 'ตรวจข้อความหมายเหตุและผลที่เกี่ยวข้อง', key=key, day=str(day.date), cell=event.cell,
                                raw=event.raw_text, critical=critical)
                        if decision and event.event_type == 'ATTENDANCE_BONUS_CUT_NOTE':
                            bonus_cut |= decision.get('bonus_effect') == 'CUT'
            if not sheet.totals.get('ot') or not sheet.totals['ot'].complete:
                uncertain_ot = True
        else:
            uncertain_ot = True
        for field, amount in (*totals.items(), ('holiday_days', work_days)):
            field_value(field, ValueCategory.AUTO_CALCULATED, amount, amount, 'Only confirmed OT classifications and work-day decisions', complete=not uncertain_ot)
        bonus_override = decisions.get(issue_key('FIELD', eid, 'bonus'))
        bonus = None
        if not bonus_override:
            default = decimal_value(profile.get('attendance_bonus_default')) if profile.get('confirmed') else None
            if not bonus_uncertain and bonus_cut:
                bonus = Decimal(0)
            elif not bonus_uncertain and custom_bonus is not None:
                bonus = custom_bonus
            elif default is not None and not bonus_uncertain and sheet:
                eligible = True
                actual = {day.date: day for day in sheet.days}
                for n in range(1, monthrange(attendance.year, attendance.month)[1] + 1):
                    day = date(attendance.year, attendance.month, n)
                    calendar = day_calendar(day)
                    if not calendar:
                        add('CALENDAR', 'ยังไม่ยืนยันวันทำงานที่บริษัทกำหนด', day=str(day), suggested='UNKNOWN')
                        eligible = False
                    elif calendar['required_workday']:
                        record = actual.get(day)
                        leave = record and any(e.event_type == 'LEAVE' for e in record.events)
                        if not record or (not leave and record.clock_in is None and record.clock_out is None):
                            add('REQUIRED_DAY', 'วันทำงานที่กำหนดยังไม่มีหลักฐานเวลาหรือการลาที่อนุมัติ', day=str(day))
                            eligible = False
                    elif calendar['affects_attendance_bonus']:
                        add('CALENDAR_BONUS_EFFECT', 'ผลของวันหยุดต่อเบี้ยขยันต้องมีกฎหรือการยืนยัน', day=str(day))
                        eligible = False
                if eligible:
                    bonus = default
        field_value('bonus', ValueCategory.AUTO_CALCULATED, bonus, bonus,
                    'Employee bonus configuration, confirmed required workdays and confirmed leave rules', complete=bonus is not None)
        # Preview the workbook's own arithmetic instead of introducing payroll
        # rates or a new income/net formula. Unsupported expressions stay in review.
        proposed = {key: value.final_value for key, value in values.items()}
        resolver = row_values(payroll_person, proposed)
        for field in ('normal_money', 'holiday_money', 'holiday_ot_money', 'income', 'net'):
            if field not in payroll_person.cells:
                continue
            cell = payroll_person.cells[field]
            computed = None
            try:
                computed = arithmetic(cell.formula, resolver) if cell.formula else cell.value or Decimal(0)
            except FormulaUnsupported:
                pass
            field_value(field, ValueCategory.AUTO_CALCULATED, cell.value, computed,
                        'Preview of validated existing Excel arithmetic; Excel recalculation must agree', complete=computed is not None)
        return EmployeeDraft(eid, eid, payroll_person.name, sheet_name, values, tuple(issues), tuple(ot_cases))
