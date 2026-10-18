"""Embedded, bounded Problems and Recovery dashboard."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.services.automation_job_service import AutomationJobState


class ProblemsPage(QWidget):
    job_selected = Signal(str)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model, self.snapshot_data = model, None
        self._jobs = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel('ปัญหาและการกู้คืน')
        self.title.setProperty('role', 'sectionTitle')
        layout.addWidget(self.title)
        self.description = QLabel('ตรวจสอบสถานะงานเบื้องหลังและข้อมูลที่ต้องดำเนินการอย่างปลอดภัย')
        self.description.setProperty('role', 'supporting')
        self.description.setWordWrap(True)
        layout.addWidget(self.description)

        cards = QGridLayout()
        self.cards = {}
        for index, key in enumerate(('monitoring', 'jobs', 'configuration', 'writes')):
            card = QGroupBox()
            card_layout = QVBoxLayout(card)
            label = QLabel(); label.setProperty('role', 'cardTitle')
            detail = QLabel(); detail.setWordWrap(True); detail.setProperty('role', 'supporting')
            card_layout.addWidget(label); card_layout.addWidget(detail)
            cards.addWidget(card, index // 2, index % 2)
            self.cards[key] = (card, label, detail)
        layout.addLayout(cards)

        controls = QHBoxLayout()
        controls.addWidget(QLabel('แสดงงาน'))
        self.filter = QComboBox()
        for label, state in (
            ('ทั้งหมด (รายการล่าสุด)', None), ('มีปัญหา', AutomationJobState.FAILED),
            ('รอตรวจสอบ', AutomationJobState.REVIEW_REQUIRED), ('กำลังประมวลผล', AutomationJobState.PROCESSING),
            ('เสร็จแล้ว', AutomationJobState.COMPLETED), ('รอประมวลผล', AutomationJobState.PENDING),
        ):
            self.filter.addItem(label, state)
        self.filter.setAccessibleName('ตัวกรองสถานะงาน')
        self.filter.currentIndexChanged.connect(self._render_jobs)
        self.refresh_button = QPushButton('รีเฟรช')
        self.refresh_button.clicked.connect(self.refresh)
        controls.addWidget(self.filter); controls.addWidget(self.refresh_button); controls.addStretch()
        layout.addLayout(controls)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['สถานะ', 'รายละเอียด', 'รอบเงินเดือน', 'ปรับปรุงล่าสุด', 'ประเภทงาน'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda *_: self.open_current())
        layout.addWidget(self.table, 1)
        self.scope = QLabel('แสดงเฉพาะรายการงานล่าสุดแบบจำกัดจำนวน')
        self.scope.setProperty('role', 'supporting')
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        self.open_detail = QPushButton('ดูรายละเอียดรายการที่เลือก')
        self.open_detail.setProperty('role', 'primary')
        self.open_detail.clicked.connect(self.open_current)
        layout.addWidget(self.open_detail)
        self.refresh()

    def refresh(self):
        self.snapshot_data = self.model.snapshot(limit=50)
        self._jobs = self.snapshot_data.recent_jobs
        for key in ('monitoring', 'jobs', 'configuration', 'writes'):
            status = getattr(self.snapshot_data, key)
            card, label, detail = self.cards[key]
            label.setText(status.label)
            detail.setText(status.detail)
            card.setProperty('semantic', 'warning' if status.requires_action else 'neutral')
        self._render_jobs()

    def _render_jobs(self, *_):
        state = self.filter.currentData()
        visible = tuple(job for job in self._jobs if state is None or job.state == state)
        self.table.setRowCount(len(visible))
        for row, job in enumerate(visible):
            for column, value in enumerate((job.state_label, job.title, job.period_label, job.updated_at, job.state)):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, job.id)
                item.setToolTip(job.detail)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        if visible:
            self.scope.setText(f'แสดง {len(visible)} รายการจากงานล่าสุดที่ระบบอ่านได้')
        else:
            self.scope.setText('ไม่พบปัญหาในรายการงานล่าสุด' if state in (None, AutomationJobState.FAILED)
                               else 'ไม่พบรายการตามตัวกรองที่เลือก')
        self.open_detail.setEnabled(bool(visible))

    def current_job_id(self):
        item = self.table.currentItem()
        return item.data(Qt.UserRole) if item else None

    def open_current(self):
        job_id = self.current_job_id()
        if job_id:
            self.job_selected.emit(job_id)
