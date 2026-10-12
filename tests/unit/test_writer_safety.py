from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import shutil

import pytest

from app.domain import EmployeeDraft, PayrollDraft, PayrollValue, ValueCategory
from app.excel.formulas import FormulaUnsupported, arithmetic
from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.excel.payroll_writer import CellWrite, PayrollWriter, WritePlan, build_plan
from app.excel.workbook_source import file_hash
from app.excel.workbook_validator import WorkbookStructure
from app.safety import SafetyError, development_target
from app.services.backup_service import BackupService


def controlled_draft(path, new_travel=Decimal(1325)):
    adapter = PayrollWorkbookAdapter.read(path)
    person = adapter.employees[0]
    value = PayrollValue('travel', ValueCategory.AUTO_CALCULATED, person.cells['travel'].value,
        None, new_travel, None, new_travel, 'Explicit controlled copy test', 'test source', True)
    employee = EmployeeDraft('test-id', 'test-id', person.name, 'test', {'travel': value}, ())
    return PayrollDraft(2026, 8, 'test source', 'source hash', str(adapter.path), adapter.source_hash, (employee,)), adapter


@pytest.fixture
def payroll_copy(copied_reference, workbook_workspace):
    source = next((copied_reference / 'payroll').glob('* 8.xlsx'))
    destination = workbook_workspace / source.name
    shutil.copy2(source, destination)
    return destination


def test_write_to_original_always_rejected_before_com():
    from app.safety import REFERENCE_ROOT
    path = next((REFERENCE_ROOT / 'payroll').glob('* 8.xlsx'))
    with pytest.raises(SafetyError, match='test_workspace'):
        PayrollWriter().execute(WritePlan(path, 'hash', (), (), 2026, 8))


def test_plan_uses_exact_sheet_and_validated_field(payroll_copy):
    draft, adapter = controlled_draft(payroll_copy)
    plan = build_plan(draft, adapter)
    assert plan.writes == (CellWrite('คิดค่าจ้าง ', 'P9', Decimal(1325)),)
    assert plan.expected == (('คิดค่าจ้าง ', 'P9', Decimal(1325)),)


def test_plan_cannot_override_salary_formula(payroll_copy):
    draft, adapter = controlled_draft(payroll_copy)
    employee = draft.employees[0]
    salary = replace(employee.values['travel'], field='base', final_value=Decimal(99999))
    draft = replace(draft, employees=(replace(employee, values={'base': salary}),))
    with pytest.raises(SafetyError, match='protected formula'):
        build_plan(draft, adapter)


def test_backup_is_hash_verified_before_excel_attempt(payroll_copy):
    original = file_hash(payroll_copy)
    class FailsBeforeOpening:
        def __enter__(self):
            raise RuntimeError('Simulated unavailable Excel')
        def __exit__(self, *args):
            pass
    draft, adapter = controlled_draft(payroll_copy)
    writer = PayrollWriter(gateway_factory=FailsBeforeOpening)
    with pytest.raises(RuntimeError, match='Simulated'):
        writer.execute(build_plan(draft, adapter))
    backups = list((payroll_copy.parent / 'backups').rglob('*.xlsx'))
    assert len(backups) == 1 and file_hash(backups[0]) == original
    assert file_hash(payroll_copy) == original


def test_invalid_backup_source_aborts_without_artifact(workbook_workspace):
    with pytest.raises(Exception):
        BackupService(workbook_workspace / 'backups').create(workbook_workspace / 'x.xlsx', b'invalid', 2026, 8)
    assert not list((workbook_workspace / 'backups').rglob('*.xlsx'))


def test_structure_detects_formula_and_format_changes_on_copy(payroll_copy):
    from openpyxl import load_workbook
    from copy import copy
    baseline = WorkbookStructure.read(payroll_copy)
    book = load_workbook(payroll_copy)
    book['คิดค่าจ้าง ']['H9'] = '=F9*G9+1'
    book.save(development_target(payroll_copy))
    book.close()
    with pytest.raises(SafetyError, match='formulas changed'):
        baseline.validate(WorkbookStructure.read(payroll_copy))


@pytest.mark.parametrize('formula', ['=SUM(A1:A2)', '=__import__(1)', '=[other.xlsx]Sheet1!A1', '=A1**2'])
def test_unconfirmed_formula_language_is_not_executed(formula):
    with pytest.raises(FormulaUnsupported):
        arithmetic(formula, lambda address: Decimal(1))


def test_existing_arithmetic_preview_not_new_business_rule():
    assert arithmetic('=18200+200+500+460', lambda a: None) == Decimal(19360)
    assert arithmetic('=D9/30/8*1.5', lambda a: Decimal(19360)) == Decimal(121)
    assert arithmetic('=+D22', lambda a: Decimal(80000)) == Decimal(80000)


def test_atomic_replacement_holds_reservation_and_preserves_backup_bytes(payroll_copy):
    from app.excel.atomic_file import atomic_replace
    from app.excel.excel_gateway import reserved_copy
    staged = payroll_copy.parent / 'staged.xlsx'
    original = payroll_copy.read_bytes()
    staged.write_bytes(original)
    with reserved_copy(payroll_copy) as content:
        assert content == original
        atomic_replace(staged, payroll_copy)
    assert payroll_copy.read_bytes() == original
