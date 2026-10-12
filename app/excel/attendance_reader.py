"""Phase 2 attendance parser: dynamic headers, exact evidence, no workbook writes."""
from calendar import monthrange
from collections import Counter
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import re
import unicodedata

from app.excel.workbook_source import WorkbookReadError, WorkbookSnapshot, filename_month
from app.models import (
    AttendanceDay, AttendanceEvent, AttendanceTotal, AttendanceWorkbook,
    EmployeeAttendance, ParseIssue, RejectedRow, Severity, SourceCell, StoredTotal,
)
from app.payroll.attendance_rules import detect_events

HEADERS = {'วันที่': 'date', 'ชื่องาน': 'work', 'สถานที่': 'location',
           'เวลาเข้า': 'clock_in', 'เวลาออก': 'clock_out', 'ot': 'ot',
           'เบี้ยเลี้ยง': 'allowance', 'ค่าเดินทาง': 'travel',
           'check in หน้างาน': 'check_in', 'check out หน้างาน': 'check_out',
           'หมายเหตุ': 'note', 'วันในสัปดาห์': 'weekday'}
REQUIRED = {'date', 'work', 'location', 'clock_in', 'clock_out', 'ot', 'allowance', 'travel'}
MONEY_FIELDS = ('ot', 'allowance', 'travel')
BLOCKING_ROWS = {'INVALID_DATE', 'MISSING_DATE', 'OUT_OF_PERIOD', 'DUPLICATE_DATE',
                 'MISSING_DATES', 'NO_CURRENT_DAYS', 'DATE_FORMULA'}


def _label(value):
    return ' '.join(unicodedata.normalize('NFC', str(value or '')).split()).casefold()


def _name(value):
    text = unicodedata.normalize('NFC', str(value or '')).strip()
    return ' '.join(re.sub(r'^(?:นาย|นางสาว|น\.ส\.|นาง)\s*', '', text).split())


def _number(value):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        n = Decimal(str(value))
        return n if n.is_finite() else None
    return None


def _date(value):
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        value = value.strip()
        try:
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
                value = date.fromisoformat(value)
            elif re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', value):
                day, month, year = map(int, value.split('/'))
                value = date(year, month, day)
            else:
                return None
        except ValueError:
            return None
    if not isinstance(value, date):
        return None
    # Explicit Buddhist-era years, never subtract 543 from Gregorian dates.
    return value.replace(year=value.year - 543) if 2400 <= value.year <= 2800 else value


def _headers(sheet):
    candidates = []
    for row in sheet:
        columns = {}
        duplicates = set()
        for cell in row:
            key = HEADERS.get(_label(cell.value))
            if key:
                if key in columns:
                    duplicates.add(key)
                columns[key] = cell.column
        if REQUIRED <= columns.keys():
            candidates.append((row[0].row, columns, duplicates))
    if len(candidates) != 1:
        return None, {}, 'Missing or ambiguous attendance header row'
    row, columns, duplicates = candidates[0]
    if duplicates:
        return None, {}, f'Duplicate attendance headers: {sorted(duplicates)}'
    # The observed date header merges A:C; weekday text sits immediately right.
    # Use an explicit weekday header if a newer template supplies one.
    columns.setdefault('weekday', columns['date'] + 1)
    return row, columns, None


def _identity(sheet, header_row):
    found = []
    for row in sheet.iter_rows(max_row=(header_row or 1) - 1):
        for cell in row:
            if _label(cell.value) == 'ชื่อ':
                target = sheet.cell(cell.row, cell.column + 1)
                found.append((target.coordinate, target.value))
    if len(found) != 1:
        return None, None
    coord, raw = found[0]
    return coord, raw if isinstance(raw, str) and raw.strip() and not raw.startswith('=') else None


def _source_cell(cell, cached, field, sheet, issues):
    raw = cell.value
    if raw is None or raw == '':
        return SourceCell(cell.coordinate, raw, 'EMPTY')
    if cell.data_type == 'f':
        issues.append(ParseIssue('DAILY_FORMULA', Severity.WARNING, sheet, cell.coordinate,
                                 f'{field}: cached formula results require validation'))
        return SourceCell(cell.coordinate, raw, 'FORMULA', cached=cached.value)
    if cell.data_type == 'e':
        issues.append(ParseIssue('CELL_ERROR', Severity.ERROR, sheet, cell.coordinate,
                                 f'{field}: Excel error in source'))
        return SourceCell(cell.coordinate, raw, 'ERROR')
    n = _number(raw)
    if n is None:
        issues.append(ParseIssue('NON_NUMERIC_VALUE', Severity.WARNING, sheet, cell.coordinate,
                                 f'{field}: non-numeric source requires review'))
        return SourceCell(cell.coordinate, raw, 'TEXT' if isinstance(raw, str) else 'INVALID')
    if n < 0:
        issues.append(ParseIssue('NEGATIVE_VALUE', Severity.WARNING, sheet, cell.coordinate,
                                 f'{field}: negative value retained without adjustment'))
    if field == 'ot' and n > 24:
        issues.append(ParseIssue('UNUSUAL_OT', Severity.WARNING, sheet, cell.coordinate,
                                 'Daily numeric OT exceeds 24 hours; units require confirmation'))
    return SourceCell(cell.coordinate, raw, 'NUMBER', number=n)


def _read_sheet(sheet, cached, year, month):
    title = sheet.title  # Never trim the key used to access an actual worksheet.
    issues = []
    header_row, columns, header_problem = _headers(sheet)
    name_cell, full_name = _identity(sheet, header_row)
    period_raw = sheet['J1'].value  # Observed metadata; not the source of daily dates.
    if header_problem:
        return EmployeeAttendance(title, full_name, name_cell, None, None, columns, period_raw,
                                  (), (), {}, (), (ParseIssue('TEMPLATE_MISMATCH', Severity.ERROR, title, None, header_problem),))
    if not full_name:
        issues.append(ParseIssue('UNKNOWN_EMPLOYEE', Severity.ERROR, title, name_cell,
                                 'Employee label is absent; sheet name alone cannot identify an employee'))
    elif title.strip('- '):
        if _name(title) != _name(full_name).split()[0]:
            issues.append(ParseIssue('IDENTITY_CONFLICT', Severity.ERROR, title, name_cell,
                                     'Sheet name and employee label disagree; human mapping required'))
        elif len(_name(full_name).split()) < 2:
            issues.append(ParseIssue('INCOMPLETE_EMPLOYEE_NAME', Severity.WARNING, title, name_cell,
                                     'First-name-only label requires a confirmed employee alias'))
    else:
        issues.append(ParseIssue('PLACEHOLDER_SHEET', Severity.WARNING, title, name_cell,
                                 'Placeholder sheet must be reviewed before assigning an employee'))
    days, rejected, total_candidates = [], [], []
    for row in sheet.iter_rows(min_row=header_row + 1):
        row_number = row[0].row
        cells = {key: sheet.cell(row_number, col) for key, col in columns.items()}
        date_cell = cells['date']
        raw_date = date_cell.value
        # Recognize actual total formulas; never count totals as daily amounts.
        sum_cells = [(key, cells[key]) for key in MONEY_FIELDS
                     if cells[key].data_type == 'f' and isinstance(cells[key].value, str)
                     and re.match(r'^=\s*SUM\s*\(', cells[key].value, re.I)]
        if raw_date is None and sum_cells:
            total_candidates.extend(sum_cells)
            continue
        relevant = {key: c.value for key, c in cells.items() if key not in ('date', 'weekday')}
        if raw_date is None and all(v is None for v in relevant.values()):
            continue
        if date_cell.data_type == 'f':
            day, reason = None, 'DATE_FORMULA'
        else:
            day = _date(raw_date)
            reason = 'MISSING_DATE' if raw_date is None else 'INVALID_DATE' if day is None else None
        if day is not None and (day.year, day.month) != (year, month):
            reason = 'OUT_OF_PERIOD'
        if reason:
            rejected.append(RejectedRow(row_number, raw_date, reason,
                                        {c.coordinate: c.value for c in row if c.value is not None}))
            issues.append(ParseIssue(reason, Severity.ERROR, title, date_cell.coordinate,
                                     'Daily row cannot be assigned to the expected payroll month'))
            continue
        values = {key: _source_cell(cells[key], cached[cells[key].coordinate], key, title, issues)
                  for key in MONEY_FIELDS}
        extra = {c.coordinate: c.value for c in row
                 if c.column not in columns.values() and c.value is not None}
        texts = {c.coordinate: c.value for c in row
                 if c.column not in (columns['date'], columns['weekday']) and isinstance(c.value, str)
                 and c.data_type != 'f'}
        events = list(detect_events(day, title, texts))
        if values['ot'].number is not None and values['ot'].number != 0:
            events.append(AttendanceEvent('OT_CLASSIFICATION_REQUIRED', day, title,
                values['ot'].coordinate, str(values['ot'].raw), hours=values['ot'].number))
        clocks = any(cells[k].value is not None for k in ('clock_in', 'clock_out'))
        if clocks and (day.weekday() == 6 or any(e.event_type == 'HOLIDAY_SUGGESTION' for e in events)):
            events.append(AttendanceEvent('WORK_ON_HOLIDAY_CANDIDATE', day, title,
                cells['work'].coordinate, str(cells['work'].value or ''), suggested_type='UNKNOWN'))
        if 'note' in cells and cells['note'].value is not None and not any(e.cell == cells['note'].coordinate for e in events):
            events.append(AttendanceEvent('UNCLASSIFIED_NOTE', day, title, cells['note'].coordinate,
                                          str(cells['note'].value)))
        def value(key):
            return cells[key].value if key in cells else None
        days.append(AttendanceDay(day, row_number, raw_date, value('weekday'), value('work'), value('location'),
                    value('clock_in'), value('clock_out'), value('check_in'), value('check_out'), value('note'),
                    values['ot'], values['allowance'], values['travel'], extra, tuple(events)))
    dates = Counter(d.date for d in days)
    for day, count in sorted(dates.items()):
        if count > 1:
            issues.append(ParseIssue('DUPLICATE_DATE', Severity.ERROR, title, None,
                                     f'Duplicate date {day.isoformat()} ({count} rows); nothing deduplicated silently'))
    expected = {date(year, month, d) for d in range(1, monthrange(year, month)[1] + 1)}
    missing = sorted(expected - dates.keys())
    if not days:
        issues.append(ParseIssue('NO_CURRENT_DAYS', Severity.ERROR, title, None, 'No valid daily rows for this month'))
    elif missing:
        issues.append(ParseIssue('MISSING_DATES', Severity.WARNING, title, None,
                                 'Missing calendar dates: ' + ', '.join(d.isoformat() for d in missing)))
    row_errors = any(i.code in BLOCKING_ROWS for i in issues)
    totals = {}
    for key in MONEY_FIELDS:
        source_cells = [getattr(day, key) for day in days]
        subtotal = sum((cell.number or Decimal(0) for cell in source_cells), Decimal(0))
        complete = (not row_errors and all(cell.kind in ('NUMBER', 'EMPTY') for cell in source_cells)
                    and not any((cell.number or 0) < 0 for cell in source_cells))
        totals[key] = AttendanceTotal(subtotal, complete, tuple(cell.coordinate for cell in source_cells))
    stored = []
    for key, cell in total_candidates:
        cached_value = cached[cell.coordinate].value
        observed = _number(cached_value)
        difference = totals[key].numeric_subtotal - observed if observed is not None else None
        stored.append(StoredTotal(key, cell.coordinate, cell.value, cached_value, difference))
        if observed is None:
            totals[key] = replace(totals[key], complete=False)
            issues.append(ParseIssue('TOTAL_CACHE_UNAVAILABLE', Severity.WARNING, title, cell.coordinate,
                                     'Stored SUM cannot be validated without an Excel numeric cache'))
        elif difference != 0:
            totals[key] = replace(totals[key], complete=False)
            issues.append(ParseIssue('TOTAL_MISMATCH', Severity.WARNING, title, cell.coordinate,
                                     f'Numeric daily subtotal differs from saved SUM by {difference}'))
    return EmployeeAttendance(title, full_name, name_cell, None, header_row, columns, period_raw,
                              tuple(days), tuple(rejected), totals, tuple(stored), tuple(issues))


def read_attendance(path: Path, *, year: int | None = None, month: int | None = None) -> AttendanceWorkbook:
    """Parse saved XLSX bytes. This function never opens Excel or saves a workbook.

    Defaults infer only a unique year from literal period/date evidence and a
    month from the filename. Pass an explicit period for other file names.
    All employee IDs remain unset until a confirmed Phase 3 alias exists.
    """
    snapshot = WorkbookSnapshot.read(path)
    try:
        named_month = filename_month(snapshot.path)
    except WorkbookReadError:
        named_month = None
    if month is None:
        month = named_month
    elif named_month is not None and month != named_month:
        raise WorkbookReadError('Explicit payroll month conflicts with the workbook filename')
    if not isinstance(month, int) or isinstance(month, bool) or not 1 <= month <= 12:
        raise WorkbookReadError('A known payroll month is required')
    with snapshot.open() as (book, cached):
        if year is None:
            evidence = set()
            for sheet in book:
                if not sheet.title.strip('- '):
                    continue
                metadata = _date(sheet['J1'].value)
                if metadata and metadata.month == month:
                    evidence.add(metadata.year)
            if not evidence:
                for sheet in book:
                    if not sheet.title.strip('- '):
                        continue
                    header, cols, error = _headers(sheet)
                    if not error:
                        for row in sheet.iter_rows(min_row=header + 1):
                            day = _date(sheet.cell(row[0].row, cols['date']).value)
                            if day and day.month == month:
                                evidence.add(day.year)
            if len(evidence) != 1:
                raise WorkbookReadError('Cannot determine a unique payroll year; supply an explicit year')
            year = evidence.pop()
        if not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year < 2400:
            raise WorkbookReadError('Expected a Gregorian payroll year between 1900 and 2399')
        employees = [_read_sheet(s, cached[s.title], year, month) for s in book]
    identities = Counter(_name(e.full_name) for e in employees if e.full_name)
    for index, employee in enumerate(employees):
        if employee.full_name and identities[_name(employee.full_name)] > 1:
            issue = ParseIssue('DUPLICATE_EMPLOYEE_LABEL', Severity.ERROR, employee.sheet_name, employee.name_cell,
                               'Multiple sheets claim the same employee label; alias review required')
            employees[index] = replace(employee, issues=(*employee.issues, issue))
    return AttendanceWorkbook(str(snapshot.path), snapshot.sha256, year, month, tuple(employees))
