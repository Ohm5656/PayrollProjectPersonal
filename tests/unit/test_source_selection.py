import shutil
import pytest

from app.db.database import Database
from app.db.repositories import Repository
from app.excel.workbook_source import file_hash
from app.services.payroll_service import PayrollService,PayrollStateError
from app.ui.main_window import MainWindow
from tests.unit.test_draft_engine import draft_case,calculate
from tests.unit.test_ui import qt_app


def test_identical_new_copy_pair_is_not_a_cached_old_destination(copied_reference,workbook_workspace):
    service=PayrollService(Repository(Database(workbook_workspace/'selection.db')))
    first=[]
    second=[]
    for kind in ('attendance','payroll'):
        source=next((copied_reference/kind).glob('* 8.xlsx'))
        for collection,folder in [(first,'first'),(second,'second')]:
            target=workbook_workspace/folder/kind/source.name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source,target)
            collection.append(target)
    one=service.prepare(*first)
    two=service.prepare(*second)
    assert not two['unchanged']
    assert two['draft'].payroll_path==str(second[1].resolve())
    assert one['draft'].payroll_path!=two['draft'].payroll_path
    # Fixture state isolates the protected-pair guard, which must precede
    # cached evidence reuse even when the workbook bytes are identical.
    with service.repo.db.transaction() as con:
        con.execute("UPDATE payroll_runs SET state='CONFIRMED' WHERE year=2026 AND month=8")
    before=file_hash(first[1])
    with pytest.raises(PayrollStateError,match='สำเนาคู่อื่น'):
        service.prepare(*first)
    assert file_hash(first[1])==before


def test_browsing_a_new_copy_clears_loaded_draft_and_write_gate(qt_app,draft_case,workbook_workspace,monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    window=MainWindow(PayrollService(draft_case[0]))
    window.show_result({'run':{'state':'READY','revision':1},'draft':calculate(draft_case)})
    target=workbook_workspace/'new-copy.xlsx'
    target.touch()
    monkeypatch.setattr(QFileDialog,'getOpenFileName',lambda *args:(str(target),'Excel'))
    window.choose_file('payroll')
    assert window.draft is None and window.run is None
    assert window.table.rowCount()==0
    assert not window.confirm_button.isEnabled() and not window.write_button.isEnabled()
    window.close()


def test_cancel_reopen_after_changing_copies_never_restores_old_write_target(qt_app,draft_case,monkeypatch):
    from PySide6.QtWidgets import QDialog
    service=PayrollService(draft_case[0])
    draft=calculate(draft_case)
    monkeypatch.setattr(service,'current',lambda year,month:({'state':'CONFIRMED','id':'fixture-run'},draft))
    monkeypatch.setattr(QDialog,'exec',lambda dialog:QDialog.Rejected)
    monkeypatch.setattr(service,'reopen',lambda *args,**kwargs:pytest.fail('Cancelled reopen must not mutate the month'))
    window=MainWindow(service)
    window.payroll.setText('new selected copy')
    window.reopen()
    assert window.run is None and window.draft is None
    assert not window.write_button.isEnabled()
    window.close()


def test_hard_link_target_is_rejected_before_any_excel_write(workbook_workspace):
    import os
    from app.excel.payroll_writer import PayrollWriter,WritePlan
    from app.safety import SafetyError
    original=workbook_workspace/'independent.xlsx'
    original.write_bytes(b'controlled copy source')
    linked=workbook_workspace/'linked.xlsx'
    os.link(original,linked)
    def forbidden():pytest.fail('Unsafe link must be rejected before COM')
    with pytest.raises(SafetyError,match='hard links'):
        PayrollWriter(gateway_factory=forbidden).execute(WritePlan(linked,file_hash(linked),(),(),2026,8))
    assert original.read_bytes()==b'controlled copy source'
