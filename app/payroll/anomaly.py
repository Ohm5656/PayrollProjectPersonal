"""Warnings retain all amounts and never change calculations."""
from decimal import Decimal

from app.domain import ReviewIssue, issue_key


def amount_warning(eid, sheet, field, current, previous):
    if current is not None and previous is not None and previous > 0 and abs(current) >= previous * Decimal(5):
        return ReviewIssue(issue_key('ANOMALY', eid, field), 'ANOMALY', eid, sheet, None, None,
                           'ยอดเปลี่ยนมากจากเดือนก่อน กรุณาตรวจสอบ', critical=False, field=field,
                           raw_text=f'{previous} → {current}')
    return None
