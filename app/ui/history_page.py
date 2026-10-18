"""Bounded database-backed audit history page."""
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.ui.history_model import HistoryViewModel


class HistoryPage(QWidget):
    event_activated = Signal(int)

    def __init__(self, repository, parent=None, *, page_size=50):
        super().__init__(parent)
        self.repository, self.page_size = repository, page_size
        self.model = HistoryViewModel()
        self._cursors, self._page, self._events = [None], 0, ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel('ประวัติการทำงาน')
        self.title.setProperty('role', 'sectionTitle')
        layout.addWidget(self.title)
        self.description = QLabel('ค้นหาและตรวจสอบการดำเนินการย้อนหลังจากข้อมูลที่บันทึกไว้')
        self.description.setProperty('role', 'supporting')
        layout.addWidget(self.description)
        filters = QHBoxLayout()
        self.year, self.month, self.action, self.actor = (QComboBox() for _ in range(4))
        for control, label in ((self.year, 'ปี'), (self.month, 'เดือน'), (self.action, 'ประเภทการดำเนินการ'), (self.actor, 'ผู้ดำเนินการ')):
            control.setAccessibleName(label)
            filters.addWidget(control, 1)
            control.currentIndexChanged.connect(self.reset_and_refresh)
        layout.addLayout(filters)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['วันที่/เวลา', 'การดำเนินการ', 'รอบเงินเดือน', 'ผู้ดำเนินการ'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.itemDoubleClicked.connect(lambda *_: self.activate_current())
        self.table.installEventFilter(self)
        layout.addWidget(self.table, 1)
        self.state = QLabel()
        self.state.setWordWrap(True)
        layout.addWidget(self.state)
        controls = QHBoxLayout()
        self.previous = QPushButton('ก่อนหน้า')
        self.next = QPushButton('ถัดไป')
        self.inspect = QPushButton('ดูรายละเอียดรายการที่เลือก')
        self.inspect.setProperty('role', 'primary')
        self.previous.clicked.connect(self.previous_page)
        self.next.clicked.connect(self.next_page)
        self.inspect.clicked.connect(self.activate_current)
        for button in (self.previous, self.next, self.inspect): controls.addWidget(button)
        controls.addStretch()
        layout.addLayout(controls)
        self._load_options()
        self.refresh()

    def _load_options(self):
        values = self.repository.audit_filter_values()
        for combo, choices in ((self.year, values['years']), (self.action, values['actions']), (self.actor, values['actors'])):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem('ทั้งหมด', None)
            for value in choices: combo.addItem(str(value), value)
            combo.blockSignals(False)
        self.month.blockSignals(True)
        self.month.clear(); self.month.addItem('ทุกเดือน', None)
        for month in range(1, 13): self.month.addItem(str(month), month)
        self.month.blockSignals(False)

    def filters(self):
        return {'year': self.year.currentData(), 'month': self.month.currentData(),
                'action': self.action.currentData(), 'actor': self.actor.currentData()}

    def reset_and_refresh(self, *_):
        self._cursors, self._page = [None], 0
        self.refresh()

    def refresh(self):
        try:
            rows = self.repository.audit_events(limit=self.page_size, before_id=self._cursors[self._page], **self.filters())
            self._events = self.model.events(rows)
            total = self.repository.audit_event_count(**self.filters())
            self._render(total)
        except Exception:
            self._events = ()
            self.table.setRowCount(0)
            self.state.setText('ไม่สามารถอ่านประวัติการดำเนินการได้ โปรดลองใหม่')
            self.previous.setEnabled(False); self.next.setEnabled(False); self.inspect.setEnabled(False)

    def _render(self, total):
        self.table.setRowCount(len(self._events))
        for row, event in enumerate(self._events):
            for column, value in enumerate((event.timestamp, event.action_label, event.period_label, event.actor)):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, event.id)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        if not total:
            self.state.setText('ยังไม่มีประวัติการดำเนินการ' if not any(self.filters().values()) else 'ไม่พบประวัติตามเงื่อนไขที่เลือก')
        else:
            start = self._page * self.page_size + 1
            self.state.setText(f'แสดง {start}–{start + len(self._events) - 1} จาก {total} รายการ')
        self.previous.setEnabled(self._page > 0)
        self.next.setEnabled(len(self._events) == self.page_size and (self._page + 1) * self.page_size < total)
        self.inspect.setEnabled(bool(self._events))

    def next_page(self):
        if not self._events: return
        self._cursors.append(self._events[-1].id); self._page += 1; self.refresh()

    def previous_page(self):
        if self._page:
            self._page -= 1; self._cursors.pop(); self.refresh()

    def current_event_id(self):
        item = self.table.currentItem()
        return item.data(Qt.UserRole) if item else None

    def activate_current(self):
        event_id = self.current_event_id()
        if event_id is not None: self.event_activated.emit(event_id)

    def eventFilter(self, watched, event):
        if watched is self.table and event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.activate_current()
            return True
        return super().eventFilter(watched, event)
