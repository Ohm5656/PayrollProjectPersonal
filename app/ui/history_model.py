"""Read-only formatting for persisted audit records."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json

from app.ui.presentation import text


@dataclass(frozen=True)
class HistoryEvent:
    id: int
    timestamp: str
    action: str
    action_label: str
    actor: str
    employee_id: str | None
    year: int | None
    month: int | None
    period_label: str
    source: str
    old_value: object
    new_value: object


def thai_period(year, month):
    if year is None or month is None:
        return '—'
    months = ('มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม')
    return f'{months[int(month) - 1]} {int(year) + 543}' if 1 <= int(month) <= 12 else f'{month}/{int(year) + 543}'


def thai_timestamp(value):
    if not value:
        return '—'
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        return str(value)
    local = parsed.astimezone(timezone(timedelta(hours=7)))
    return f'{local.day:02}/{local.month:02}/{local.year + 543} {local:%H:%M}'


def decode_audit_value(value):
    if value in (None, ''):
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


class HistoryViewModel:
    def event(self, row):
        return HistoryEvent(row['id'], thai_timestamp(row.get('timestamp')), row.get('action', ''),
                            text(row.get('action', '')), row.get('actor') or '—', row.get('employee_id'), row.get('year'), row.get('month'),
                            thai_period(row.get('year'), row.get('month')), row.get('source') or '—',
                            decode_audit_value(row.get('old_value')), decode_audit_value(row.get('new_value')))

    def events(self, rows):
        return tuple(self.event(row) for row in rows)
