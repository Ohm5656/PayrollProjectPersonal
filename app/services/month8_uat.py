"""Copies-only Month 8 UAT preparation and read-only comparison evidence."""
from datetime import datetime
from pathlib import Path
from shutil import copy2, move

from app.excel.payroll_reader import PayrollWorkbookAdapter
from app.domain import THAI_FIELDS
from app.safety import ROOT, REFERENCE_ROOT, TEST_ROOT, SafetyError, record_baseline
from app.services.monthly_workflow import master_template_path, verify_monthly_copy

UAT_ROOT = TEST_ROOT / 'uat_month8'


def _reference(kind, month=8):
    candidates = list((REFERENCE_ROOT / kind).glob(f'* {month}.xlsx'))
    if len(candidates) != 1:
        raise SafetyError(f'Month {month} {kind} source is missing or ambiguous')
    return candidates[0]


def prepare_month8_uat(workflow, *, root=UAT_ROOT):
    """Archive prior UAT data then prepare one safe attendance copy.

    This is intentionally unable to target any folder outside test_workspace.
    """
    root = Path(root)
    if TEST_ROOT.resolve() not in root.resolve().parents:
        raise SafetyError('UAT workspace must remain inside test_workspace')
    baseline = record_baseline(ROOT / 'reports' / 'source_hash_baseline.json')
    attendance_source, historical = _reference('attendance'), _reference('payroll')
    template = master_template_path()
    archive = None
    if root.exists() and any(root.iterdir()):
        archive_root = root / 'archive'; archive_root.mkdir(exist_ok=True)
        archive = archive_root / datetime.now().strftime('%Y-%m-%d_%H%M%S_%f')
        archive.mkdir()
        for item in list(root.iterdir()):
            if item.name != 'archive':
                move(str(item), str(archive / item.name))
    attendance, output = root / 'attendance', root / 'payroll_output'
    for folder in (attendance, output, root / 'backups', root / 'logs'):
        folder.mkdir(parents=True, exist_ok=True)
    copied = attendance / attendance_source.name
    copy2(attendance_source, copied)
    workflow.configure(attendance, output, template)
    config = {**workflow.configuration(), 'mode': 'UAT_MONTH8', 'uat_root': str(root),
              'historical_month8': str(historical)}
    workflow.repo.set_setting('workflow_configuration', config)
    return {'root': root, 'attendance': copied, 'payroll_output': output,
            'template': template, 'historical': historical, 'archive': archive,
            'baseline_files': len(baseline['files'])}


def month8_comparison(generated, historical=None):
    """Read two payroll workbooks and publish only stable label-based comparisons."""
    historical = Path(historical or _reference('payroll'))
    generated = Path(generated)
    current, prior = PayrollWorkbookAdapter.read(generated), PayrollWorkbookAdapter.read(historical)
    fields = ('base', 'normal_ot', 'holiday_days', 'holiday_ot', 'bonus', 'travel', 'allowance',
              'phone', 'position', 'housing', 'income', 'net')
    lines = ['# Month 8 UAT comparison', '',
             f'Generated UAT workbook: `{generated}`', f'Historical reference (read-only): `{historical}`', '',
             'This comparison is evidence for review. A difference is not automatically a software defect.', '']
    prior_people = {p.name: p for p in prior.employees}
    for employee in current.employees:
        lines += [f'## {employee.name}', '']
        reference = prior_people.get(employee.name)
        if not reference:
            lines += ['Status: **IDENTITY_CONFLICT** — no exact historical payroll identity.', '']
            continue
        lines += ['| รายการ | ระบบ UAT | ประวัติเดือน 8 | สถานะ |', '| --- | ---: | ---: | --- |']
        for field in fields:
            now, old = employee.cells.get(field), reference.cells.get(field)
            if not now or not old: continue
            status = 'MATCH' if now.value == old.value else 'USER_REVIEW_REQUIRED'
            lines.append(f'| {THAI_FIELDS.get(field, field)} | {now.value if now.value is not None else "รอยืนยัน"} | {old.value if old.value is not None else "—"} | {status} |')
        lines.append('')
    report = ROOT / 'reports' / 'month8_uat_comparison.md'
    report.write_text('\n'.join(lines), encoding='utf-8')
    return report
