"""Staged COM writes with a verified backup; development paths only."""
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
import json
import os
import shutil

from app.domain import PayrollState, utc_now
from app.excel.excel_gateway import ExcelGateway, reserved_copy
from app.excel.formulas import FormulaUnsupported, arithmetic, row_values
from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.excel.workbook_source import file_hash
from app.excel.workbook_validator import WorkbookStructure, equivalent, validate_expected
from app.excel.package_values import preserve_package_values
from app.excel.atomic_file import atomic_replace
from app.safety import ROOT, SafetyError, development_target, verify_baseline
from app.services.backup_service import BackupService
from app.services.serialization import serialized


@dataclass(frozen=True)
class CellWrite:
    sheet: str
    address: str
    value: object


@dataclass(frozen=True)
class WritePlan:
    target: Path
    source_hash: str
    writes: tuple[CellWrite, ...]
    expected: tuple
    year: int
    month: int


def build_plan(draft, adapter, employee_ids=None, *, validate_target=True):
    if str(adapter.path) != draft.payroll_path or adapter.source_hash != draft.payroll_hash:
        raise SafetyError('Payroll destination changed since the reviewed draft')
    selected = set(employee_ids) if employee_ids is not None else {e.employee_id for e in draft.employees if e.employee_id}
    if not selected or selected - {e.employee_id for e in draft.employees if e.employee_id}:
        raise SafetyError('A valid employee selection is required')
    if draft.global_issues:
        raise SafetyError('Unresolved workbook-wide issues prevent writing')
    writes, expected = [], []
    for employee in draft.employees:
        if employee.employee_id not in selected:
            continue
        if not employee.ready:
            raise SafetyError('Critical employee review items must be resolved before writing')
        person = adapter.employee(employee.name)
        proposed = {key: value.final_value for key, value in employee.values.items()}
        resolver = row_values(person, proposed)
        for field, value in employee.values.items():
            if field not in person.cells or value.final_value is None:
                raise SafetyError('Payroll input field lacks a validated destination')
            cell = person.cells[field]
            if not cell.formula and cell.raw is None and value.final_value == 0:
                # An approved zero preserves an originally blank input. Excel
                # arithmetic already treats that blank reference as zero.
                expected.append((adapter.sheet_name, cell.coordinate, None))
                continue
            if cell.formula:
                try:
                    predicted = arithmetic(cell.formula, resolver)
                except FormulaUnsupported as exc:
                    raise SafetyError('A protected formula cannot be safely checked') from exc
                if not equivalent(predicted, value.final_value):
                    raise SafetyError(f'Approved amount conflicts with a protected formula at {adapter.sheet_name}!{cell.coordinate}')
            elif not equivalent(cell.value, value.final_value):
                writes.append(CellWrite(adapter.sheet_name, cell.coordinate, value.final_value))
            expected.append((adapter.sheet_name, cell.coordinate, value.final_value))
    if validate_target:
        development_target(adapter.path)
    return WritePlan(adapter.path, adapter.source_hash, tuple(writes), tuple(expected), draft.year, draft.month)


class PayrollWriter:
    def __init__(self, service=None, *, backup_root=None, gateway_factory=ExcelGateway):
        self.service = service
        self.backup_root = backup_root
        self.gateway_factory = gateway_factory
        self.last_result = None

    def execute(self, plan, *, run_id=None, allowed_states=None, expected_revision=None):
        target = development_target(plan.target)
        baseline_path = ROOT / 'reports/source_hash_baseline.json'
        if baseline_path.exists():
            verify_baseline(json.loads(baseline_path.read_text(encoding='utf-8')))
        with reserved_copy(target):
            pass  # Report open/unsaved/locked copies before attempting a read or backup.
        adapter = PayrollWorkbookAdapter.read(target)
        if adapter.source_hash != plan.source_hash:
            raise SafetyError('Destination changed before write')
        before = WorkbookStructure.read(target)
        operation_id = str(uuid4())
        stage = development_target(target.parent / '_staging' / operation_id / target.name)
        stage.parent.mkdir(parents=True, exist_ok=True)
        committed = False
        backup = None
        result_hash = None
        try:
            with reserved_copy(target) as original:
                if sha256(original).hexdigest() != plan.source_hash:
                    raise SafetyError('Destination changed during reservation')
                original_inode = target.stat().st_ino
                backup = BackupService(self.backup_root or target.parent / 'backups').create(target, original, plan.year, plan.month)
                if self.service and run_id:
                    with self.service.repo.db.transaction() as con:
                        con.execute('INSERT INTO write_operations(id,run_id,status,target,backup_path,backup_hash,created_at) VALUES (?,?,?,?,?,?,?)',
                            (operation_id, run_id, 'STAGED', str(target), str(backup.path), backup.sha256, utc_now()))
                        self.service.repo.audit(con, 'WORKBOOK_BACKUP', new={'path': str(backup.path), 'hash': backup.sha256}, actor='system')
                with stage.open('xb') as stream:
                    stream.write(original)
                with self.gateway_factory() as gateway:
                    with gateway.open_copy(stage) as book:
                        for change in plan.writes:
                            cell = book.Worksheets(change.sheet).Range(change.address)
                            if bool(cell.HasFormula):
                                raise SafetyError('A formula cell cannot be overwritten')
                            if isinstance(change.value, datetime):
                                from openpyxl.utils.datetime import to_excel, CALENDAR_MAC_1904, CALENDAR_WINDOWS_1900
                                cell.Value2 = to_excel(change.value, CALENDAR_MAC_1904 if book.Date1904 else CALENDAR_WINDOWS_1900)
                            else:
                                cell.Value2 = float(change.value) if isinstance(change.value, Decimal) else change.value
                            del cell
                        gateway.app.CalculateFull()
                        book.Save()
                    # Restore original styles/package parts before the native
                    # reopen, so Excel validates the exact file to be committed.
                    preserve_package_values(original, stage, plan.writes)
                    # Reopen only our staged copy before it can replace the target.
                    with gateway.open_copy(stage, read_only=True):
                        pass
                    owned_pid = gateway.pid
                    pre_existing = dict(gateway.pre_existing)
                    excel_version = gateway.version
                    owned_creation_time=gateway.creation_time
                # Excel normalizes some legacy styles on Save. Keep the original
                # package and transfer only approved values and exact formula caches.
                before.validate(WorkbookStructure.read(stage))
                validate_expected(stage, plan.expected)
                # Recheck unique headers from the saved staged workbook.
                after_adapter = PayrollWorkbookAdapter.read(stage)
                if after_adapter.sheet_name != adapter.sheet_name or after_adapter.columns != adapter.columns:
                    raise SafetyError('Payroll header structure changed')
                result_hash = file_hash(stage)
                if self.service and run_id:
                    with self.service.repo.db.connection() as con:
                        current = con.execute('SELECT state,source_path,source_hash,revision FROM payroll_runs WHERE id=?', (run_id,)).fetchone()
                        permitted = allowed_states or {PayrollState.CONFIRMED}
                        if not current or current['state'] not in permitted or (expected_revision is not None and current['revision'] != expected_revision) or file_hash(Path(current['source_path'])) != current['source_hash']:
                            raise SafetyError('Attendance or confirmed month state changed while Excel calculated; write aborted')
                if target.stat().st_ino != original_inode:
                    raise SafetyError('Destination identity changed while the write was staged')
                atomic_replace(stage, target)
                committed = True
            if file_hash(target) != result_hash:
                raise SafetyError('Atomic replacement hash mismatch')
            self.post_commit_validate(target, plan.expected)
            self.last_result = {'operation_id': operation_id, 'target': str(target),
                'backup_path': str(backup.path), 'backup_hash': backup.sha256, 'result_hash': result_hash,
                'excel_pid': owned_pid, 'pre_existing_excel': pre_existing, 'excel_version': excel_version,
                'excel_creation_time':owned_creation_time,'excel_exit_code':gateway.process_exit_code,
                'writes': len(plan.writes), 'validated': True}
            return self.last_result
        except Exception as exc:
            restored = False
            if committed and backup and result_hash:
                # Restore only if this remains the exact file this operation wrote.
                with reserved_copy(target) as current:
                    if sha256(current).hexdigest() != result_hash:
                        raise SafetyError('Destination changed externally; automatic rollback deferred; verified backup retained') from exc
                    recovery = development_target(target.parent / '_staging' / operation_id / ('restore_' + target.name))
                    content = backup.path.read_bytes()
                    if sha256(content).hexdigest() != backup.sha256:
                        raise SafetyError('Backup no longer valid; automatic restore forbidden') from exc
                    with recovery.open('xb') as stream:
                        stream.write(content)
                    atomic_replace(recovery, target)
                restored = file_hash(target) == backup.sha256
                if not restored:
                    raise SafetyError('Rollback validation failed; stop and retain backup') from exc
            if self.service and run_id and backup:
                with self.service.repo.db.transaction() as con:
                    con.execute('UPDATE write_operations SET status=?,error=?,completed_at=? WHERE id=?',
                                ('ROLLED_BACK' if restored else 'FAILED', type(exc).__name__, utc_now(), operation_id))
                    self.service.repo.audit(con, 'WORKBOOK_WRITE_FAILED', new={'backup': str(backup.path), 'restored': restored}, actor='system')
            raise

    @staticmethod
    def post_commit_validate(target, expected):
        validate_expected(target, expected)

    @serialized
    def write_employee_copy(self,year,month,employee_id,*,reason,actor='user'):
        """First controlled copy test: one approved employee, no month finalization."""
        if not reason.strip(): raise SafetyError('ต้องระบุเหตุผลการทดสอบรายคน')
        run,draft=self.service.current(year,month)
        permitted={PayrollState.DRAFT,PayrollState.NEEDS_REVIEW,PayrollState.READY}
        if not run or run['state'] not in permitted: raise SafetyError('ต้องเปิดเดือนใหม่ก่อนทดสอบรายคน')
        if file_hash(Path(draft.source_path))!=draft.source_hash: raise SafetyError('Attendance changed since review')
        adapter=PayrollWorkbookAdapter.read(draft.payroll_path)
        plan=build_plan(draft,adapter,[employee_id])
        employee=next(e for e in draft.employees if e.employee_id==employee_id)
        from app.excel.payslip_adapter import PayslipAdapter,configured_mapping
        slips=PayslipAdapter.read(adapter.path)
        slip=slips.employee(employee.name)
        delta,expectations=slips.plan_employee(employee,adapter.employee(employee.name),
            mapping=configured_mapping(self.service.repo,draft,employee,slip))
        changes=list(plan.writes)+list(delta)
        validations=list(plan.expected)+list(expectations)
        from app.excel.workbook_source import WorkbookSnapshot
        with WorkbookSnapshot.read(adapter.path).open() as (book,_):
            for address,wanted in [(slip.period_cell,month),(slip.payment_date_cell,adapter.payment_date())]:
                if book[slip.sheet][address].value!=wanted: changes.append(CellWrite(slip.sheet,address,wanted))
                validations.append((slip.sheet,address,wanted))
        plan=replace(plan,writes=tuple(changes),expected=tuple(validations))
        if not changes:
            try:
                validate_expected(adapter.path,plan.expected)
                return {'unchanged':True,'validated':True}
            except SafetyError: pass  # Existing caches need isolated recalculation.
        result=self.execute(plan,run_id=run['id'],allowed_states=permitted,expected_revision=run['revision'])
        with self.service.repo.db.transaction() as con:
            con.execute('UPDATE write_operations SET status=?,result_hash=?,completed_at=? WHERE id=?',
                ('VALIDATED_SINGLE',result['result_hash'],utc_now(),result['operation_id']))
            self.service.repo.audit(con,'SINGLE_EMPLOYEE_COPY_TEST',employee_id=employee_id,year=year,month=month,
                new={'reason':reason,**result},actor=actor)
        self.service.prepare(draft.source_path,draft.payroll_path,force=True,year=year,month=month)
        return result

    @serialized
    def write_month(self, year, month, *, actor='user', payslip_employee_ids=None):
        if not self.service:
            raise SafetyError('Month writes require a payroll service')
        run, draft = self.service.current(year, month)
        if not run or run['state'] not in {PayrollState.CONFIRMED, PayrollState.WRITTEN}:
            raise SafetyError('Payroll must be confirmed and not locked before writing')
        if file_hash(Path(draft.source_path)) != draft.source_hash:
            raise SafetyError('Attendance changed after confirmation')
        if run['state'] == PayrollState.WRITTEN and file_hash(Path(draft.payroll_path)) == run['payroll_hash']:
            return {'unchanged': True, 'validated': True}
        adapter = PayrollWorkbookAdapter.read(Path(draft.payroll_path))
        if adapter.source_hash != run['payroll_hash']:
            raise SafetyError('Payroll copy changed outside the validated write workflow')
        reviewed_draft = replace(draft, payroll_hash=adapter.source_hash)
        plan = build_plan(reviewed_draft, adapter)
        from app.excel.payslip_adapter import PayslipAdapter, configured_mapping
        slips = PayslipAdapter.read(adapter.path)
        all_ids = {employee.employee_id for employee in draft.employees if employee.employee_id}
        selected = set(payslip_employee_ids) if payslip_employee_ids is not None else all_ids
        if not selected or selected - all_ids:
            raise SafetyError('Invalid payslip employee selection')
        changes, expected = list(plan.writes), list(plan.expected)
        from app.excel.workbook_source import WorkbookSnapshot
        with WorkbookSnapshot.read(adapter.path).open() as (source_book, _):
            metadata_values = {(slip.sheet,address): source_book[slip.sheet][address].value for slip in slips.slips
                               for address in (slip.period_cell,slip.payment_date_cell)}
        for employee in draft.employees:
            if employee.employee_id in selected:
                slip = slips.employee(employee.name)
                delta, validations = slips.plan_employee(employee, adapter.employee(employee.name),
                    mapping=configured_mapping(self.service.repo, draft, employee, slip))
                changes.extend(delta)
                expected.extend(validations)
                # Period and payment date are taken from the selected month and
                # the workbook's own explicit payment-date label, not a pay-day rule.
                desired_metadata = [(slip.period_cell, draft.month), (slip.payment_date_cell, adapter.payment_date())]
                for address, wanted in desired_metadata:
                    if metadata_values[(slip.sheet,address)] != wanted:
                        changes.append(CellWrite(slip.sheet, address, wanted))
                    expected.append((slip.sheet, address, wanted))
        plan = replace(plan, writes=tuple(changes), expected=tuple(expected))
        result = self.execute(plan, run_id=run['id'])
        with self.service.repo.db.transaction() as con:
            current = con.execute('SELECT state,source_hash FROM payroll_runs WHERE id=?', (run['id'],)).fetchone()
            if current['state'] != PayrollState.CONFIRMED or current['source_hash'] != draft.source_hash:
                raise SafetyError('Month state changed during the write; finalization withheld')
            coverage_key = 'payslip_coverage:' + run['id']
            prior = self.service.repo.setting(coverage_key, {})
            covered = set(prior.get('employee_ids', [])) if prior.get('source_hash') == draft.source_hash and prior.get('revision') == run['revision'] else set()
            covered |= selected
            self.service.repo.set_setting(coverage_key, {'source_hash': draft.source_hash, 'revision': run['revision'], 'employee_ids': sorted(covered)})
            final_state = PayrollState.WRITTEN if covered >= all_ids else PayrollState.CONFIRMED
            con.execute('UPDATE payroll_runs SET state=?,payroll_hash=? WHERE id=?', (final_state, result['result_hash'], run['id']))
            con.execute('UPDATE monthly_payroll SET status=? WHERE run_id=?', (final_state, run['id']))
            con.execute('UPDATE write_operations SET status=?,result_hash=?,completed_at=? WHERE id=?',
                        ('VALIDATED' if final_state == PayrollState.WRITTEN else 'VALIDATED_PARTIAL', result['result_hash'], utc_now(), result['operation_id']))
            result['payslip_employee_ids'] = sorted(selected)
            result['month_state'] = final_state.value
            self.service.repo.audit(con, 'WORKBOOK_WRITTEN', year=year, month=month, new=result, actor=actor)
        return result
