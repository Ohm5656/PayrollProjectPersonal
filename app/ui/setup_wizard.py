"""Guided first-run setup for the copies-only folder workflow."""
from pathlib import Path

from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton

from app.services.monthly_workflow import master_template_path
from app.services.windows_startup import StartupState, WindowsStartupService


class SetupWizard(QDialog):
    def __init__(self, workflow, parent=None, *, startup_service=None):
        super().__init__(parent)
        self.workflow = workflow
        self.startup_service = startup_service or WindowsStartupService()
        self.monitoring_choice_persisted = False
        self.setWindowTitle('ตั้งค่า NTP Payroll ครั้งแรก')
        layout = QFormLayout(self)
        layout.addRow(QLabel('เลือกโฟลเดอร์เพียงครั้งเดียว แล้วระบบจะเฝ้าดูไฟล์บันทึกเวลาในโฟลเดอร์นั้น'))
        existing = workflow.configuration() or {}
        self.attendance = self._path_row(layout, 'โฟลเดอร์บันทึกเวลา', existing.get('attendance_folder', ''))
        self.payroll = self._path_row(layout, 'โฟลเดอร์ผลลัพธ์เงินเดือน', existing.get('payroll_folder', ''))
        self.template = self._path_row(layout, 'แม่แบบรายเดือน', existing.get('template_path', str(master_template_path())), file=True)
        self.error = QLabel('โหมดทดสอบ: การเขียนจะทำได้เฉพาะสำเนาใน test_workspace')
        self.error.setWordWrap(True)
        layout.addRow(self.error)
        preference = getattr(getattr(workflow, 'repo', None), 'setting', lambda *_: None)('watch_enabled', None)
        self.start_monitoring = QCheckBox('เริ่มเฝ้าดูไฟล์บันทึกเวลาหลังบันทึกการตั้งค่า')
        self.start_monitoring.setChecked(preference is not False)
        self.start_monitoring.setToolTip('การเริ่มพร้อม Windows และการเฝ้าดูไฟล์เป็นคนละการตั้งค่า')
        if preference is False:
            self.start_monitoring.setEnabled(False)
            self.start_monitoring.setText('การเฝ้าดูไฟล์ถูกหยุดไว้ตามการตั้งค่าที่เลือกก่อนหน้า')
        layout.addRow(QLabel('การเฝ้าดูไฟล์'), self.start_monitoring)
        self.start_with_windows = QCheckBox('เปิดโปรแกรมอัตโนมัติเมื่อเข้าสู่ Windows')
        self.startup_status = QLabel()
        self.startup_repair = QPushButton('ซ่อมแซม')
        self.startup_repair.clicked.connect(self.repair_startup)
        startup_row = QHBoxLayout(); startup_row.addWidget(self.start_with_windows); startup_row.addWidget(self.startup_repair)
        layout.addRow(QLabel('การเริ่มทำงาน'), startup_row)
        layout.addRow('สถานะ:', self.startup_status)
        self.refresh_startup_status()
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _path_row(self, layout, title, value, *, file=False):
        edit = QLineEdit(value)
        button = QPushButton('เลือก')
        def choose():
            selected = QFileDialog.getOpenFileName(self, title, edit.text(), 'Excel (*.xlsx)')[0] if file else QFileDialog.getExistingDirectory(self, title, edit.text())
            if selected: edit.setText(selected)
        button.clicked.connect(choose)
        row = QHBoxLayout(); row.addWidget(edit); row.addWidget(button)
        layout.addRow(title, row)
        return edit

    def save(self):
        try:
            self.workflow.configure(self.attendance.text(), self.payroll.text(), self.template.text())
        except Exception as exc:
            self.error.setText(str(exc))
            return
        # A first run may set an explicit intent, but it must never overwrite
        # an existing pause/enable choice restored from persisted settings.
        repo = getattr(self.workflow, 'repo', None)
        if repo is not None and repo.setting('watch_enabled', None) is None:
            repo.set_setting('watch_enabled', self.start_monitoring.isChecked())
            self.monitoring_choice_persisted = True
        status = self.startup_service.validate()
        if self.start_with_windows.isChecked() and not status.enabled:
            result = self.startup_service.install()
            if not result.success:
                self.error.setText('บันทึกโฟลเดอร์แล้ว แต่ไม่สามารถตั้งค่าให้เปิดพร้อม Windows ได้ กรุณาตรวจสอบการตั้งค่าแล้วลองใหม่')
                self.refresh_startup_status()
                return
        elif not self.start_with_windows.isChecked() and status.installed:
            result = self.startup_service.remove()
            if not result.success:
                self.error.setText('บันทึกโฟลเดอร์แล้ว แต่ไม่สามารถปิดการเริ่มพร้อม Windows ได้ กรุณาลองใหม่')
                self.refresh_startup_status()
                return
        self.accept()

    def refresh_startup_status(self):
        status = self.startup_service.validate()
        labels = {
            StartupState.VALID: 'เปิดใช้งานแล้ว',
            StartupState.NOT_INSTALLED: 'ปิดใช้งาน',
            StartupState.NEEDS_REPAIR: 'ต้องแก้ไขการตั้งค่า',
            StartupState.INVALID_LAUNCH: 'ไม่พบไฟล์สำหรับเริ่มโปรแกรม',
            StartupState.UNAVAILABLE: 'ไม่สามารถตรวจสอบ Task Scheduler ได้',
            StartupState.ERROR: 'ตรวจสอบการเริ่มพร้อม Windows ไม่สำเร็จ',
        }
        # A broken owned task still represents an enabled user intent.  Keep
        # it checked so Save does not silently remove a task that needs an
        # explicit Repair action; unchecking remains an explicit disable.
        self.start_with_windows.setChecked(status.installed)
        self.startup_status.setText(labels[status.state])
        self.startup_repair.setVisible(status.state == StartupState.NEEDS_REPAIR)
        self.start_with_windows.setEnabled(status.state not in {StartupState.UNAVAILABLE, StartupState.INVALID_LAUNCH})
        return status

    def repair_startup(self):
        result = self.startup_service.repair()
        if not result.success:
            self.error.setText('ไม่สามารถซ่อมแซมการเริ่มพร้อม Windows ได้ กรุณาตรวจสอบการตั้งค่าแล้วลองใหม่')
        self.refresh_startup_status()
