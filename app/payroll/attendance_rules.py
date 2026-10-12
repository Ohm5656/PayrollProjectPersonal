"""Detect explicit source phrases without deciding payroll consequences."""
from datetime import date
from decimal import Decimal
import re

from app.models import AttendanceEvent, DayType

LEAVE_TOKEN = re.compile(r'(?<![ก-๙])ลา(?=\s|$|\d|ป่วย|กิจ|พักร้อน|ไม่รับ|ครึ่ง)')
LATE_NOTE = re.compile(r'(?:เช็[คก]อิน.*(?:เกิน|8:36)|เข้างานสาย|ตอกบัตรเกิน)')


def suggested_holiday(text: str) -> DayType:
    if 'น้ำท่วม' in text:
        return DayType.EMERGENCY_CLOSURE
    if 'หยุดแทน' in text:
        return DayType.SUBSTITUTE_HOLIDAY
    if 'สงกรานต์' in text:
        return DayType.COMPANY_SPECIAL_HOLIDAY
    if 'วันแม่' in text or 'ปีใหม่' in text:
        return DayType.PUBLIC_HOLIDAY
    if 'วันอาทิตย์' in text:
        return DayType.WEEKLY_HOLIDAY
    return DayType.UNKNOWN


def detect_events(day: date, sheet: str, texts: dict[str, str]) -> tuple[AttendanceEvent, ...]:
    events = []
    for cell, text in texts.items():
        base = {'date': day, 'sheet': sheet, 'cell': cell, 'raw_text': text}
        leave = LEAVE_TOKEN.search(text)
        if leave or 'ใบลา' in text:
            suffix = text[leave.start():] if leave else text
            hours_match = re.search(r'ลา\s*(\d+(?:\.\d+)?)\s*ชั่วโมง', suffix)
            days_match = re.search(r'ลา\s*(\d+(?:\.\d+)?)\s*วัน', suffix)
            half_day = bool(re.search(r'ลา\s*(?:1/2|ครึ่ง)\s*วัน', suffix))
            kind = next((kind for token, kind in (
                ('ลาป่วย', 'SICK_LEAVE'), ('ลากิจ', 'PERSONAL_LEAVE'),
                ('ลาพักร้อน', 'ANNUAL_LEAVE'), ('ลาไม่รับ', 'UNPAID_LEAVE')) if token in text), 'UNKNOWN_LEAVE')
            events.append(AttendanceEvent('LEAVE', suggested_type=kind,
                hours=Decimal(hours_match[1]) if hours_match else None,
                days=Decimal('0.5') if half_day else Decimal(days_match[1]) if days_match else None, **base))
        if LATE_NOTE.search(text):
            events.append(AttendanceEvent('LATE_CHECK_IN', **base))
        if 'ออกก่อนเวลา' in text:
            events.append(AttendanceEvent('EARLY_DEPARTURE', **base))
        if 'ตัดเบี้ยเลี้ยง' in text:
            events.append(AttendanceEvent('ALLOWANCE_CUT_NOTE', **base))
        if 'ตัดเบี้ยขยัน' in text:
            events.append(AttendanceEvent('ATTENDANCE_BONUS_CUT_NOTE', **base))
        if 'หยุด' in text or 'วันอาทิตย์' in text:
            events.append(AttendanceEvent('HOLIDAY_SUGGESTION', suggested_type=suggested_holiday(text), **base))
        if 'ลืมตอกบัตร' in text or 'ไม่ตอกบัตร' in text:
            events.append(AttendanceEvent('MISSING_CLOCK_NOTE', **base))
    return tuple(events)
