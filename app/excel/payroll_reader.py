"""Validated label-based adapters for the observed payroll layouts."""
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from datetime import datetime
import re

from app.analysis.historical import FIELD_LABELS
from app.domain import normalized_name
from app.excel.workbook_source import WorkbookSnapshot


class TemplateError(ValueError):
    def __init__(self, detail):
        super().__init__('รูปแบบไฟล์เงินเดือนเปลี่ยน กรุณาตรวจสอบ: ' + detail)


def label(value):
    return ' '.join(str(value or '').split()).casefold()


def numeric(value):
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        result = Decimal(str(value))
        return result if result.is_finite() else None
    return None


@dataclass(frozen=True)
class PayrollCell:
    coordinate: str
    value: Decimal | None
    raw: object
    formula: str | None


@dataclass(frozen=True)
class PayrollEmployee:
    name: str
    row: int
    cells: dict[str, PayrollCell]


@dataclass(frozen=True)
class PayrollWorkbookAdapter:
    path: Path
    source_hash: str
    sheet_name: str
    header_row: int
    columns: dict[str, int]
    employees: tuple[PayrollEmployee, ...]
    period_text: str | None = None

    @classmethod
    def read(cls, path):
        snapshot = WorkbookSnapshot.read(path)
        with snapshot.open() as (book, cached):
            mains = [s for s in book if label(s.title) == label('คิดค่าจ้าง')]
            if len(mains) != 1:
                raise TemplateError('Cannot uniquely locate the payroll calculation sheet')
            sheet = mains[0]
            name_headers = [c for row in sheet for c in row if label(c.value) == label('ชื่อ-สกุล')]
            if len(name_headers) != 1:
                raise TemplateError('Employee-name header is missing or ambiguous')
            major = name_headers[0].row
            name_col = name_headers[0].column
            headers = [c for row in sheet.iter_rows(min_row=major, max_row=major + 2) for c in row]
            def find(text, required=True):
                matches = [c for c in headers if label(c.value) == label(text)]
                if len(matches) > 1 or (required and not matches):
                    raise TemplateError(f'Header is missing or ambiguous: {text}')
                return matches[0] if matches else None
            ordinal = find('ลำดับ').column
            columns = {'base': find('ค่าจ้าง').column,
                       'income': find('รวมเงินได้').column, 'net': find('รายได้สุทธิ').column}
            for group, fields, expected in [
                ('ค่าล่วงเวลาปกติ x 1.5', ('normal_rate', 'normal_ot', 'normal_money'), ('ชั่วโมงละ', 'จำนวนชม.', 'รวมเงิน')),
                ('ค่าทำงานในวันหยุด', ('holiday_rate', 'holiday_days', 'holiday_money'), ('วันละ', 'จำนวนวัน', 'รวมเงิน')),
                ('OT วันหยุด x 3', ('holiday_ot_rate', 'holiday_ot', 'holiday_ot_money'), ('ชั่วโมงละ', 'จำนวนชม.', 'รวมเงิน')),
            ]:
                start = find(group)
                for offset, (field, subheader) in enumerate(zip(fields, expected)):
                    cell = sheet.cell(start.row + 1, start.column + offset)
                    if label(cell.value) != label(subheader):
                        raise TemplateError(f'Unexpected group structure: {group}')
                    columns[field] = cell.column
            for field, text in FIELD_LABELS.items():
                cell = find(text, required=field in {'bonus', 'travel', 'allowance'})
                if cell:
                    columns[field] = cell.column
            data_start = major + 3
            employees = []
            seen = set()
            for row in sheet.iter_rows(min_row=data_start):
                number = sheet.cell(row[0].row, ordinal).value
                name = sheet.cell(row[0].row, name_col).value
                if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
                    continue
                if not isinstance(name, str) or not normalized_name(name):
                    raise TemplateError('Numbered employee row lacks a name')
                normalized = normalized_name(name)
                if normalized in seen:
                    raise TemplateError('Duplicate full payroll name')
                seen.add(normalized)
                cells = {}
                for field, column in columns.items():
                    cell = sheet.cell(row[0].row, column)
                    if cell.data_type == 'f' and not isinstance(cell.value, str):
                        raise TemplateError('Unsupported formula type in a payroll value cell')
                    value = cached[sheet.title][cell.coordinate].value if cell.data_type == 'f' else cell.value
                    if cell.data_type == 'e':
                        raise TemplateError('Excel error in payroll values')
                    cells[field] = PayrollCell(cell.coordinate, numeric(value), cell.value,
                                               cell.value if cell.data_type == 'f' else None)
                employees.append(PayrollEmployee(name, row[0].row, cells))
            if not employees:
                raise TemplateError('No numbered employee rows found')
            period_labels = [c.value for row in sheet.iter_rows(max_row=major - 1) for c in row
                             if isinstance(c.value, str) and 'ประจำเดือน' in c.value]
            period_text = period_labels[0] if len(period_labels) == 1 else None
        return cls(snapshot.path, snapshot.sha256, sheet.title, major, columns, tuple(employees), period_text)

    def payment_date(self):
        months = ['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน',
                  'กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
        match = re.search(r'จ่ายวันที่\s*(\d{1,2})\s+(' + '|'.join(months) + r')\s+(\d{4})', self.period_text or '')
        if not match:
            raise TemplateError('Payment date cannot be uniquely read from the payroll period label')
        day, month, year = int(match[1]), months.index(match[2]) + 1, int(match[3])
        year = year - 543 if 2400 <= year <= 2800 else year
        return datetime(year, month, day)

    def period(self):
        months = ['มกราคม','กุมภาพันธ์','มีนาคม','เมษายน','พฤษภาคม','มิถุนายน',
                  'กรกฎาคม','สิงหาคม','กันยายน','ตุลาคม','พฤศจิกายน','ธันวาคม']
        match = re.search(r'ประจำเดือน\s+('+'|'.join(months)+r')\s+(\d{4})',self.period_text or '')
        if not match: raise TemplateError('Payroll month/year label is missing or ambiguous')
        year=int(match[2])
        return (year-543 if 2400<=year<=2800 else year,months.index(match[1])+1)

    def employee(self, name):
        matches = [e for e in self.employees if normalized_name(e.name) == normalized_name(name)]
        if len(matches) != 1:
            raise TemplateError('Employee identity must match a unique full payroll name')
        return matches[0]
