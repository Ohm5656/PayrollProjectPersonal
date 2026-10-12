"""Atomic draft persistence, reviews, audit and protected-month transitions."""
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4, uuid5, NAMESPACE_URL
import json
from threading import RLock
from app.services.serialization import serialized

from app.domain import FINAL_STATES, PayrollState, decode_draft, encode, issue_key, utc_now
from app.excel.attendance_reader import read_attendance
from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.excel.workbook_source import file_hash
from app.payroll.calculator import DraftCalculator


class PayrollStateError(ValueError):
    pass


def draft_difference(old, new):
    before = {(e.key, field): value for e in old.employees for field, value in e.values.items()}
    after = {(e.key, field): value for e in new.employees for field, value in e.values.items()}
    changes = []
    for eid, field in sorted(before.keys() | after.keys()):
        a, b = before.get((eid, field)), after.get((eid, field))
        if a != b:
            changes.append({'employee_key': eid, 'field': field,
                'old_source': a.source_value if a else None, 'new_source': b.source_value if b else None,
                'old_final': a.final_value if a else None, 'new_draft': b.final_value if b else None,
                'source_difference': (b.source_value - a.source_value) if a and b and a.source_value is not None and b.source_value is not None else None})
    return {'message': 'พบการแก้ไขบันทึกเวลาหลังยืนยันเงินเดือน', 'old_hash': old.source_hash,
            'new_hash': new.source_hash, 'fields': changes,
            'old_issues': [asdict(i) for i in old.issues], 'new_issues': [asdict(i) for i in new.issues]}


class PayrollService:
    def __init__(self, repository):
        self.repo = repository
        self.calculator = DraftCalculator(repository)
        self.operation_lock = RLock()

    def current(self, year, month):
        run = self.repo.run(year, month)
        return (run, decode_draft(run['evidence'])) if run else (None, None)

    @serialized
    def prepare(self, attendance_path, payroll_path, *, force=False, year=None, month=None):
        attendance = read_attendance(attendance_path, year=year, month=month)
        payroll = PayrollWorkbookAdapter.read(payroll_path)
        if payroll.period() != (attendance.year,attendance.month):
            from app.excel.payroll_reader import TemplateError
            raise TemplateError('เดือน/ปีของไฟล์เงินเดือนไม่ตรงกับบันทึกเวลา กรุณาเลือกไฟล์คู่เดือนเดียวกัน')
        run = self.repo.run(attendance.year, attendance.month)
        same_pair = run and Path(run['source_path']).resolve() == Path(attendance.source_path).resolve() and Path(run['payroll_path']).resolve() == payroll.path
        if run and not same_pair and run['state'] in FINAL_STATES:
            raise PayrollStateError('เดือนนี้ยืนยันด้วยสำเนาคู่อื่น กรุณาเลือกคู่เดิมหรือเปิดเดือนใหม่ก่อนเปลี่ยนไฟล์')
        if same_pair and run['source_hash'] == attendance.source_hash and run['payroll_hash'] == payroll.source_hash and not force:
            return {'run': run, 'draft': decode_draft(run['evidence']), 'unchanged': True, 'protected': run['state'] in FINAL_STATES}
        if not self.repo.employees():
            for person in payroll.employees:
                self.repo.create_employee(person.name, actor='initial exact payroll roster')
        draft = self.calculator.calculate(attendance, payroll)
        from app.excel.payslip_adapter import preflight_payslips
        draft = preflight_payslips(draft, payroll, self.repo)
        event_decisions = self.repo.decisions(draft.source_hash)
        with self.repo.db.transaction() as con:
            current = con.execute('SELECT * FROM payroll_runs WHERE year=? AND month=?', (draft.year, draft.month)).fetchone()
            if current and current['state'] in FINAL_STATES:
                if current['source_hash'] != draft.source_hash:
                    diff = draft_difference(decode_draft(current['evidence']), draft)
                    con.execute('INSERT INTO source_changes(run_id,old_hash,new_hash,difference,created_at) VALUES (?,?,?,?,?) '
                                'ON CONFLICT(run_id,new_hash) DO NOTHING',
                                (current['id'], current['source_hash'], draft.source_hash, encode(diff), utc_now()))
                    self.repo.audit(con, 'ATTENDANCE_CHANGED_AFTER_CONFIRMATION', year=draft.year, month=draft.month,
                                    old=current['source_hash'], new=draft.source_hash, actor='system')
                    return {'run': dict(current), 'draft': decode_draft(current['evidence']), 'protected': True, 'difference': diff}
                return {'run': dict(current), 'draft': decode_draft(current['evidence']), 'protected': True, 'unchanged': True}
            run_id = current['id'] if current else str(uuid4())
            revision = current['revision'] + 1 if current else 1
            con.execute('INSERT INTO payroll_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,NULL) ON CONFLICT(year,month) '
                        'DO UPDATE SET state=excluded.state,source_path=excluded.source_path,source_hash=excluded.source_hash,'
                        'payroll_path=excluded.payroll_path,payroll_hash=excluded.payroll_hash,revision=excluded.revision,'
                        'evidence=excluded.evidence,calculated_at=excluded.calculated_at,confirmed_at=NULL',
                        (run_id, draft.year, draft.month, draft.state.value, draft.source_path, draft.source_hash,
                         draft.payroll_path, draft.payroll_hash, revision, encode(draft.evidence()), utc_now()))
            con.execute('DELETE FROM monthly_payroll WHERE run_id=?', (run_id,))
            con.execute('DELETE FROM review_issues WHERE run_id=?', (run_id,))
            for employee in draft.employees:
                pid = str(uuid5(NAMESPACE_URL, run_id + ':' + employee.key))
                con.execute('INSERT INTO monthly_payroll VALUES (?,?,?,?,?,?,?,?,NULL)',
                    (pid, run_id, employee.employee_id, employee.key, draft.year, draft.month,
                     'READY' if employee.ready else 'NEEDS_REVIEW', utc_now()))
                for key, value in employee.values.items():
                    con.execute('INSERT INTO monthly_payroll_items VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (pid, key, str(value.final_value) if value.final_value is not None else None,
                         value.category.value, value.source_reference,
                         str(value.source_value) if value.source_value is not None else None,
                         str(value.previous_value) if value.previous_value is not None else None,
                         str(value.draft_value) if value.draft_value is not None else None,
                         str(value.user_override) if value.user_override is not None else None, int(value.confirmed), value.reason))
            for issue in draft.issues:
                con.execute('INSERT OR IGNORE INTO review_issues VALUES (?,?,?,?,?,?)',
                            (run_id, issue.key, issue.employee_id, issue.kind, int(issue.critical), encode(asdict(issue))))
            assignments = {e.sheet: e.employee_id for e in draft.employees if e.sheet and e.employee_id}
            for sheet in attendance.employees:
                for day in sheet.days:
                    for event in day.events:
                        event_id = issue_key(event.event_type, assignments.get(sheet.sheet_name), sheet.sheet_name, str(day.date), event.cell, event.raw_text)
                        con.execute('INSERT OR IGNORE INTO attendance_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                            (issue_key('PERSISTED_EVENT', draft.source_hash, sheet.sheet_name, str(day.date), event.cell, event.event_type),
                             assignments.get(sheet.sheet_name), str(day.date), event.event_type, event.raw_text,
                             str(event.hours) if event.hours is not None else None,
                             str(event.days) if event.days is not None else None,
                             int(event_id in event_decisions), draft.source_path,
                             draft.source_hash, sheet.sheet_name, event.cell))
            con.execute('INSERT INTO processed_files VALUES (?,?,?,?) ON CONFLICT(path) DO UPDATE SET '
                        'modified_time=excluded.modified_time,hash=excluded.hash,processed_at=excluded.processed_at',
                        (draft.source_path, Path(draft.source_path).stat().st_mtime_ns, draft.source_hash, utc_now()))
            self.repo.audit(con, 'DRAFT_CALCULATED', year=draft.year, month=draft.month,
                            new={'revision': revision, 'issues': len(draft.issues)}, source=draft.source_hash, actor='system')
        return {'run': self.repo.run(draft.year, draft.month), 'draft': draft, 'protected': False, 'unchanged': False}

    @serialized
    def confirm(self, year, month, *, actor='user', expected_revision=None):
        with self.repo.db.transaction() as con:
            run = con.execute('SELECT * FROM payroll_runs WHERE year=? AND month=?', (year, month)).fetchone()
            if not run or run['state'] != PayrollState.READY:
                raise PayrollStateError('ยังมีรายการสำคัญที่ต้องตรวจสอบ')
            if expected_revision is not None and run['revision'] != expected_revision:
                raise PayrollStateError('ข้อมูลฉบับร่างเปลี่ยน กรุณาตรวจสอบใหม่')
            draft = decode_draft(run['evidence'])
            if draft.state != PayrollState.READY:
                raise PayrollStateError('Draft validation failed')
            if file_hash(Path(run['source_path'])) != run['source_hash'] or file_hash(Path(run['payroll_path'])) != run['payroll_hash']:
                raise PayrollStateError('ไฟล์เปลี่ยนหลังคำนวณ กรุณาอ่านข้อมูลใหม่')
            con.execute('UPDATE payroll_runs SET state=?,confirmed_at=? WHERE id=?', (PayrollState.CONFIRMED, utc_now(), run['id']))
            con.execute('UPDATE monthly_payroll SET status=?,confirmed_at=? WHERE run_id=?', (PayrollState.CONFIRMED, utc_now(), run['id']))
            self.repo.audit(con, 'PAYROLL_CONFIRMED', year=year, month=month, old=run['state'], new=PayrollState.CONFIRMED,
                            source=run['source_hash'], actor=actor)
        return self.repo.run(year, month)

    @serialized
    def reopen(self, year, month, *, reason, actor='user'):
        if not reason.strip():
            raise PayrollStateError('ต้องระบุเหตุผลก่อนเปิดเดือนที่ยืนยันแล้ว')
        with self.repo.db.transaction() as con:
            run = con.execute('SELECT * FROM payroll_runs WHERE year=? AND month=?', (year, month)).fetchone()
            if not run or run['state'] not in FINAL_STATES:
                raise PayrollStateError('เดือนนี้ไม่ได้อยู่ในสถานะยืนยันแล้ว')
            con.execute('UPDATE payroll_runs SET state=?,confirmed_at=NULL WHERE id=?', (PayrollState.DRAFT, run['id']))
            con.execute('UPDATE monthly_payroll SET status=?,confirmed_at=NULL WHERE run_id=?', (PayrollState.DRAFT, run['id']))
            con.execute('UPDATE source_changes SET acknowledged=1 WHERE run_id=?', (run['id'],))
            self.repo.audit(con, 'MONTH_REOPENED', year=year, month=month, old=run['state'],
                            new={'state': 'DRAFT', 'reason': reason}, actor=actor)

    @serialized
    def lock(self, year, month, *, actor='user'):
        with self.repo.db.transaction() as con:
            run = con.execute('SELECT * FROM payroll_runs WHERE year=? AND month=?', (year, month)).fetchone()
            if not run or run['state'] != PayrollState.WRITTEN:
                raise PayrollStateError('ต้องเขียนและตรวจสอบไฟล์สำเร็จก่อนล็อกเดือน')
            con.execute('UPDATE payroll_runs SET state=? WHERE id=?', (PayrollState.LOCKED, run['id']))
            con.execute('UPDATE monthly_payroll SET status=? WHERE run_id=?', (PayrollState.LOCKED, run['id']))
            self.repo.audit(con, 'MONTH_LOCKED', year=year, month=month, actor=actor)
