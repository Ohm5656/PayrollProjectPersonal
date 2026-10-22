"""Read-only detail surfaces for automation jobs and staged Excel writes."""
from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget

from app.ui.theme import apply_surface_background


class ProblemJobDetailPage(QWidget):
    back_requested = Signal()
    retry_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._job_id = None
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel('รายละเอียดงานเบื้องหลัง'); title.setProperty('role', 'sectionTitle'); layout.addWidget(title)
        self.summary = QLabel(); self.summary.setWordWrap(True); layout.addWidget(self.summary)
        form = QFormLayout()
        self.values = {key: QLabel('—') for key in ('status', 'period', 'type', 'updated', 'attempts', 'source', 'failure')}
        for key, label in (('status', 'สถานะ'), ('period', 'รอบเงินเดือน'), ('type', 'ประเภทงาน'),
                           ('updated', 'ปรับปรุงล่าสุด'), ('attempts', 'จำนวนครั้งที่พยายาม'),
                           ('source', 'ไฟล์ต้นทาง'), ('failure', 'รหัสปัญหา')):
            self.values[key].setWordWrap(True); form.addRow(label, self.values[key])
        layout.addLayout(form)
        layout.addWidget(QLabel('รายละเอียดทางเทคนิค'))
        self.technical = QTextEdit(); self.technical.setReadOnly(True); self.technical.setMaximumHeight(110)
        layout.addWidget(self.technical)
        controls = QHBoxLayout()
        self.retry = QPushButton('ลองประมวลผลงานนี้อีกครั้ง')
        self.retry.setProperty('role', 'primary')
        self.retry.setEnabled(False)
        self.retry.clicked.connect(lambda: self.retry_requested.emit(self._job_id) if self._job_id else None)
        self.back = QPushButton('กลับ')
        self.back.clicked.connect(self.back_requested)
        controls.addWidget(self.retry); controls.addWidget(self.back); controls.addStretch(); layout.addLayout(controls)

    def refresh(self, raw_job, presented, *, retry_allowed=False):
        self._job_id = presented.id
        self.summary.setText(presented.title + '\n' + presented.detail)
        values = {
            'status': presented.state_label, 'period': presented.period_label,
            'type': str(raw_job.get('job_type') or 'ไม่ระบุ'), 'updated': presented.updated_at,
            'attempts': str(raw_job.get('attempt_count') if raw_job.get('attempt_count') is not None else 'ไม่ระบุ'),
            'source': Path(raw_job.get('source_path') or '').name or 'ไม่ระบุไฟล์ต้นทาง',
            'failure': presented.failure_code or 'ไม่มีรหัสปัญหาที่บันทึกไว้',
        }
        for key, value in values.items(): self.values[key].setText(value)
        self.technical.setPlainText(raw_job.get('failure_message') or 'ไม่มีรายละเอียดเพิ่มเติมที่บันทึกไว้')
        self.retry.setEnabled(bool(retry_allowed))


class StagedWriteInspectionPage(QWidget):
    back_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel('รายการเขียน Excel ที่ต้องตรวจสอบ'); title.setProperty('role', 'sectionTitle'); layout.addWidget(title)
        warning = QLabel('หน้านี้แสดงหลักฐานแบบอ่านอย่างเดียว ระบบจะไม่เขียนทับ กู้คืน หรือลบไฟล์โดยอัตโนมัติ')
        warning.setProperty('role', 'supporting'); warning.setWordWrap(True); layout.addWidget(warning)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['รหัสรายการ', 'พบไฟล์ปลายทาง', 'สำรองข้อมูลใช้ได้', 'สถานะ'])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers); self.table.setAlternatingRowColors(True)
        apply_surface_background(self.table)
        layout.addWidget(self.table, 1)
        self.state = QLabel(); self.state.setWordWrap(True); layout.addWidget(self.state)
        back = QPushButton('กลับ'); back.clicked.connect(self.back_requested); layout.addWidget(back)

    def refresh(self, staged_writes):
        self.table.setRowCount(len(staged_writes))
        for row, item in enumerate(staged_writes):
            for column, value in enumerate((item.get('operation_id'), 'พบ' if item.get('target_exists') else 'ไม่พบ',
                                            'ใช้ได้' if item.get('backup_valid') else 'ตรวจสอบไม่ได้',
                                            item.get('classification'))):
                self.table.setItem(row, column, QTableWidgetItem(str(value)))
        self.table.resizeColumnsToContents()
        self.state.setText('พบรายการที่ต้องตรวจสอบด้วยตนเอง' if staged_writes else 'ไม่พบรายการเขียน Excel ที่ค้างตรวจสอบ')
