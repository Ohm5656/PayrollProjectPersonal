"""Embedded Settings page; actions are intentionally owned by MainWindow."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from app.ui.components import SectionContainer, StatusBadge


class SettingsPage(QScrollArea):
    """Editable configuration surface with no direct service mutations."""
    save_requested = Signal(dict)
    repair_requested = Signal()
    dirty_changed = Signal(bool)

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self._saved_values = None
        self._loading = False
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        monitoring = SectionContainer('การเฝ้าดูไฟล์')
        self.monitoring_badge = StatusBadge()
        self.monitoring_detail = QLabel()
        self.monitoring_detail.setWordWrap(True)
        self.monitoring_detail.setProperty('role', 'supporting')
        monitoring.addWidget(self.monitoring_badge)
        monitoring.addWidget(self.monitoring_detail)
        layout.addWidget(monitoring)

        workflow = SectionContainer('โฟลเดอร์ทำงาน')
        self.configuration_detail = QLabel()
        self.configuration_detail.setWordWrap(True)
        self.configuration_detail.setProperty('role', 'supporting')
        workflow.addWidget(self.configuration_detail)
        form = QFormLayout()
        self.attendance = self._path_input('โฟลเดอร์บันทึกเวลา', directory=True)
        self.payroll = self._path_input('โฟลเดอร์ผลลัพธ์เงินเดือน', directory=True)
        self.template = self._path_input('ไฟล์แม่แบบรายเดือน', directory=False)
        for label, row in (('โฟลเดอร์บันทึกเวลา', self.attendance),
                           ('โฟลเดอร์ผลลัพธ์เงินเดือน', self.payroll),
                           ('ไฟล์แม่แบบรายเดือน', self.template)):
            form.addRow(label, row)
        workflow.layout.addLayout(form)
        layout.addWidget(workflow)

        startup = SectionContainer('เริ่มพร้อม Windows')
        self.start_with_windows = QCheckBox('เปิดโปรแกรมเมื่อเข้าสู่ Windows')
        self.startup_badge = StatusBadge()
        self.startup_detail = QLabel()
        self.startup_detail.setWordWrap(True)
        self.startup_detail.setProperty('role', 'supporting')
        actions = QHBoxLayout()
        self.refresh_startup = QPushButton('ตรวจสอบสถานะอีกครั้ง')
        self.repair_startup = QPushButton('ซ่อมแซม')
        self.repair_startup.setVisible(False)
        self.refresh_startup.clicked.connect(self.refresh_status)
        self.repair_startup.clicked.connect(self.repair_requested)
        actions.addWidget(self.refresh_startup)
        actions.addWidget(self.repair_startup)
        actions.addStretch()
        startup.addWidget(self.start_with_windows)
        startup.addWidget(self.startup_badge)
        startup.addWidget(self.startup_detail)
        startup.layout.addLayout(actions)
        layout.addWidget(startup)

        safety = SectionContainer('ขอบเขตความปลอดภัย')
        safety_text = QLabel('ระบบทำงานกับไฟล์สำเนาใน test_workspace เท่านั้น ไม่เขียนไฟล์ต้นฉบับ และหน้านี้ไม่เริ่มหรือหยุดการเฝ้าดูไฟล์')
        safety_text.setWordWrap(True)
        safety_text.setProperty('role', 'supporting')
        safety.addWidget(safety_text)
        layout.addWidget(safety)

        self.message = QLabel()
        self.message.setWordWrap(True)
        self.message.setProperty('role', 'supporting')
        layout.addWidget(self.message)
        self.save = QPushButton('บันทึกการตั้งค่า')
        self.save.setProperty('role', 'primary')
        self.save.clicked.connect(self._request_save)
        layout.addWidget(self.save)
        layout.addStretch()

        for edit in (self.attendance.edit, self.payroll.edit, self.template.edit):
            edit.textChanged.connect(self._values_changed)
        self.start_with_windows.toggled.connect(self._values_changed)
        # Do not query Task Scheduler while the main shell is being created.
        # MainWindow loads this page only after the user opens Settings.

    def _path_input(self, title, *, directory):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit()
        button = QPushButton('เลือก')
        def choose():
            selected = (QFileDialog.getExistingDirectory(self, title, edit.text()) if directory
                        else QFileDialog.getOpenFileName(self, title, edit.text(), 'Excel (*.xlsx)')[0])
            if selected:
                edit.setText(selected)
        button.clicked.connect(choose)
        row.addWidget(edit)
        row.addWidget(button)
        holder.edit = edit
        holder.browse = button
        return holder

    def values(self):
        return {
            'attendance_folder': self.attendance.edit.text().strip(),
            'payroll_folder': self.payroll.edit.text().strip(),
            'template_path': self.template.edit.text().strip(),
            'start_with_windows': self.start_with_windows.isChecked(),
        }

    def is_dirty(self):
        return self._saved_values is not None and self.values() != self._saved_values

    def _values_changed(self, *_):
        if not self._loading:
            self.dirty_changed.emit(self.is_dirty())

    def load(self, *, refresh_startup=False):
        snapshot = self.model.snapshot(refresh_startup=refresh_startup)
        self._loading = True
        self.attendance.edit.setText(snapshot.attendance_folder)
        self.payroll.edit.setText(snapshot.payroll_folder)
        self.template.edit.setText(snapshot.template_path)
        self.start_with_windows.setChecked(snapshot.startup_enabled)
        self._loading = False
        self._saved_values = self.values()
        self._render_status(snapshot)
        self.message.setText('')
        self.dirty_changed.emit(False)
        return snapshot

    def refresh_status(self):
        """Refresh only the possibly expensive startup status; keep dirty edits."""
        snapshot = self.model.snapshot(refresh_startup=True)
        self._render_status(snapshot)
        return snapshot

    def _render_status(self, snapshot):
        preference = {None: 'ยังไม่ได้กำหนด', False: 'หยุดไว้', True: 'เปิดไว้'}[snapshot.watch_preference]
        self.monitoring_badge.setText(f'การเฝ้าดูไฟล์: {snapshot.monitoring_label} ({preference})')
        self.monitoring_detail.setText(snapshot.monitoring_detail)
        self.configuration_detail.setText(snapshot.configuration_detail)
        self.startup_badge.setText(snapshot.startup_label)
        self.startup_detail.setText(snapshot.startup_detail)
        self.repair_startup.setVisible(snapshot.startup_repair_available)
        self.start_with_windows.setEnabled(snapshot.startup_state not in {'UNAVAILABLE', 'INVALID_LAUNCH'})

    def _request_save(self):
        self.message.setText('')
        self.save_requested.emit(self.values())

    def operation_finished(self, message, *, success, reload=True):
        if reload:
            self.load(refresh_startup=True)
        self.message.setText(message)
        self.message.setProperty('semantic', '' if success else 'warning')
        self.message.style().unpolish(self.message)
        self.message.style().polish(self.message)

    def set_busy(self, busy):
        self.save.setEnabled(not busy)
        self.refresh_startup.setEnabled(not busy)
        self.repair_startup.setEnabled(not busy)
