"""Payroll decisions and source-preserving draft types (separate from Phase 2)."""
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
import json
import re
import unicodedata


class PayrollState(StrEnum):
    DRAFT = 'DRAFT'
    NEEDS_REVIEW = 'NEEDS_REVIEW'
    READY = 'READY'
    CONFIRMED = 'CONFIRMED'
    WRITTEN = 'WRITTEN'
    LOCKED = 'LOCKED'


class ValueCategory(StrEnum):
    AUTO_CALCULATED = 'AUTO_CALCULATED'
    RECURRING = 'RECURRING'
    MANUAL = 'MANUAL'
    REVIEW_REQUIRED = 'REVIEW_REQUIRED'


class ReusePolicy(StrEnum):
    ALWAYS_SUGGEST = 'ALWAYS_SUGGEST'
    AUTO_REUSE = 'AUTO_REUSE'
    NEVER_REUSE = 'NEVER_REUSE'
    ONE_TIME = 'ONE_TIME'


class OTCategory(StrEnum):
    NORMAL = 'NORMAL'
    HOLIDAY_OT = 'HOLIDAY_OT'
    HOLIDAY_WORK = 'HOLIDAY_WORK'


RECURRING_FIELDS = {'base', 'phone', 'position', 'housing'}
MANUAL_FIELDS = {'advance', 'tool_loss', 'damage', 'loan', 'special_bonus', 'adjustment',
                 'tax', 'social_security', 'annual_leave_return', 'no_leave_award', 'advance_return'}
FINAL_STATES = {PayrollState.CONFIRMED, PayrollState.WRITTEN, PayrollState.LOCKED}
THAI_FIELDS = {'base': 'เงินเดือน/ค่าจ้าง', 'phone': 'ค่าโทรศัพท์', 'position': 'ค่าตำแหน่ง',
               'housing': 'ที่พัก+ค่าน้ำ+ไฟ', 'travel': 'ค่าเดินทาง', 'allowance': 'เบี้ยเลี้ยง',
               'bonus': 'เบี้ยขยัน', 'advance': 'เบิกล่วงหน้า', 'tool_loss': 'หักเครื่องมือหาย',
               'loan': 'หักเงินกู้ยืม', 'tax': 'ภาษี', 'social_security': 'ประกันสังคม',
               'special_bonus': 'โบนัสพิเศษ', 'annual_leave_return': 'คืนพักร้อน',
               'no_leave_award': 'รางวัลไม่ลา', 'advance_return': 'คืนเบิก advance',
               'normal_ot': 'OT ปกติ (ชม.)', 'holiday_ot': 'OT วันหยุด (ชม.)',
               'holiday_days': 'ทำงานวันหยุด (วัน)', 'normal_money': 'ค่าล่วงเวลาปกติ',
               'holiday_money': 'ค่าทำงานวันหยุด', 'holiday_ot_money': 'ค่าล่วงเวลาวันหยุด',
               'income': 'รายได้รวม', 'net': 'รายได้สุทธิ'}


def normalized_name(value):
    text = unicodedata.normalize('NFC', str(value or '')).strip()
    return ' '.join(re.sub(r'^(?:นาย|นางสาว|น\.ส\.|นาง)\s*', '', text).split())


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def decimal_value(value):
    if value is None or value == '':
        return None
    if isinstance(value, bool):
        raise ValueError('Boolean is not a payroll amount')
    try:
        result = Decimal(str(value).replace(',', ''))
    except InvalidOperation as exc:
        raise ValueError('กรุณาระบุจำนวนเงินเป็นตัวเลข') from exc
    if not result.is_finite():
        raise ValueError('Amount must be finite')
    return result


def json_default(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)


def issue_key(kind, *parts):
    return kind + ':' + sha256(encode(parts).encode('utf-8')).hexdigest()[:24]


@dataclass(frozen=True)
class ReviewIssue:
    key: str
    kind: str
    employee_id: str | None
    sheet: str | None
    day: str | None
    cell: str | None
    message: str
    raw_text: str = ''
    critical: bool = True
    field: str | None = None
    suggested: str | None = None


@dataclass(frozen=True)
class PayrollValue:
    field: str
    category: ValueCategory
    source_value: Decimal | None
    previous_value: Decimal | None
    draft_value: Decimal | None
    user_override: Decimal | None
    final_value: Decimal | None
    reason: str
    source_reference: str
    confirmed: bool = False


@dataclass(frozen=True)
class OTCase:
    date: str
    cell: str
    raw: str
    hours: Decimal | None
    day_type: str
    suggested_category: str | None
    category: str | None
    confidence: str
    reason: str


@dataclass(frozen=True)
class EmployeeDraft:
    key: str
    employee_id: str | None
    name: str
    sheet: str | None
    values: dict[str, PayrollValue]
    issues: tuple[ReviewIssue, ...]
    ot_cases: tuple[OTCase, ...] = ()

    @property
    def ready(self):
        return bool(self.employee_id) and not any(i.critical for i in self.issues) and all(
            v.final_value is not None for v in self.values.values())


@dataclass(frozen=True)
class PayrollDraft:
    year: int
    month: int
    source_path: str
    source_hash: str
    payroll_path: str
    payroll_hash: str
    employees: tuple[EmployeeDraft, ...]
    global_issues: tuple[ReviewIssue, ...] = ()

    @property
    def issues(self):
        return (*self.global_issues, *(i for e in self.employees for i in e.issues))

    @property
    def state(self):
        return PayrollState.READY if self.employees and all(e.ready for e in self.employees) and not any(
            i.critical for i in self.global_issues) else PayrollState.NEEDS_REVIEW

    def evidence(self):
        return asdict(self)


def decode_draft(text):
    data = json.loads(text) if isinstance(text, str) else text
    employees = []
    for employee in data['employees']:
        values = {}
        for key, value in employee['values'].items():
            value = dict(value)
            value['category'] = ValueCategory(value['category'])
            for money in ('source_value', 'previous_value', 'draft_value', 'user_override', 'final_value'):
                value[money] = decimal_value(value[money])
            values[key] = PayrollValue(**value)
        cases = [OTCase(**{**case, 'hours': decimal_value(case['hours'])}) for case in employee.get('ot_cases', [])]
        employees.append(EmployeeDraft(employee['key'], employee['employee_id'], employee['name'], employee['sheet'],
            values, tuple(ReviewIssue(**i) for i in employee['issues']), tuple(cases)))
    return PayrollDraft(data['year'], data['month'], data['source_path'], data['source_hash'],
        data['payroll_path'], data['payroll_hash'], tuple(employees), tuple(ReviewIssue(**i) for i in data['global_issues']))
