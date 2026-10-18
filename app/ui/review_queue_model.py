"""Read-only presentation adapter for the embedded payroll review queue."""
from dataclasses import dataclass
from datetime import date

from app.ui.presentation import issue_text, raw_evidence


ISSUE_CATEGORIES = {
    'IDENTITY': ('IDENTITY', 'ข้อมูลพนักงาน'),
    'UNKNOWN_PAYROLL_EMPLOYEE': ('IDENTITY', 'ข้อมูลพนักงาน'),
    'LEAVE': ('LEAVE', 'การลา'),
    'OT': ('OT', 'OT'),
    'HOLIDAY_WORK': ('OT', 'ทำงานวันหยุด'),
    'HOLIDAY': ('CALENDAR', 'ปฏิทินวันทำงาน'),
    'PAYSLIP_MAPPING': ('PAYSLIP', 'ผังใบเงินเดือน'),
    'FIELD': ('FINANCIAL', 'รายการเงินเดือน'),
}


@dataclass(frozen=True)
class ReviewQueueItem:
    issue: object
    employee_id: str | None
    employee_name: str
    category: str
    category_label: str
    severity: str
    severity_label: str
    date_label: str
    description: str
    evidence: str
    source_reference: str
    action_kind: str


@dataclass(frozen=True)
class ReviewQueueSnapshot:
    year: int
    month: int
    period_label: str
    items: tuple[ReviewQueueItem, ...]
    critical_count: int
    warning_count: int
    employees: tuple[tuple[str, str], ...]


def thai_date(value):
    """Format verified ISO dates for display; leave unavailable evidence blank."""
    if not value:
        return ''
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return str(value)
    return f'{parsed.day:02}/{parsed.month:02}/{parsed.year + 543}'


def thai_period(year, month):
    months = ('มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
              'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม')
    return f'{months[int(month) - 1]} {int(year) + 543}'


def classify_issue(issue):
    """Classify only by existing issue metadata; no financial inference."""
    if issue.kind.startswith('SOURCE_'):
        return 'SOURCE', 'ข้อมูลจากไฟล์ต้นทาง', 'source_correction'
    if issue.kind.startswith('CALENDAR'):
        return 'CALENDAR', 'ปฏิทินวันทำงาน', 'decision'
    category, label = ISSUE_CATEGORIES.get(issue.kind, ('OTHER', 'รายการที่ต้องตรวจสอบ'))
    return category, label, 'payslip' if issue.kind == 'PAYSLIP_MAPPING' else 'decision'


class ReviewQueueModel:
    """Transforms one selected draft into stable, filter-ready queue items."""
    def snapshot(self, draft, *, year, month):
        if draft is None:
            return ReviewQueueSnapshot(int(year), int(month), thai_period(year, month), (), 0, 0, ())
        names = {employee.employee_id: employee.name for employee in draft.employees if employee.employee_id}
        items = tuple(sorted(
            (self._item(issue, names) for issue in draft.issues),
            key=lambda item: (
                0 if item.severity == 'CRITICAL' else 1,
                item.employee_name.casefold(),
                item.issue.day or '', item.issue.kind, item.issue.key,
            ),
        ))
        employees = tuple(sorted(((employee_id, name) for employee_id, name in names.items()),
                                 key=lambda entry: entry[1].casefold()))
        return ReviewQueueSnapshot(
            int(year), int(month), thai_period(year, month), items,
            sum(item.severity == 'CRITICAL' for item in items),
            sum(item.severity == 'WARNING' for item in items), employees,
        )

    @staticmethod
    def _item(issue, names):
        category, category_label, action_kind = classify_issue(issue)
        if issue.employee_id:
            employee_name = names.get(issue.employee_id, 'ไม่พบข้อมูลพนักงาน')
        else:
            employee_name = 'ข้อมูลส่วนกลาง'
        reference = ' / '.join(part for part in (issue.sheet, issue.cell) if part)
        return ReviewQueueItem(
            issue=issue,
            employee_id=issue.employee_id,
            employee_name=employee_name,
            category=category,
            category_label=category_label,
            severity='CRITICAL' if issue.critical else 'WARNING',
            severity_label='ต้องดำเนินการ' if issue.critical else 'คำเตือน',
            date_label=thai_date(issue.day),
            description=issue_text(issue),
            evidence=raw_evidence(issue),
            source_reference=reference,
            action_kind=action_kind,
        )
