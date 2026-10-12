from datetime import date, datetime, time
from decimal import Decimal

import pytest

from app.excel.attendance_reader import read_attendance
from app.excel.workbook_source import WorkbookReadError
from app.models import Severity
from app.payroll.attendance_rules import detect_events


def employee(book, sheet='ดนุกานต์'):
    return next(e for e in book.employees if e.sheet_name == sheet)


def edited_first(edit, change):
    return employee(read_attendance(edit(change), year=2026, month=8))


@pytest.mark.parametrize('month', range(1, 10))
def test_all_months_against_independent_raw_analysis(month, parsed_history, historical_data):
    parsed = parsed_history[month]
    observed = next(f for f in historical_data['files'] if f['kind'] == 'attendance' and f['month'] == month)
    assert (parsed.year, parsed.month) == (2026, month)
    assert [e.sheet_name for e in parsed.employees] == [a['sheet'] for a in observed['attendance']]
    for record in observed['attendance']:
        e = employee(parsed, record['sheet'])
        assert e.full_name == record['full_name']
        assert len(e.days) == len(record['records'])
        for field in ('ot', 'allowance', 'travel'):
            assert e.totals[field].numeric_subtotal == record['numeric_sums'][field]
        assert [day.date.isoformat() for day in e.days] == [r['date'] for r in record['records']]
        assert e.employee_id is None  # Never use a sheet name as the stable employee ID.


def test_blank_template_is_quarantined(parsed_history):
    for parsed in parsed_history.values():
        e = employee(parsed, '-')
        assert not e.days
        assert len(e.rejected_rows) == 31
        assert {'UNKNOWN_EMPLOYEE', 'OUT_OF_PERIOD', 'NO_CURRENT_DAYS'} <= {i.code for i in e.issues}
        assert e.requires_review and e.totals['travel'].source_sum is None


def test_stale_named_sheet_is_not_zero_pay(parsed_history):
    e = employee(parsed_history[8], '--')
    assert e.full_name == 'อดิศักดิ์  สาคำตา'
    assert not e.days and e.requires_review
    assert e.totals['allowance'].source_sum is None
    assert e.attendance_bonus is None


def test_month8_conflicting_and_duplicate_names(parsed_history):
    book = parsed_history[8]
    wrong = employee(book, 'อดิศักดิ์')
    assert wrong.full_name == 'บรรจง มูลที'
    assert {'IDENTITY_CONFLICT', 'DUPLICATE_EMPLOYEE_LABEL'} <= {i.code for i in wrong.issues}
    assert 'DUPLICATE_EMPLOYEE_LABEL' in {i.code for i in employee(book, 'บรรจง').issues}
    assert wrong.employee_id is None


def test_first_name_only_requires_alias(parsed_history):
    e = employee(parsed_history[9], 'ภานุวัฒน์')
    assert 'INCOMPLETE_EMPLOYEE_NAME' in {i.code for i in e.issues}
    assert e.requires_review


def test_raw_clocks_and_amounts_preserved(parsed_history):
    first = employee(parsed_history[8]).days[0]
    assert first.date == date(2026, 8, 1)
    assert first.clock_in == time(8) and first.clock_out == time(17)
    assert first.check_in == time(7, 24)
    assert first.allowance.raw == 150 and first.allowance.number == Decimal('150')
    assert first.travel.coordinate == 'J3'


@pytest.mark.parametrize('text,hours,days', [
    ('ลา', None, None), ('Office   ลา 3 ชั่วโมง', Decimal(3), None),
    ('OFFICE + ลา 1/2 วัน', None, Decimal('0.5')), ('ลา 2 วัน', None, Decimal(2)),
])
def test_leave_keeps_duration_without_consequences(text, hours, days):
    events = detect_events(date(2026, 9, 1), 'employee', {'D3': text})
    leave = next(e for e in events if e.event_type == 'LEAVE')
    assert (leave.hours, leave.days) == (hours, days)
    assert leave.suggested_type == 'UNKNOWN_LEAVE'
    assert leave.requires_review and leave.affects_attendance_bonus is None


@pytest.mark.parametrize('text', ['เวลาเข้า', 'สงขลา', 'CP RAM ลาดหลุมแก้ว', 'รอรางกับสายไฟ'])
def test_place_names_are_not_leave(text):
    assert not any(e.event_type == 'LEAVE' for e in detect_events(date(2026, 8, 1), 'e', {'D3': text}))


@pytest.mark.parametrize('text,kind', [
    ('หยุดแทนวันอาทิตย์ที่ 6/9/2569', 'SUBSTITUTE_HOLIDAY'),
    ('หยุดน้ำท่วม', 'EMERGENCY_CLOSURE'), ('หยุดวันแม่แห่งชาติ', 'PUBLIC_HOLIDAY'),
    ('หยุดเทศกาลสงกรานต์', 'COMPANY_SPECIAL_HOLIDAY'), ('หยุดฉุกเฉินใหม่', 'UNKNOWN'),
])
def test_holidays_are_suggestions_not_policy(text, kind):
    event = next(e for e in detect_events(date(2026, 9, 7), 'e', {'D3': text}) if e.event_type == 'HOLIDAY_SUGGESTION')
    assert event.suggested_type == kind and event.requires_review
    assert event.affects_attendance_bonus is None


def test_real_emergency_and_substitute_events(parsed_history):
    events = [e for sheet in parsed_history[9].employees for day in sheet.days for e in day.events]
    assert any(e.suggested_type == 'EMERGENCY_CLOSURE' for e in events)
    assert any(e.suggested_type == 'SUBSTITUTE_HOLIDAY' for e in events)


def test_late_and_allowance_notes_do_not_decide_attendance_bonus(parsed_history):
    sheet = employee(parsed_history[8], 'วัชระ')
    late = [e for d in sheet.days for e in d.events if e.event_type == 'LATE_CHECK_IN']
    assert late and sheet.attendance_bonus is None
    assert all(e.affects_attendance_bonus is None for e in late)
    events = detect_events(date(2026, 8, 1), 'e', {'M3': 'เช็คอินเกิน 8:30 ตัดเบี้ยเลี้ยง'})
    assert {e.event_type for e in events} == {'LATE_CHECK_IN', 'ALLOWANCE_CUT_NOTE'}
    assert all(e.affects_attendance_bonus is None and e.affects_allowance is None for e in events)


def test_ot_is_not_assigned_to_normal_or_holiday_rates(parsed_history):
    day = next(d for d in employee(parsed_history[8]).days if d.ot.number)
    event = next(e for e in day.events if e.event_type == 'OT_CLASSIFICATION_REQUIRED')
    assert event.hours == day.ot.number and event.suggested_type is None
    assert event.requires_review


@pytest.mark.parametrize('raw', ['150', 'อบรม', 'เช็คอินเกินเวลา', True, time(2)])
def test_non_numeric_amount_is_never_silently_zero(edit_attendance_copy, raw):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['I3'], 'value', raw))
    assert e.days[0].allowance.raw == raw
    assert e.days[0].allowance.number is None
    assert not e.totals['allowance'].complete and e.totals['allowance'].source_sum is None
    assert 'NON_NUMERIC_VALUE' in {i.code for i in e.issues}


def test_negative_money_is_retained_for_review(edit_attendance_copy):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['J3'], 'value', -50))
    assert e.days[0].travel.number == Decimal(-50)
    assert not e.totals['travel'].complete
    assert any(i.code == 'NEGATIVE_VALUE' and i.cell == 'J3' for i in e.issues)


@pytest.mark.parametrize('raw', ['31/02/2026', 'invalid', None, '=DATE(2026,8,1)'])
def test_invalid_or_missing_dates_block_sums(edit_attendance_copy, raw):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['A3'], 'value', raw))
    assert len(e.days) == 30 and e.rejected_rows[0].date_raw == raw
    assert e.totals['travel'].source_sum is None
    assert any(i.severity == Severity.ERROR for i in e.issues)


def test_duplicate_dates_are_retained_and_block_totals(edit_attendance_copy):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['A4'], 'value', s['A3'].value))
    assert len(e.days) == 31  # Never silently remove one person's row or money.
    assert 'DUPLICATE_DATE' in {i.code for i in e.issues}
    assert e.totals['travel'].source_sum is None


def test_out_of_month_rows_retain_evidence(edit_attendance_copy):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['A3'], 'value', datetime(2026, 7, 1)))
    assert e.rejected_rows[0].reason == 'OUT_OF_PERIOD'
    assert 'J3' in e.rejected_rows[0].source_cells


def test_daily_formula_not_evaluated_or_trusted(edit_attendance_copy):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['I3'], 'value', '=100+50'))
    assert e.days[0].allowance.raw == '=100+50'
    assert e.days[0].allowance.kind == 'FORMULA'
    assert e.days[0].allowance.number is None
    assert 'DAILY_FORMULA' in {i.code for i in e.issues}
    assert e.totals['allowance'].source_sum is None


def test_excel_error_not_a_number(edit_attendance_copy):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['I3'], 'value', '#VALUE!'))
    assert e.days[0].allowance.kind == 'ERROR'
    assert 'CELL_ERROR' in {i.code for i in e.issues}


def test_missing_or_duplicate_headers_fail_safely(edit_attendance_copy):
    path = edit_attendance_copy(lambda s: setattr(s['J2'], 'value', 'Changed travel label'))
    e = employee(read_attendance(path, year=2026, month=8))
    assert not e.days and not e.totals
    assert e.issues[0].code == 'TEMPLATE_MISMATCH'


def test_duplicate_header_fails_safely(edit_attendance_copy):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['AA2'], 'value', 'OT'))
    assert e.issues[0].code == 'TEMPLATE_MISMATCH'


def test_shifted_table_and_extra_column_supported(edit_attendance_copy):
    def shift(sheet):
        from openpyxl.worksheet.cell_range import CellRange
        # move_range does not relocate merge definitions; move those explicitly
        # so this test creates a valid shifted template rather than corrupting it.
        ranges = [CellRange(str(r)) for r in sheet.merged_cells.ranges]
        for merged in ranges:
            sheet.unmerge_cells(str(merged))
        sheet.move_range('A1:W36', rows=4, cols=2, translate=True)
        for merged in ranges:
            merged.shift(row_shift=4, col_shift=2)
            sheet.merge_cells(str(merged))
        sheet['AA7'] = 'new extra-column note'
    e = edited_first(edit_attendance_copy, shift)
    assert e.header_row == 6 and e.name_cell == 'D5'
    assert e.columns['travel'] == 12
    assert e.days[0].travel.coordinate == 'L7'
    assert e.days[0].extra_cells['AA7'] == 'new extra-column note'
    assert e.totals['travel'].numeric_subtotal == Decimal(1300)


def test_extended_daily_rows_not_truncated(edit_attendance_copy):
    def extend(sheet):
        sheet['A150'] = datetime(2026, 8, 1)
        sheet['J150'] = 99
    e = edited_first(edit_attendance_copy, extend)
    assert any(d.row == 150 for d in e.days)
    assert e.totals['travel'].numeric_subtotal == Decimal(1399)
    assert 'DUPLICATE_DATE' in {i.code for i in e.issues}


def test_raw_buddhist_date_is_preserved(edit_attendance_copy):
    e = edited_first(edit_attendance_copy, lambda s: setattr(s['A3'], 'value', datetime(2569, 8, 1)))
    assert e.days[0].date == date(2026, 8, 1)
    assert e.days[0].date_raw.year == 2569


def test_period_conflict_fails_before_parsing(copied_reference):
    path = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    with pytest.raises(WorkbookReadError, match='conflicts'):
        read_attendance(path, year=2026, month=9)


def test_idempotent_reread_has_identical_evidence(copied_reference):
    path = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    first = read_attendance(path)
    assert read_attendance(path) == first
    assert sum(e.totals['travel'].numeric_subtotal for e in first.employees) > 0


def test_stored_sum_is_validation_not_extra_daily_money(parsed_history):
    e = employee(parsed_history[8])
    assert e.totals['travel'].numeric_subtotal == Decimal(1300)
    stored = next(t for t in e.stored_totals if t.field == 'travel')
    assert stored.formula == '=SUM(J3:J35)' and stored.difference == 0
    assert e.totals['travel'].source_sum == Decimal(1300)
