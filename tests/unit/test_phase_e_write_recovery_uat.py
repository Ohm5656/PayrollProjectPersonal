from pathlib import Path

import pytest
from openpyxl import load_workbook

from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.excel.payroll_writer import PayrollWriter, build_plan
from app.excel.workbook_source import file_hash
from app.safety import SafetyError
from app.services.payroll_service import PayrollStateError
from tests.phase_e_fixtures import create_synthetic_excel_fixture, uat_root
from tests.unit.test_phase_e_calculation_uat import _service_with_configured_synthetic_inputs


class FailsBeforeOpeningExcel:
    """A gateway substitute: proves the pre-COM backup path without Excel."""
    def __enter__(self):
        raise RuntimeError("synthetic Excel gateway unavailable")

    def __exit__(self, *unused):
        return False


def _confirmed_synthetic_service(label):
    fixture, repo, service, _ = _service_with_configured_synthetic_inputs(label)
    prepared = service.prepare(fixture["attendance"], fixture["payroll"], force=True, year=2026, month=9)
    service.confirm(2026, 9, actor="phase-e-uAT", expected_revision=prepared["run"]["revision"])
    return fixture, repo, service, prepared["draft"]


def test_phase_e_generated_payslips_and_write_plan_are_preflighted_without_excel():
    fixture, _, _, draft = _confirmed_synthetic_service("write_preflight")
    payroll = PayrollWorkbookAdapter.read(fixture["payroll"])
    plan = build_plan(draft, payroll)
    assert plan.target == fixture["payroll"]
    assert plan.writes
    assert all(write.sheet == payroll.sheet_name for write in plan.writes)
    assert all(Path(plan.target).resolve().is_relative_to(fixture["root"]) for _ in plan.writes)


def test_phase_e_simulated_excel_failure_keeps_generated_payroll_and_verified_backup():
    fixture, _, _, draft = _confirmed_synthetic_service("backup_failure")
    payroll = PayrollWorkbookAdapter.read(fixture["payroll"])
    plan = build_plan(draft, payroll)
    original_hash = file_hash(fixture["payroll"])
    with pytest.raises(RuntimeError, match="synthetic Excel gateway unavailable"):
        PayrollWriter(backup_root=fixture["root"] / "backups", gateway_factory=FailsBeforeOpeningExcel).execute(plan)

    backups = list((fixture["root"] / "backups").rglob("*.xlsx"))
    assert len(backups) == 1
    assert file_hash(backups[0]) == original_hash
    assert file_hash(fixture["payroll"]) == original_hash
    staged = list((fixture["payroll"].parent / "_staging").rglob("*.xlsx"))
    assert len(staged) == 1
    assert file_hash(staged[0]) == original_hash
    assert staged[0].resolve().is_relative_to(fixture["root"])


def test_phase_e_changed_generated_destination_is_blocked_before_write():
    fixture, _, _, draft = _confirmed_synthetic_service("changed_destination")
    book = load_workbook(fixture["payroll"])
    try:
        book["คิดค่าจ้าง"]["N7"] = 301
        book.save(fixture["payroll"])
    finally:
        book.close()
    with pytest.raises(SafetyError, match="destination changed"):
        build_plan(draft, PayrollWorkbookAdapter.read(fixture["payroll"]))


def test_phase_e_write_cannot_skip_confirmation():
    fixture, _, service, draft = _service_with_configured_synthetic_inputs("confirm_gate")[:4]
    prepared = service.prepare(fixture["attendance"], fixture["payroll"], force=True, year=2026, month=9)
    with pytest.raises(SafetyError, match="Payroll must be confirmed"):
        PayrollWriter(service).write_month(2026, 9)
    with pytest.raises(PayrollStateError):
        service.confirm(2026, 9, expected_revision=prepared["run"]["revision"] + 1)


def test_phase_e_single_employee_copy_requires_an_explicit_reason():
    fixture, _, service, _ = _confirmed_synthetic_service("single_copy_reason")
    _, draft = service.current(2026, 9)
    with pytest.raises(SafetyError, match="ระบุเหตุผล"):
        PayrollWriter(service).write_employee_copy(2026, 9, draft.employees[0].employee_id, reason="")
