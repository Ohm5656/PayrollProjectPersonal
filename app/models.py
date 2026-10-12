"""Immutable source evidence. No payroll policy or eligibility is inferred."""
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'


class DayType(StrEnum):
    WORKING_DAY = 'WORKING_DAY'
    WEEKLY_HOLIDAY = 'WEEKLY_HOLIDAY'
    SUBSTITUTE_HOLIDAY = 'SUBSTITUTE_HOLIDAY'
    PUBLIC_HOLIDAY = 'PUBLIC_HOLIDAY'
    COMPANY_SPECIAL_HOLIDAY = 'COMPANY_SPECIAL_HOLIDAY'
    EMERGENCY_CLOSURE = 'EMERGENCY_CLOSURE'
    EMPLOYEE_LEAVE = 'EMPLOYEE_LEAVE'
    UNKNOWN = 'UNKNOWN'


@dataclass(frozen=True)
class ParseIssue:
    code: str
    severity: Severity
    sheet: str
    cell: str | None
    message: str


@dataclass(frozen=True)
class SourceCell:
    coordinate: str
    raw: Any
    kind: str
    number: Decimal | None = None
    cached: Any = None


@dataclass(frozen=True)
class AttendanceEvent:
    event_type: str
    date: date
    sheet: str
    cell: str
    raw_text: str
    suggested_type: str | None = None
    hours: Decimal | None = None
    days: Decimal | None = None
    requires_review: bool = True
    affects_attendance_bonus: bool | None = None
    affects_allowance: bool | None = None


@dataclass(frozen=True)
class AttendanceDay:
    date: date
    row: int
    date_raw: Any
    weekday_raw: Any
    work: Any
    location: Any
    clock_in: Any
    clock_out: Any
    check_in: Any
    check_out: Any
    note: Any
    ot: SourceCell
    allowance: SourceCell
    travel: SourceCell
    extra_cells: dict[str, Any] = field(default_factory=dict)
    events: tuple[AttendanceEvent, ...] = ()


@dataclass(frozen=True)
class AttendanceTotal:
    numeric_subtotal: Decimal
    complete: bool
    source_cells: tuple[str, ...]

    @property
    def source_sum(self) -> Decimal | None:
        """Validated numeric source sum only; not a confirmed payroll amount."""
        return self.numeric_subtotal if self.complete else None


@dataclass(frozen=True)
class StoredTotal:
    field: str
    cell: str
    formula: Any
    cached: Any
    difference: Decimal | None


@dataclass(frozen=True)
class RejectedRow:
    row: int
    date_raw: Any
    reason: str
    source_cells: dict[str, Any]


@dataclass(frozen=True)
class EmployeeAttendance:
    sheet_name: str
    full_name: str | None
    name_cell: str | None
    employee_id: str | None
    header_row: int | None
    columns: dict[str, int]
    period_raw: Any
    days: tuple[AttendanceDay, ...]
    rejected_rows: tuple[RejectedRow, ...]
    totals: dict[str, AttendanceTotal]
    stored_totals: tuple[StoredTotal, ...]
    issues: tuple[ParseIssue, ...]
    attendance_bonus: Decimal | None = None

    @property
    def requires_review(self) -> bool:
        return any(i.severity != Severity.INFO for i in self.issues) or any(
            e.requires_review for day in self.days for e in day.events)


@dataclass(frozen=True)
class AttendanceWorkbook:
    source_path: str
    source_hash: str
    year: int
    month: int
    employees: tuple[EmployeeAttendance, ...]

    @property
    def requires_review(self) -> bool:
        return any(s.requires_review for s in self.employees)
