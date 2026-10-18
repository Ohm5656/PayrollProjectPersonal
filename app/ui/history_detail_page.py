"""Read-only audit event detail; navigation is explicit through a signal."""
import json

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget


def display_value(value):
    if value is None:
        return 'ไม่มีข้อมูลที่บันทึกไว้'
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


class HistoryDetailPage(QWidget):
    back_requested = Signal()
    period_requested = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel('รายละเอียดประวัติการทำงาน'); self.title.setProperty('role', 'sectionTitle'); layout.addWidget(self.title)
        self.summary = QLabel(); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        self.before = self._payload('ข้อมูลก่อนดำเนินการ'); layout.addWidget(self.before)
        self.after = self._payload('ข้อมูลหลังดำเนินการ'); layout.addWidget(self.after)
        self.timeline = QTextEdit(); self.timeline.setReadOnly(True); self.timeline.setPlaceholderText('ไม่มีเหตุการณ์ของรอบนี้ที่บันทึกไว้'); layout.addWidget(self.timeline, 1)
        controls = QHBoxLayout(); self.open_period = QPushButton('เปิดดูรอบเงินเดือนนี้'); self.back = QPushButton('กลับ')
        self.open_period.clicked.connect(self._open_period); self.back.clicked.connect(self.back_requested)
        controls.addWidget(self.open_period); controls.addWidget(self.back); controls.addStretch(); layout.addLayout(controls)
        self._year = self._month = None

    @staticmethod
    def _payload(title):
        field = QTextEdit(); field.setReadOnly(True); field.setObjectName(title); field.setPlaceholderText(title); return field

    def refresh(self, event, *, employee_name=None, timeline=()):
        self._year, self._month = event.get('year'), event.get('month')
        identity = employee_name or event.get('employee_id') or 'ไม่มีข้อมูลพนักงาน'
        self.summary.setText('\n'.join((
            f"เวลา: {event['timestamp']}", f"การดำเนินการ: {event['action_label']}",
            f"ผู้ดำเนินการ: {event['actor']}", f"พนักงาน: {identity}",
            f"รอบเงินเดือน: {event['period_label']}", f"ต้นทาง: {event['source']}")))
        self.before.setPlainText(display_value(event['old_value']))
        self.after.setPlainText(display_value(event['new_value']))
        self.timeline.setPlainText('\n'.join(f"{row.timestamp} — {row.action_label}" for row in reversed(timeline)))
        self.open_period.setEnabled(self._year is not None and self._month is not None)

    def _open_period(self):
        if self._year is not None and self._month is not None:
            self.period_requested.emit(int(self._year), int(self._month))
