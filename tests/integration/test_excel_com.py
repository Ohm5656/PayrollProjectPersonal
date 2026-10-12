from pathlib import Path

import pytest

from app.excel.excel_gateway import ExcelGateway, excel_processes, verify_existing_excel, FileInUse
from app.excel.payroll_writer import PayrollWriter, build_plan
from app.excel.workbook_source import file_hash
from app.excel.workbook_validator import WorkbookStructure, validate_expected
from app.safety import SafetyError
from tests.unit.test_writer_safety import controlled_draft, payroll_copy

pytestmark = pytest.mark.excel_com


def test_real_isolated_excel_write_reopen_and_preserve(payroll_copy):
    before_excel = excel_processes()
    before = WorkbookStructure.read(payroll_copy)
    source_hash = file_hash(payroll_copy)
    draft, adapter = controlled_draft(payroll_copy)
    writer = PayrollWriter()
    result = writer.execute(build_plan(draft, adapter))
    assert result['validated']
    assert result['excel_pid'] not in before_excel
    assert result['backup_hash'] == source_hash
    assert file_hash(Path(result['backup_path'])) == source_hash
    before.validate(WorkbookStructure.read(payroll_copy))
    validate_expected(payroll_copy, (('คิดค่าจ้าง ', 'P9', 1325),))
    verify_existing_excel(before_excel)


def test_real_post_commit_failure_restores_verified_backup(payroll_copy, monkeypatch):
    original = file_hash(payroll_copy)
    writer = PayrollWriter()
    draft, adapter = controlled_draft(payroll_copy)
    def fail(*args):
        raise SafetyError('Injected post-commit validation failure')
    monkeypatch.setattr(writer, 'post_commit_validate', fail)
    with pytest.raises(SafetyError, match='Injected'):
        writer.execute(build_plan(draft, adapter))
    assert file_hash(payroll_copy) == original


def test_open_unsaved_copy_is_deferred_without_save_or_close(payroll_copy):
    original = file_hash(payroll_copy)
    draft, adapter = controlled_draft(payroll_copy)
    writer = PayrollWriter()
    with ExcelGateway() as owner:
        with owner.open_copy(payroll_copy) as book:
            book.Worksheets('คิดค่าจ้าง ').Range('P9').Value2 = 777
            assert not bool(book.Saved)
            with pytest.raises(FileInUse):
                writer.execute(build_plan(draft, adapter))
            assert not bool(book.Saved)
            assert int(owner.app.Workbooks.Count) == 1
            assert book.Worksheets('คิดค่าจ้าง ').Range('P9').Value2 == 777
    assert file_hash(payroll_copy) == original
