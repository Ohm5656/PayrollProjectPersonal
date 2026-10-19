"""Native Windows Excel tests. They skip rather than attach to user Excel."""
from functools import partial
from pathlib import Path

import pytest

from app.domain import PayrollState
from app.excel.excel_gateway import ExcelGateway, ExcelUnavailable, excel_processes
from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.excel.payroll_writer import PayrollWriter
from app.excel.workbook_source import file_hash
from app.excel.workbook_validator import WorkbookStructure
from tests.phase_e_fixtures import uat_root
from tests.unit.test_phase_e_calculation_uat import _service_with_configured_synthetic_inputs
from tests.unit.test_phase_e_write_recovery_uat import _confirmed_synthetic_service


def _native_gateway(root):
    if excel_processes():
        pytest.skip("Native COM test refused: a user-owned Excel process is already running")
    return partial(ExcelGateway, lifecycle_root=root / "logs"), root / "logs" / "events.jsonl"


def _cells(adapter, row):
    return {field: cell.value for field, cell in adapter.employees[row].cells.items()}


def _input_cells(adapter, row):
    return {field: cell.value for field, cell in adapter.employees[row].cells.items() if not cell.formula}


def test_phase_e6_real_single_employee_copy_uses_owned_excel_only():
    fixture, repo, service, _ = _service_with_configured_synthetic_inputs("e6_single_native")
    prepared = service.prepare(fixture["attendance"], fixture["payroll"], force=True, year=2026, month=9)
    draft = prepared["draft"]
    factory, lifecycle = _native_gateway(fixture["root"])
    before_hash = file_hash(fixture["payroll"])
    before_structure = WorkbookStructure.read(fixture["payroll"])
    before = PayrollWorkbookAdapter.read(fixture["payroll"])
    other_before = _input_cells(before, 1)
    employee_id = draft.employees[0].employee_id

    result = PayrollWriter(service, backup_root=fixture["root"] / "backups", gateway_factory=factory).write_employee_copy(
        2026, 9, employee_id, reason="Phase E.6 native synthetic single-employee test", actor="phase-e6",
    )
    after = PayrollWorkbookAdapter.read(fixture["payroll"])
    before_structure.validate(WorkbookStructure.read(fixture["payroll"]))
    assert result["validated"] and result["writes"] > 0
    assert result["target"] == str(fixture["payroll"])
    assert result["backup_hash"] == before_hash
    assert file_hash(Path(result["backup_path"])) == before_hash
    assert after.employees[0].cells["income"].value == 33100
    assert after.employees[0].cells["net"].value == 32200
    assert _input_cells(after, 1) == other_before
    assert after.employees[1].cells["income"].value == 34700
    assert lifecycle.is_file()
    assert {event for event in lifecycle.read_text(encoding="utf-8").splitlines() if event}
    assert repo.db.query("SELECT * FROM write_operations WHERE status='VALIDATED_SINGLE'")
    assert service.current(2026, 9)[0]["state"] in {PayrollState.DRAFT, PayrollState.READY}
    assert not excel_processes()


def test_phase_e6_real_month_write_recalculates_and_preserves_structure():
    fixture, repo, service, _ = _confirmed_synthetic_service("e6_month_native")
    factory, lifecycle = _native_gateway(fixture["root"])
    before_hash = file_hash(fixture["payroll"])
    before_structure = WorkbookStructure.read(fixture["payroll"])

    result = PayrollWriter(service, backup_root=fixture["root"] / "backups", gateway_factory=factory).write_month(2026, 9, actor="phase-e6")
    after = PayrollWorkbookAdapter.read(fixture["payroll"])
    before_structure.validate(WorkbookStructure.read(fixture["payroll"]))
    assert result["validated"] and result["month_state"] == PayrollState.WRITTEN
    assert result["backup_hash"] == before_hash
    assert file_hash(Path(result["backup_path"])) == before_hash
    assert all(person.cells["income"].value == 33100 and person.cells["net"].value == 32200 for person in after.employees)
    assert lifecycle.is_file()
    assert repo.run(2026, 9)["state"] == PayrollState.WRITTEN
    assert repo.audit_history(limit=1)[0]["action"] == "WORKBOOK_WRITTEN"
    assert not excel_processes()


def test_phase_e6_native_gateway_is_explicitly_unavailable_or_isolated():
    if excel_processes():
        pytest.skip("Native COM readiness refused: a user-owned Excel process is already running")
    try:
        with ExcelGateway(lifecycle_root=uat_root("e6_com_readiness") / "logs") as gateway:
            assert gateway.isolated and gateway.version and gateway.pid
    except ExcelUnavailable as exc:
        pytest.skip(f"Native Excel COM unavailable: {exc}")
    assert not excel_processes()
