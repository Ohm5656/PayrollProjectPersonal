from calendar import monthrange
from datetime import date
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QCheckBox, QLabel,
                              QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QDialogButtonBox, QMessageBox)
from app.models import DayType

DAY_LABELS = {'UNKNOWN':'รอยืนยัน', 'WORKING_DAY':'วันทำงาน', 'WEEKLY_HOLIDAY':'วันหยุดประจำสัปดาห์',
              'SUBSTITUTE_HOLIDAY':'วันหยุดชดเชย', 'PUBLIC_HOLIDAY':'วันหยุดนักขัตฤกษ์',
              'COMPANY_SPECIAL_HOLIDAY':'วันหยุดพิเศษบริษัท', 'EMERGENCY_CLOSURE':'หยุดฉุกเฉิน',
              'EMPLOYEE_LEAVE':'วันลาพนักงาน'}


class CalendarReview(QDialog):
    def __init__(self, service, draft, *, employee=None, actor='user', parent=None):
        super().__init__(parent)
        self.service, self.draft, self.actor = service, draft, actor
        self.setWindowTitle('ยืนยันปฏิทินวันทำงาน')
        self.resize(700, 650)
        layout = QVBoxLayout(self)
        self.scope = QComboBox()
        if employee: self.scope.addItem('เฉพาะ ' + employee.name, employee.employee_id)
        self.scope.addItem('ทั้งบริษัท', '*')
        layout.addWidget(self.scope)
        layout.addWidget(QLabel('เลือกสถานะแต่ละวันตามปฏิทินจริง วันรอยืนยันจะยังไม่ใช้คำนวณสิทธิ'))
        weekdays = QHBoxLayout()
        self.weekdays = []
        for name in ['จันทร์','อังคาร','พุธ','พฤหัส','ศุกร์','เสาร์','อาทิตย์']:
            check = QCheckBox(name)
            self.weekdays.append(check)
            weekdays.addWidget(check)
        layout.addLayout(weekdays)
        fill = QPushButton('กำหนดวันที่เลือกเป็นวันทำงาน / วันที่เหลือเป็นวันหยุดประจำสัปดาห์')
        fill.clicked.connect(self.fill_weekdays)
        layout.addWidget(fill)
        self.table = QTableWidget(monthrange(draft.year, draft.month)[1], 4)
        self.table.setHorizontalHeaderLabels(['วันที่','สถานะ','ต้องทำงาน','ผลต่อเบี้ยขยันต้องตรวจ'])
        self.rows = []
        for row in range(self.table.rowCount()):
            day = date(draft.year, draft.month, row+1)
            self.table.setItem(row, 0, QTableWidgetItem(f'{day.day:02}/{day.month:02}/{day.year+543}'))
            combo = QComboBox()
            for kind in DayType: combo.addItem(DAY_LABELS[kind.value], kind.value)
            required, affects = QCheckBox(), QCheckBox()
            self.table.setCellWidget(row, 1, combo)
            self.table.setCellWidget(row, 2, required)
            self.table.setCellWidget(row, 3, affects)
            self.rows.append((day,combo,required,affects))
        self.scope.currentIndexChanged.connect(self.load_scope)
        self.load_scope()
        layout.addWidget(self.table)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText('เหตุผล / ที่มาของปฏิทินที่ยืนยัน')
        layout.addWidget(self.reason)
        buttons = QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def load_scope(self):
        scope = self.scope.currentData()
        for day, combo, required, affects in self.rows:
            calendar = self.service.repo.calendar(scope, day)
            combo.setCurrentIndex(combo.findData(calendar['type'] if calendar else 'UNKNOWN'))
            required.setChecked(bool(calendar and calendar['required_workday']))
            affects.setChecked(bool(calendar and calendar['affects_attendance_bonus']))

    def fill_weekdays(self):
        chosen = {n for n,check in enumerate(self.weekdays) if check.isChecked()}
        if not chosen:
            QMessageBox.warning(self, 'เลือกวันทำงาน', 'กรุณาเลือกวันทำงานก่อน')
            return
        for day,combo,required,_ in self.rows:
            working = day.weekday() in chosen
            combo.setCurrentIndex(combo.findData('WORKING_DAY' if working else 'WEEKLY_HOLIDAY'))
            required.setChecked(working)

    def persist(self):
        if not self.reason.text().strip(): raise ValueError('กรุณาระบุที่มาของปฏิทิน')
        entries = [(d,c.currentData(),r.isChecked(),a.isChecked()) for d,c,r,a in self.rows if c.currentData() != 'UNKNOWN']
        if not entries: raise ValueError('ยังไม่ได้เลือกวันเพื่อยืนยัน')
        with self.service.repo.db.transaction():
            for day,kind,required,affects in entries:
                self.service.repo.confirm_calendar(day,kind,self.reason.text(),required_workday=required,
                    affects_attendance_bonus=affects,scope=self.scope.currentData(),actor=self.actor)

    def save(self):
        try: self.persist()
        except ValueError as exc:
            QMessageBox.warning(self,'ยังบันทึกไม่ได้',str(exc))
            return
        self.accept()
