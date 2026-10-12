from decimal import Decimal
import json

import pytest

from app.analysis.historical import LEAVE, render_report, write_reports
from app.excel.workbook_source import discover_workbooks, filename_month, safe_output_path


def test_discovers_all_18_copies(copied_reference):
    for kind in ('attendance', 'payroll'):
        files = discover_workbooks(copied_reference / kind)
        assert len(files) == 9
        assert {filename_month(p) for p in files} == set(range(1, 10))


def test_every_sheet_is_inspected(historical_data):
    data = historical_data
    assert data['read_only_verified']
    assert len(data['files']) == 18
    assert all(f['sheets'] and f['sha256'] for f in data['files'])
    assert all('formulas' in s and 'merged_ranges' in s and 'print_area' in s
               for f in data['files'] for s in f['sheets'])
    assert {f['month'] for f in data['files']} == set(range(1, 10))


def test_report_sections_and_serialization(historical_data, workbook_workspace, copied_reference):
    write_reports(historical_data, workbook_workspace, copied_reference)
    text = (workbook_workspace / 'historical_analysis.md').read_text(encoding='utf-8')
    for section in ('Identity evidence', 'Travel and allowance', 'bonus versus leave',
                    'special holidays', 'Recurring versus variable', 'Unknown business rules', 'OT evidence'):
        assert section in text
    evidence = json.loads((workbook_workspace / 'historical_analysis.json').read_text(encoding='utf-8'))
    assert len(evidence['files']) == 18
    assert 'เลขที่บ/ช' not in json.dumps(evidence, ensure_ascii=False)


def test_output_to_reference_is_rejected(copied_reference):
    with pytest.raises(ValueError, match='read-only'):
        safe_output_path(copied_reference / 'report.md', copied_reference)


def test_output_never_writes_workbooks(workbook_workspace, copied_reference):
    with pytest.raises(ValueError, match='never write XLSX'):
        safe_output_path(workbook_workspace / 'test.xlsx', copied_reference)


@pytest.mark.parametrize('text', ['สงขลา', 'ลาดหลุมแก้ว', 'เวลาเข้า', 'รอรางกับสายไฟ'])
def test_leave_not_in_place_or_time_words(text):
    assert not LEAVE.search(text)


def test_late_does_not_universally_remove_bonus(historical_data):
    counterexamples = [c for c in historical_data['comparisons']
                      if c['mapping'] == 'EXACT_FULL_NAME' and c['late_dates']
                      and (c['recorded_bonus'] or 0) > 0]
    assert counterexamples, 'Historical evidence contradicts late => zero bonus'


def test_identity_conflict_is_not_fuzzy_matched(historical_data):
    c = next(c for c in historical_data['comparisons'] if c['month'] == 8 and c['sheet'] == 'อดิศักดิ์')
    assert c['attendance_name'] == 'บรรจง มูลที'
    assert c['name_conflict'] and c['duplicate_identity']
    assert c['mapping'] == 'REVIEW_REQUIRED'
    assert c['payroll_travel'] is None


def test_all_months_have_comparisons(historical_data):
    assert {c['month'] for c in historical_data['comparisons']} == set(range(1, 10))
    assert any(c['travel_difference'] not in (None, Decimal(0)) or c['allowance_difference'] not in (None, Decimal(0))
               for c in historical_data['comparisons'] if c['mapping'] == 'EXACT_FULL_NAME')


def test_stale_template_dates_are_not_current_attendance(historical_data):
    for f in historical_data['files']:
        if f['kind'] != 'attendance':
            continue
        blank = next(a for a in f['attendance'] if a['sheet'] == '-')
        assert not blank['records']
        assert blank['other_periods'] == {'2021-10': 31}


def test_payroll_layout_variants_are_mapped_by_headers(historical_data):
    payrolls = {f['month']: f['payroll'] for f in historical_data['files'] if f['kind'] == 'payroll'}
    assert all(not p['template_issues'] for p in payrolls.values())
    assert payrolls[1]['net_income_header'] == ['AD5']
    assert payrolls[3]['net_income_header'] == ['AB5']
    assert payrolls[8]['net_income_header'] == ['AA5']
    assert [payrolls[m]['field_columns']['housing'] for m in (1, 3, 8)] == [23, 22, 21]
    assert payrolls[3]['field_columns']['special_bonus'] == 19
