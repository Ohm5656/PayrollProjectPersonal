from decimal import Decimal
from pathlib import Path
import json
import shutil
import pytest

from app.db.database import Database
from app.db.repositories import Repository
from app.domain import PayrollState
from app.domain import issue_key, encode
from app.excel.excel_gateway import ExcelGateway, excel_processes, verify_existing_excel
from app.excel.payroll_writer import PayrollWriter
from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.excel.workbook_source import file_hash
from app.excel.workbook_validator import WorkbookStructure, validate_expected
from app.services.payroll_service import PayrollService
from tests.integration.review_fixture import approve_month8


def copied_month8(copied_reference, workbook_workspace):
    paths = []
    for kind in ('attendance', 'payroll'):
        source = next((copied_reference/kind).glob('* 8.xlsx'))
        target = workbook_workspace/kind/source.name
        target.parent.mkdir()
        shutil.copy2(source, target)
        paths.append(target)
    return paths


def test_human_review_fixture_reaches_ready_with_real_month8(copied_reference, workbook_workspace):
    attendance, payroll = copied_month8(copied_reference, workbook_workspace)
    service = PayrollService(Repository(Database(workbook_workspace/'pipeline.db')))
    result = approve_month8(service, attendance, payroll)
    assert result['draft'].state == PayrollState.READY
    service.confirm(2026, 8, actor='TEST FIXTURE')
    assert service.current(2026, 8)[0]['state'] == PayrollState.CONFIRMED
    before=file_hash(payroll)
    from zipfile import ZipFile
    with ZipFile(attendance,'a') as book: book.comment=b'controlled post-confirmation source save'
    changed=service.prepare(attendance,payroll,year=2026,month=8)
    assert changed['protected'] and changed['difference']['message']=='พบการแก้ไขบันทึกเวลาหลังยืนยันเงินเดือน'
    assert service.current(2026,8)[0]['state']==PayrollState.CONFIRMED
    assert file_hash(payroll)==before


@pytest.mark.excel_com
def test_full_month8_pipeline_partial_all_idempotency_change_and_lock(copied_reference, workbook_workspace):
    attendance, payroll = copied_month8(copied_reference, workbook_workspace)
    before_excel = excel_processes()
    service = PayrollService(Repository(Database(workbook_workspace/'pipeline.db')))
    approved = approve_month8(service, attendance, payroll)['draft']
    structure = WorkbookStructure.read(payroll)
    service.confirm(2026, 8, actor='TEST FIXTURE')
    writer = PayrollWriter(service)
    first_id = approved.employees[0].employee_id
    first = writer.write_month(2026, 8, actor='TEST FIXTURE', payslip_employee_ids=[first_id])
    assert first['validated'] and first['month_state'] == PayrollState.CONFIRMED
    result = writer.write_month(2026, 8, actor='TEST FIXTURE')
    assert result['month_state'] == PayrollState.WRITTEN
    structure.validate(WorkbookStructure.read(payroll))
    saved = file_hash(payroll)
    assert writer.write_month(2026, 8)['unchanged']
    assert file_hash(payroll) == saved
    original = PayrollWorkbookAdapter.read(payroll)
    person = original.employees[0]
    old_travel = person.cells['travel'].value
    # Only a copied attendance cell is saved through our own isolated Excel.
    with ExcelGateway() as gateway:
        with gateway.open_copy(attendance) as book:
            cell = book.Worksheets('ดนุกานต์').Range('J3')
            cell.Value2 = float(Decimal(str(cell.Value2 or 0)) + 25)
            gateway.app.CalculateFull()
            book.Save()
            cell = None
    changed_hash = file_hash(attendance)
    for state in (PayrollState.WRITTEN, PayrollState.LOCKED):
        if state == PayrollState.LOCKED: service.lock(2026, 8, actor='TEST FIXTURE')
        changed = service.prepare(attendance, payroll, year=2026, month=8)
        assert changed['protected'] and changed['difference']['new_hash'] == changed_hash
        assert service.current(2026, 8)[0]['state'] == state
        assert file_hash(payroll) == saved
        changes = changed['difference']['fields']
        assert any(c['field'] == 'travel' and c['source_difference'] == '25' for c in json.loads(encode(changes)))
    service.reopen(2026, 8, reason='TEST ONLY: inspect delta and explicitly reopen', actor='TEST FIXTURE')
    revised = approve_month8(service, attendance, payroll)['draft']
    service.confirm(2026, 8, actor='TEST FIXTURE')
    assert writer.write_month(2026, 8)['validated']
    refreshed = PayrollWorkbookAdapter.read(payroll)
    assert refreshed.employee(person.name).cells['travel'].value == old_travel + 25
    # Independent fields remain unchanged; gross/net change only by the same
    # source travel delta, through the workbook's existing formulas.
    for employee in original.employees:
        for field, cell in employee.cells.items():
            value = refreshed.employee(employee.name).cells[field].value
            expected = cell.value + 25 if employee.name == person.name and field in {'travel','income','net'} else cell.value
            assert value == expected, (employee.name, field, value, expected)
    structure.validate(WorkbookStructure.read(payroll))
    assert writer.write_month(2026, 8)['unchanged']
    verify_existing_excel(before_excel)
    assert service.repo.db.query("SELECT * FROM audit_log WHERE action='REVIEW_DECISION'")
    assert len(service.repo.db.query('SELECT * FROM source_changes')) == 1


@pytest.mark.excel_com
def test_first_safe_copy_test_writes_one_employee_before_month_confirmation(copied_reference,workbook_workspace):
    attendance,payroll=copied_month8(copied_reference,workbook_workspace)
    service=PayrollService(Repository(Database(workbook_workspace/'single.db')))
    draft=approve_month8(service,attendance,payroll)['draft']
    employee,other=draft.employees[:2]
    # Leave another employee's advance pending: single testing must not require
    # or confirm an entire payroll month.
    with service.repo.db.transaction() as con:
        con.execute('DELETE FROM review_decisions WHERE source_hash=? AND issue_key=?',
                    (draft.source_hash,issue_key('FIELD',other.employee_id,'advance')))
    desired=employee.values['travel'].final_value+Decimal(25)
    service.repo.decide(draft.source_hash,issue_key('FIELD',employee.employee_id,'travel'),{'value':str(desired)},
                        reason='TEST ONLY: controlled single employee +25 travel',actor='TEST FIXTURE')
    result=service.prepare(attendance,payroll,force=True,year=2026,month=8)
    assert result['draft'].state==PayrollState.NEEDS_REVIEW
    from app.excel.workbook_source import WorkbookSnapshot
    with WorkbookSnapshot.read(payroll).open() as (book,_):
        before={(s.title,c.coordinate):c.value for s in book for row in s for c in row if c.data_type!='f'}
    writer=PayrollWriter(service)
    saved=writer.write_employee_copy(2026,8,employee.employee_id,reason='ทดสอบสำเนาเฉพาะคนเดียว',actor='TEST FIXTURE')
    assert saved['validated']
    assert service.current(2026,8)[0]['state']==PayrollState.NEEDS_REVIEW
    assert PayrollWorkbookAdapter.read(payroll).employee(employee.name).cells['travel'].value==desired
    from app.excel.payslip_adapter import PayslipAdapter
    slip=PayslipAdapter.read(payroll).employee(employee.name)
    allowed={(slip.sheet,c.address) for c in slip.slots}|{(slip.sheet,c.label_address) for c in slip.slots}
    allowed|={(slip.sheet,slip.period_cell),(slip.sheet,slip.payment_date_cell)}
    person=PayrollWorkbookAdapter.read(payroll).employee(employee.name)
    allowed|={('คิดค่าจ้าง ',c.coordinate) for c in person.cells.values()}
    with WorkbookSnapshot.read(payroll).open() as (book,_):
        for (sheet,address),value in before.items():
            if (sheet,address) not in allowed: assert book[sheet][address].value==value,(sheet,address)
    assert service.repo.db.query("SELECT * FROM audit_log WHERE action='SINGLE_EMPLOYEE_COPY_TEST'")
