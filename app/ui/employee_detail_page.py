"""Read-only employee payroll evidence page with explicit edit requests."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.domain import FINAL_STATES, THAI_FIELDS
from app.ui.components import SectionContainer
from app.ui.presentation import text
from app.ui.theme import apply_surface_background


def money(value):
    return '—' if value is None else f'{value:,.2f}'


def value_category(category):
    return {
        'AUTO_CALCULATED': 'คำนวณจากข้อมูล',
        'RECURRING': 'ค่าประจำ',
        'MANUAL': 'รายการที่ต้องยืนยัน',
        'REVIEW_REQUIRED': 'รอตรวจสอบ',
    }.get(str(category), text(category))


class EmployeeDetailPage(QWidget):
    back_requested = Signal()
    field_review_requested = Signal(str)
    profile_requested = Signal()
    calendar_requested = Signal()
    zero_review_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        self.title = QLabel('รายละเอียดพนักงาน')
        self.title.setProperty('role', 'sectionTitle')
        layout.addWidget(self.title)
        self.context = QLabel()
        self.context.setProperty('role', 'supporting')
        self.context.setWordWrap(True)
        layout.addWidget(self.context)

        self.status = SectionContainer('สถานะการตรวจสอบ')
        self.status_text = QLabel()
        self.status.addWidget(self.status_text)
        layout.addWidget(self.status)

        self.table = QTableWidget(0, 10)
        self.table.setHorizontalHeaderLabels(['รายการ', 'ยอดสุดท้าย', 'ประเภทข้อมูล', 'ยืนยันแล้ว', 'ต้นทาง', 'เดือนก่อน', 'ฉบับร่าง', 'ผู้ใช้แก้ไข', 'เหตุผล', 'หลักฐานต้นทาง'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        apply_surface_background(self.table)
        self.table.cellDoubleClicked.connect(lambda row, _column: self.open_field(row))
        layout.addWidget(self.table, 1)

        actions = QHBoxLayout()
        self.review_field = QPushButton('ตรวจสอบรายการที่เลือก')
        self.review_field.setProperty('role', 'primary')
        self.review_field.clicked.connect(lambda: self.open_field(self.table.currentRow()))
        self.profile = QPushButton('ค่าประจำพนักงาน')
        self.profile.clicked.connect(self.profile_requested)
        self.calendar = QPushButton('ตรวจสอบปฏิทิน')
        self.calendar.clicked.connect(self.calendar_requested)
        self.zero_review = QPushButton('ยืนยันรายการพิเศษเป็นศูนย์')
        self.zero_review.clicked.connect(self.zero_review_requested)
        self.back = QPushButton('กลับ')
        self.back.clicked.connect(self.back_requested)
        for button in (self.review_field, self.profile, self.calendar, self.zero_review, self.back):
            actions.addWidget(button)
        layout.addLayout(actions)
        self._employee = None
        self._read_only = True

    def refresh(self, draft, employee, run):
        self._employee = employee
        state = str(run['state']) if run else 'NO_DRAFT'
        self._read_only = state in FINAL_STATES
        self.title.setText(f'รายละเอียดพนักงาน — {employee.name}')
        self.context.setText(f'รอบ {draft.month}/{draft.year + 543} · {employee.sheet or "ไม่มีข้อมูลชีต"}')
        self.status_text.setText('พร้อมตรวจสอบ' if employee.ready else f'มีรายการรอตรวจสอบ {len(employee.issues)} รายการ')
        fields = list(employee.values)
        self.table.setRowCount(len(fields))
        for row, field in enumerate(fields):
            value = employee.values[field]
            cells = (
                THAI_FIELDS.get(field, field), money(value.final_value), value_category(value.category),
                'ยืนยันแล้ว' if value.confirmed else 'ยังไม่ยืนยัน', money(value.source_value), money(value.previous_value),
                money(value.draft_value), money(value.user_override), text(value.reason) if value.reason else '—',
                value.source_reference or '—',
            )
            for column, cell_text in enumerate(cells):
                cell = QTableWidgetItem(cell_text)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                cell.setData(Qt.UserRole, field)
                if column in {1, 4, 5, 6, 7}:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(row, column, cell)
        self.table.resizeColumnsToContents()
        enabled = not self._read_only
        self.review_field.setEnabled(enabled)
        self.profile.setEnabled(enabled and bool(employee.employee_id))
        self.calendar.setEnabled(enabled)
        self.zero_review.setEnabled(enabled)

    def open_field(self, row):
        if self._read_only or row < 0:
            return
        item = self.table.item(row, 0)
        if item:
            self.field_review_requested.emit(item.data(Qt.UserRole))
