"""Embedded, read-only review queue; decisions remain owned by existing dialogs."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.ui.components import SectionContainer


class ReviewQueuePage(QWidget):
    issue_activated = Signal(object)
    overview_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.period = QLabel()
        self.period.setProperty('role', 'sectionTitle')
        layout.addWidget(self.period)
        self.description = QLabel('รายการที่ต้องตรวจสอบก่อนยืนยันเงินเดือน')
        self.description.setProperty('role', 'supporting')
        layout.addWidget(self.description)

        summary = QHBoxLayout()
        self.critical_card = self._metric('ต้องดำเนินการ')
        self.warning_card = self._metric('คำเตือน')
        self.visible_card = self._metric('รายการที่แสดง')
        for card in (self.critical_card, self.warning_card, self.visible_card):
            summary.addWidget(card, 1)
        layout.addLayout(summary)

        filters = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('ค้นหาพนักงานหรือรายการ...')
        self.search.setAccessibleName('ค้นหารายการรอตรวจสอบ')
        self.category = QComboBox()
        self.category.setAccessibleName('กรองประเภทปัญหา')
        self.category.addItem('ทุกประเภท', None)
        self.employee = QComboBox()
        self.employee.setAccessibleName('กรองพนักงาน')
        self.employee.addItem('พนักงานทุกคน', None)
        self.severity = QComboBox()
        self.severity.setAccessibleName('กรองระดับความสำคัญ')
        self.severity.addItem('ทั้งหมด', None)
        self.severity.addItem('ต้องดำเนินการ', 'CRITICAL')
        self.severity.addItem('คำเตือน', 'WARNING')
        for control in (self.search, self.category, self.employee, self.severity):
            filters.addWidget(control, 1)
        layout.addLayout(filters)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['พนักงาน / บริบท', 'ประเภท', 'วันที่', 'รายการ', 'สถานะ'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda *_: self.activate_current())
        layout.addWidget(self.table, 1)

        self.empty = QLabel()
        self.empty.setWordWrap(True)
        layout.addWidget(self.empty)
        buttons = QHBoxLayout()
        self.open_button = QPushButton('ตรวจสอบรายการที่เลือก')
        self.open_button.setProperty('role', 'primary')
        self.open_button.clicked.connect(self.activate_current)
        self.to_overview_button = QPushButton('ไปที่ภาพรวม')
        self.to_overview_button.clicked.connect(self.overview_requested)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.to_overview_button)
        buttons.addStretch()
        layout.addLayout(buttons)

        self._snapshot = None
        self._items = ()
        for control, signal in ((self.search, self.search.textChanged), (self.category, self.category.currentIndexChanged),
                                (self.employee, self.employee.currentIndexChanged), (self.severity, self.severity.currentIndexChanged)):
            signal.connect(self.apply_filters)

    @staticmethod
    def _metric(title):
        card = SectionContainer(title)
        card.value = QLabel('0 รายการ')
        card.value.setProperty('role', 'sectionTitle')
        card.addWidget(card.value)
        return card

    def refresh(self, snapshot):
        selected_key = self.current_issue_key()
        self._snapshot = snapshot
        self.period.setText(snapshot.period_label)
        self.critical_card.value.setText(f'{snapshot.critical_count} รายการ')
        self.warning_card.value.setText(f'{snapshot.warning_count} รายการ')
        self._replace_options(self.category, [('ทุกประเภท', None), *self._categories(snapshot)])
        self._replace_options(self.employee, [('พนักงานทุกคน', None), *[(name, employee_id) for employee_id, name in snapshot.employees]])
        self.apply_filters(selected_key=selected_key)

    @staticmethod
    def _categories(snapshot):
        return sorted({(item.category_label, item.category) for item in snapshot.items}, key=lambda item: item[0])

    @staticmethod
    def _replace_options(combo, options):
        selected = combo.currentData()
        combo.blockSignals(True)
        combo.clear()
        for label, value in options:
            combo.addItem(label, value)
        index = combo.findData(selected)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def filtered_items(self):
        if not self._snapshot:
            return ()
        needle = self.search.text().casefold().strip()
        category, employee, severity = self.category.currentData(), self.employee.currentData(), self.severity.currentData()
        return tuple(item for item in self._snapshot.items if (
            (not needle or needle in ' '.join((item.employee_name, item.category_label, item.description, item.evidence)).casefold())
            and (category is None or item.category == category)
            and (employee is None or item.employee_id == employee)
            and (severity is None or item.severity == severity)
        ))

    def apply_filters(self, *_args, selected_key=None):
        self._items = self.filtered_items()
        self.visible_card.value.setText(f'{len(self._items)} จาก {len(self._snapshot.items) if self._snapshot else 0} รายการ')
        self.table.setRowCount(len(self._items))
        for row, item in enumerate(self._items):
            values = (item.employee_name, item.category_label, item.date_label or '—', item.description, item.severity_label)
            for column, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.UserRole, item.issue)
                cell.setToolTip(item.evidence or item.source_reference)
                self.table.setItem(row, column, cell)
            if item.issue.key == selected_key:
                self.table.selectRow(row)
        has_draft = bool(self._snapshot and self._snapshot.items)
        self.empty.setVisible(not has_draft or not self._items)
        self.open_button.setEnabled(bool(self.current_issue()))
        self.to_overview_button.setVisible(not has_draft)
        if not self._snapshot or not self._snapshot.items:
            self.empty.setText('ยังไม่มีรายการรอตรวจสอบสำหรับรอบนี้ กรุณาอ่านข้อมูลจากไฟล์ Excel ก่อน')
        elif not self._items:
            self.empty.setText('ไม่พบรายการที่ตรงกับตัวกรอง')
        else:
            self.empty.setText('')

    def current_issue(self):
        current = self.table.currentItem()
        return current.data(Qt.UserRole) if current else None

    def current_issue_key(self):
        issue = self.current_issue()
        return issue.key if issue else None

    def activate_current(self):
        issue = self.current_issue()
        if issue:
            self.issue_activated.emit(issue)
