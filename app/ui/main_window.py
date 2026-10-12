from datetime import datetime, timedelta, timezone
from pathlib import Path
import logging
import shutil
from uuid import uuid4

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.domain import FINAL_STATES, PayrollState, THAI_FIELDS, decimal_value
from app.excel.workbook_source import discover_workbooks, file_hash, filename_month
from app.safety import REFERENCE_ROOT, TEST_ROOT, development_target
from app.ui.review import EmployeeReview, ReviewCenter, money
from app.ui.presentation import text,error_text

STATE_TEXT = {'DRAFT': 'ฉบับร่าง', 'NEEDS_REVIEW': 'ต้องตรวจสอบ', 'READY': 'พร้อมยืนยัน',
              'CONFIRMED': 'ยืนยันเงินเดือนแล้ว', 'WRITTEN': 'บันทึกลง Excel แล้ว', 'LOCKED': 'ปิดรอบเดือนแล้ว'}


class JobSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class Job(QRunnable):
    def __init__(self, work):
        super().__init__()
        self.work = work
        self.signals = JobSignals()

    def run(self):
        try:
            self.signals.finished.emit(self.work())
        except Exception as exc:
            logging.getLogger('ntp').exception('Operation failed')
            self.signals.failed.emit(str(exc))


class MainWindow(QMainWindow):
    state_changed = Signal(str)
    notify = Signal(str, str)
    exit_when_idle = Signal()
    watched_result = Signal(object)
    watched_error = Signal(str)

    def __init__(self, service, *, writer=None, parent=None):
        super().__init__(parent)
        self.service, self.writer = service, writer
        self.draft, self.run, self.busy, self.tray = None, None, False, None
        self.watcher = None
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.jobs = []
        self.exit_pending = False
        self.watched_result.connect(self.receive_watched_result)
        self.watched_error.connect(self.receive_watched_error)
        self.setWindowTitle('NTP Payroll Assistant')
        self.resize(1130, 720)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        title = QLabel('NTP Payroll Assistant')
        title.setStyleSheet('font-size:24px; font-weight:600')
        layout.addWidget(title)
        layout.addWidget(QLabel('โหมดทดสอบ — เตรียมและบันทึกข้อมูลลงไฟล์สำเนาเท่านั้น'))
        layout.addWidget(QLabel('เริ่มต้น: 1 เลือกเดือน  •  2 เลือกปี  •  3 เลือกไฟล์บันทึกเวลา  •  4 เลือกไฟล์เงินเดือน  •  5 อ่านข้อมูล'))
        now = datetime.now(timezone(timedelta(hours=7)))
        period = QHBoxLayout()
        self.year = QSpinBox()
        self.year.setRange(2000, 2399)
        self.year.setValue(now.year)
        self.month = QSpinBox()
        self.month.setRange(1, 12)
        self.month.setValue(now.month)
        period.addWidget(QLabel('เดือน'))
        period.addWidget(self.month)
        period.addWidget(QLabel('ปี ค.ศ.'))
        period.addWidget(self.year)
        self.actor = QLineEdit(service.repo.setting('actor', 'ผู้ใช้'))
        period.addWidget(QLabel('ผู้ตรวจสอบ'))
        period.addWidget(self.actor)
        self.copy_button = QPushButton('เตรียมสำเนาข้อมูลเดือนที่เลือก')
        self.copy_button.clicked.connect(self.prepare_copies)
        period.addWidget(self.copy_button)
        layout.addLayout(period)
        sources = QFormLayout()
        self.attendance = QLineEdit(service.repo.setting('attendance_path', ''))
        self.payroll = QLineEdit(service.repo.setting('payroll_path', ''))
        for key, widget, label_text in [('attendance', self.attendance, 'ไฟล์บันทึกเวลาสำเนา'), ('payroll', self.payroll, 'ไฟล์เงินเดือนสำเนา')]:
            widget.setReadOnly(True)
            row = QHBoxLayout()
            row.addWidget(widget)
            browse = QPushButton('เลือกไฟล์')
            browse.clicked.connect(lambda checked=False, k=key: self.choose_file(k))
            row.addWidget(browse)
            sources.addRow(label_text, row)
        layout.addLayout(sources)
        cards = QGridLayout()
        self.cards = {}
        for index, (key, text) in enumerate([('attendance', 'ข้อมูลเวลา'), ('save', 'บันทึกไฟล์ล่าสุด'),
            ('employees', 'พนักงาน'), ('issues', 'รายการที่ต้องตรวจสอบ'), ('state', 'สถานะเงินเดือน')]):
            box = QGroupBox(text)
            box_layout = QVBoxLayout(box)
            value = QLabel('—')
            value.setWordWrap(True)
            box_layout.addWidget(value)
            cards.addWidget(box, 0, index)
            self.cards[key] = value
        layout.addLayout(cards)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['ชื่อ', 'OT', 'เบี้ยเลี้ยง', 'ค่าเดินทาง', 'เบี้ยขยัน', 'รายการพิเศษ', 'สถานะ'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.cellDoubleClicked.connect(self.employee_review)
        layout.addWidget(self.table)
        actions = QHBoxLayout()
        self.read_button = QPushButton('อ่านข้อมูล / คำนวณฉบับร่าง')
        self.read_button.clicked.connect(self.read_draft)
        self.review_button = QPushButton('รายการที่ต้องตรวจสอบ')
        self.review_button.clicked.connect(self.review)
        self.profile_button = QPushButton('ค่าประจำพนักงาน')
        self.profile_button.clicked.connect(self.profile_dialog)
        self.confirm_button = QPushButton('ยืนยันเงินเดือน')
        self.confirm_button.clicked.connect(self.confirm)
        self.write_button = QPushButton('บันทึกเงินเดือนลงไฟล์สำเนา')
        self.write_button.clicked.connect(self.write)
        self.slips_button = QPushButton('ใบเงินเดือนรายบุคคล')
        self.slips_button.clicked.connect(self.payslips)
        for widget in (self.read_button, self.review_button, self.profile_button, self.confirm_button, self.write_button, self.slips_button):
            actions.addWidget(widget)
        layout.addLayout(actions)
        second = QHBoxLayout()
        advanced=QGroupBox('ตัวเลือกเพิ่มเติม')
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_body=QWidget()
        advanced_body.setVisible(False)
        advanced.toggled.connect(advanced_body.setVisible)
        advanced_layout=QVBoxLayout(advanced)
        advanced_layout.addWidget(advanced_body)
        second=QHBoxLayout(advanced_body)
        for text, callback in [('ดูประวัติ', self.history), ('ตั้งค่า', self.settings),
                               ('ทดสอบสำเนาเฉพาะคนที่เลือก', self.single_employee_test),
                               ('ปฏิทินวันทำงาน', self.calendar_review),
                               ('เปิดรอบเดือนที่ยืนยันแล้วใหม่', self.reopen), ('ปิดรอบเดือน', self.lock)]:
            button = QPushButton(text)
            button.clicked.connect(callback)
            second.addWidget(button)
        layout.addWidget(advanced)
        self.statusBar().showMessage('เลือกเดือนและเตรียมสำเนาข้อมูลเพื่อเริ่มทดสอบ')
        self.update_buttons()

    def configure_watcher(self):
        if self.watcher:
            if not self.watcher.stop():
                self.statusBar().showMessage('กำลังรอการอ่านไฟล์ครั้งก่อนให้เสร็จ')
                return
            self.watcher = None
        if not self.service.repo.setting('watch_enabled', False) or not self.attendance.text() or not self.payroll.text():
            return
        from app.services.watcher import AttendanceWatcher
        try:
            path = development_target(Path(self.attendance.text()))
            payroll = development_target(Path(self.payroll.text()))
            year, month = self.year.value(), self.month.value()
            initial = self.run['source_hash'] if self.run and self.run['source_path'] == str(path) and self.run['payroll_path'] == str(payroll) else None
            self.watcher = AttendanceWatcher(path,
                lambda p: self.service.prepare(p, payroll, year=year, month=month),
                initial_hash=initial, on_result=self.watched_result.emit, notify=self.watched_error.emit)
            self.watcher.start()
        except Exception as exc:
            self.receive_watched_error(str(exc))

    def receive_watched_result(self, result):
        if Path(result['draft'].source_path) != Path(self.attendance.text()): return
        if Path(result['draft'].payroll_path) != Path(self.payroll.text()): return
        # Refresh current persisted revision, since a manual job may have
        # completed after the watcher result was queued on the GUI thread.
        result = dict(result)
        result['run'], result['draft'] = self.service.current(result['draft'].year, result['draft'].month)
        self.show_result(result)
        if not result.get('unchanged') and not result.get('difference'):
            self.notify.emit('อ่านบันทึกเวลาที่บันทึกแล้ว', 'ฉบับร่างพร้อมตรวจสอบ')
        if self.exit_pending and not self.busy: self.exit_when_idle.emit()

    def receive_watched_error(self, message):
        self.state_changed.emit('error')
        self.statusBar().showMessage(message)
        self.notify.emit('อ่านบันทึกเวลาไม่สำเร็จ', message)
        if self.exit_pending and not self.busy: self.exit_when_idle.emit()

    def update_buttons(self):
        state = self.run['state'] if self.run else None
        self.read_button.setEnabled(not self.busy)
        self.copy_button.setEnabled(not self.busy)
        self.review_button.setEnabled(bool(self.draft) and not self.busy and state not in FINAL_STATES)
        self.profile_button.setEnabled(bool(self.draft) and not self.busy and state not in FINAL_STATES)
        self.confirm_button.setEnabled(state == PayrollState.READY and not self.busy)
        self.write_button.setEnabled(self.writer is not None and state == PayrollState.CONFIRMED and not self.busy)
        self.slips_button.setEnabled(bool(self.draft) and not self.busy)
        self.month.setEnabled(not self.busy)
        self.year.setEnabled(not self.busy)

    def clear_source_selection(self):
        self.run,self.draft=None,None
        self.table.setRowCount(0)
        for card in self.cards.values(): card.setText('—')
        self.update_buttons()

    def work(self, task, success):
        if self.busy:
            return
        self.busy = True
        self.update_buttons()
        self.state_changed.emit('processing')
        job = Job(task)
        self.jobs.append(job)
        def done(result):
            self.busy = False
            self.jobs.remove(job)
            success(result)
            self.update_buttons()
            if self.exit_pending:
                self.exit_when_idle.emit()
        def failed(message):
            self.busy = False
            self.jobs.remove(job)
            self.update_buttons()
            self.state_changed.emit('error')
            self.statusBar().showMessage(error_text(message))
            self.notify.emit('ดำเนินการไม่สำเร็จ', error_text(message))
            if self.exit_pending:
                self.exit_when_idle.emit()
        job.signals.finished.connect(done)
        job.signals.failed.connect(failed)
        self.pool.start(job)

    def choose_file(self, key):
        if self.busy: return
        path, _ = QFileDialog.getOpenFileName(self, 'เลือกไฟล์สำเนา', str(TEST_ROOT), 'Excel (*.xlsx)')
        if not path:
            return
        try:
            development_target(Path(path))
        except RuntimeError:
            QMessageBox.warning(self, 'เลือกไฟล์สำเนา', 'กรุณาเลือกไฟล์สำเนาที่อยู่ในโฟลเดอร์ทดสอบ')
            return
        getattr(self, key).setText(path)
        self.service.repo.set_setting(key + '_path', path)
        self.clear_source_selection()
        self.configure_watcher()

    def prepare_copies(self):
        month = self.month.value()
        def copy():
            paths = {}
            folder = TEST_ROOT / 'manual_sessions' / str(uuid4())
            for kind in ('attendance', 'payroll'):
                files = [p for p in discover_workbooks(REFERENCE_ROOT / kind) if filename_month(p) == month]
                if len(files) != 1:
                    raise ValueError('ไม่พบไฟล์ต้นทางเพียงไฟล์เดียวสำหรับเดือนที่เลือก')
                destination = development_target(folder / kind / files[0].name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(files[0], destination)
                if file_hash(files[0]) != file_hash(destination):
                    raise RuntimeError('Copy verification failed')
                paths[kind] = str(destination)
            return paths
        def loaded(paths):
            for kind, path in paths.items():
                getattr(self, kind).setText(path)
                self.service.repo.set_setting(kind + '_path', path)
            self.clear_source_selection()
            self.statusBar().showMessage('เตรียมสำเนาแล้ว กดอ่านข้อมูลเพื่อเริ่มตรวจสอบ')
            self.configure_watcher()
        self.work(copy, loaded)

    def read_draft(self):
        if not self.attendance.text() or not self.payroll.text():
            self.statusBar().showMessage('กรุณาเลือกไฟล์สำเนาทั้งสองไฟล์')
            return
        attendance_path, payroll_path = Path(self.attendance.text()), Path(self.payroll.text())
        year, month = self.year.value(), self.month.value()
        self.service.repo.set_setting('actor', self.actor.text())
        self.work(lambda: self.service.prepare(attendance_path, payroll_path, force=True, year=year, month=month), self.show_result)

    def show_result(self, result):
        self.run, self.draft = result['run'], result['draft']
        self.render()
        if result.get('difference'):
            self.notify.emit('พบการแก้ไขบันทึกเวลาหลังยืนยันเงินเดือน', 'เดือนที่ยืนยันแล้วคงข้อมูลเดิม กรุณาดูส่วนต่างก่อนเปิดเดือนใหม่')

    def render(self):
        draft = self.draft
        if not draft:
            return
        self.year.setValue(draft.year)
        self.month.setValue(draft.month)
        self.cards['attendance'].setText(Path(draft.source_path).name)
        source=Path(draft.source_path)
        saved=datetime.fromtimestamp(source.stat().st_mtime,timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S') if source.is_file() else 'ไม่พบไฟล์สำเนา'
        self.cards['save'].setText(saved)
        self.cards['employees'].setText(str(sum(bool(e.employee_id) for e in draft.employees)))
        self.cards['issues'].setText(str(len(draft.issues)))
        self.cards['state'].setText(STATE_TEXT.get(self.run['state'], self.run['state']))
        self.table.setRowCount(len(draft.employees))
        for row, employee in enumerate(draft.employees):
            def amount(field):
                return employee.values[field].final_value if field in employee.values else None
            critical = any(i.critical for i in employee.issues)
            status = 'พร้อม' if employee.ready else 'มีข้อผิดพลาด' if any(i.kind.startswith('SOURCE_') and i.critical for i in employee.issues) else 'ต้องตรวจสอบ' if employee.issues else 'ยังไม่มีข้อมูล'
            texts = [employee.name, f'{money(amount("normal_ot"))} / {money(amount("holiday_ot"))}',
                money(amount('allowance')), money(amount('travel')), money(amount('bonus')),
                str(sum(v.final_value not in (None, 0) for k, v in employee.values.items() if k not in {'travel','allowance','bonus','base','normal_ot','holiday_ot','holiday_days'})), status]
            for column, text in enumerate(texts):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.state_changed.emit('review' if self.run['state'] == PayrollState.NEEDS_REVIEW else 'ready')
        self.statusBar().showMessage(f'เดือน {draft.month}/{draft.year + 543} — {STATE_TEXT[self.run["state"]]}')
        self.update_buttons()

    def review(self):
        if self.draft:
            ReviewCenter(self.service, self.draft, actor=self.actor.text(), on_changed=self.read_draft, parent=self).exec()

    def employee_review(self, row, column=0):
        if not self.draft or self.busy or self.run['state'] in FINAL_STATES:
            return
        employee = self.draft.employees[row]
        if employee.employee_id:
            EmployeeReview(self.service, self.draft, employee, actor=self.actor.text(), on_changed=self.read_draft, parent=self).exec()
        else:
            self.review()

    def selected_employee(self):
        if not self.draft or self.table.currentRow() < 0:
            return None
        return self.draft.employees[self.table.currentRow()]

    def profile_dialog(self):
        employee = self.selected_employee()
        if not employee or not employee.employee_id:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('ค่าประจำ — ' + employee.name)
        layout = QFormLayout(dialog)
        profile = self.service.repo.profile(employee.employee_id)
        controls = {}
        for key, text in [('base_salary', 'เงินเดือน/ค่าจ้าง'), ('attendance_bonus_default', 'เบี้ยขยันเมื่อผ่านเงื่อนไข'),
                          ('phone_allowance', 'ค่าโทรศัพท์'), ('position_allowance', 'ค่าตำแหน่ง'), ('housing', 'ค่าที่พักประจำ')]:
            widget = QLineEdit(profile.get(key) or '')
            controls[key] = widget
            layout.addRow(text, widget)
        required = QCheckBox('ต้องใช้ข้อมูลเวลาประจำเดือน')
        required.setChecked(bool(profile.get('attendance_required', 1)))
        layout.addRow(required)
        layout.addRow(QLabel('ค่าประจำที่ยืนยันจะเสนอใช้ตามการตั้งค่านี้ในเดือนถัดไป'))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            try:
                self.service.repo.confirm_profile(employee.employee_id, actor=self.actor.text(),
                    attendance_required=required.isChecked(), **{k: decimal_value(w.text()) for k, w in controls.items()})
                self.read_draft()
            except ValueError as exc:
                QMessageBox.warning(self, 'ข้อมูลไม่ถูกต้อง', str(exc))

    def calendar_review(self):
        if not self.draft or self.busy or self.run['state'] in FINAL_STATES: return
        from app.ui.calendar_review import CalendarReview
        if CalendarReview(self.service,self.draft,employee=self.selected_employee(),actor=self.actor.text(),parent=self).exec() == QDialog.Accepted:
            self.read_draft()

    def confirm(self):
        if not self.run:
            return
        revision = self.run['revision']
        self.work(lambda: self.service.confirm(self.draft.year, self.draft.month, actor=self.actor.text(), expected_revision=revision),
                  lambda run: self.refresh())

    def refresh(self):
        if self.draft:
            self.run, self.draft = self.service.current(self.draft.year, self.draft.month)
            self.render()

    def write(self):
        if self.writer and self.run:
            year, month, actor = self.draft.year, self.draft.month, self.actor.text()
            self.work(lambda: self.writer.write_month(year, month, actor=actor), lambda result: self.refresh())

    def single_employee_test(self):
        employee=self.selected_employee()
        if not self.writer or not employee or not employee.ready or self.busy or self.run['state'] in FINAL_STATES:
            self.statusBar().showMessage('เลือกพนักงานที่ตรวจสอบครบแล้ว ในเดือนที่ยังไม่ยืนยัน')
            return
        dialog=QDialog(self)
        dialog.setWindowTitle('ทดสอบสำเนารายคน — '+employee.name)
        layout=QVBoxLayout(dialog)
        layout.addWidget(QLabel('จะบันทึกแถวเงินเดือนและสลิปของ '+employee.name+' ในไฟล์สำเนาที่เลือก'))
        path=QLabel(self.payroll.text())
        path.setWordWrap(True)
        layout.addWidget(path)
        reason=QLineEdit()
        reason.setPlaceholderText('เหตุผลการทดสอบรายคน')
        layout.addWidget(reason)
        buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec()==QDialog.Accepted and reason.text().strip():
            year,month,eid,actor=self.draft.year,self.draft.month,employee.employee_id,self.actor.text()
            self.work(lambda:self.writer.write_employee_copy(year,month,eid,reason=reason.text(),actor=actor),lambda result:self.refresh())

    def payslips(self):
        if not self.draft:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('ใบเงินเดือนรายบุคคล')
        layout = QVBoxLayout(dialog)
        checks = []
        for employee in self.draft.employees:
            if employee.employee_id:
                check = QCheckBox(employee.name)
                check.setProperty('employee_id', employee.employee_id)
                checks.append(check)
                layout.addWidget(check)
        all_button = QPushButton('เลือกทั้งหมด')
        all_button.clicked.connect(lambda: [check.setChecked(True) for check in checks])
        layout.addWidget(all_button)
        update = QPushButton('อัปเดตใบเงินเดือนที่เลือกในไฟล์สำเนา')
        update.setEnabled(self.writer is not None and self.run['state'] in {PayrollState.CONFIRMED, PayrollState.WRITTEN})
        def perform():
            ids = [c.property('employee_id') for c in checks if c.isChecked()]
            if ids:
                dialog.accept()
                self.work(lambda: self.writer.write_month(self.draft.year, self.draft.month, actor=self.actor.text(), payslip_employee_ids=ids),
                          lambda result: self.refresh())
        update.clicked.connect(perform)
        layout.addWidget(update)
        dialog.exec()

    def reopen(self):
        run,draft = (self.run,self.draft) if self.run else self.service.current(self.year.value(),self.month.value())
        if not run or run['state'] not in FINAL_STATES:
            self.statusBar().showMessage('ไม่พบเดือนที่ยืนยันแล้วสำหรับเดือน/ปีที่เลือก')
            return
        import json
        dialog = QDialog(self)
        dialog.setWindowTitle('ส่วนต่างหลังยืนยันเงินเดือน')
        dialog.resize(850, 480)
        layout = QVBoxLayout(dialog)
        source_label=QLabel(f'เดือน {draft.month}/{draft.year+543}\nคู่ไฟล์ที่ยืนยันเดิม: {draft.source_path}\n{draft.payroll_path}')
        source_label.setWordWrap(True)
        layout.addWidget(source_label)
        changes = self.service.repo.pending_changes(run['id'])
        latest = json.loads(changes[0]['difference']) if changes else {'fields': []}
        table = QTableWidget(len(latest['fields']), 7)
        table.setHorizontalHeaderLabels(['พนักงาน','รายการ', 'ต้นทางเดิม', 'ต้นทางใหม่', 'ส่วนต่าง','ยืนยันเดิม','ฉบับร่างใหม่'])
        names={employee.key:employee.name for employee in draft.employees}
        for row, change in enumerate(latest['fields']):
            for col, value in enumerate([names.get(change['employee_key'],change['employee_key']),THAI_FIELDS.get(change['field'], change['field']), change['old_source'], change['new_source'], change['source_difference'],change['old_final'],change['new_draft']]):
                table.setItem(row, col, QTableWidgetItem(str(value if value is not None else '—')))
        layout.addWidget(table)
        acknowledged = QCheckBox('ตรวจส่วนต่างแล้ว และต้องการเปิดเดือนนี้ใหม่')
        layout.addWidget(acknowledged)
        reason = QLineEdit()
        reason.setPlaceholderText('เหตุผลที่เปิดเดือนใหม่')
        layout.addWidget(reason)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted and acknowledged.isChecked() and reason.text().strip():
            self.service.reopen(draft.year, draft.month, reason=reason.text(), actor=self.actor.text())
            self.read_draft()

    def lock(self):
        if self.run and self.run['state'] == PayrollState.WRITTEN:
            self.service.lock(self.draft.year, self.draft.month, actor=self.actor.text())
            self.refresh()

    def history(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('ประวัติการตรวจสอบ')
        dialog.resize(880, 490)
        layout = QVBoxLayout(dialog)
        rows = self.service.repo.audit_history()
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(['เวลา', 'การดำเนินการ', 'เดือน', 'ผู้ตรวจสอบ'])
        for i, row in enumerate(rows):
            for j, value in enumerate([row['timestamp'], text(row['action']), f'{row["month"] or ""}/{row["year"] or ""}', row['actor']]):
                table.setItem(i, j, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        dialog.exec()

    def settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('ตั้งค่า')
        layout = QFormLayout(dialog)
        start = QCheckBox('เฝ้าดูการบันทึกไฟล์ในโฟลเดอร์สำเนา')
        start.setChecked(self.service.repo.setting('watch_enabled', False))
        layout.addRow(start)
        layout.addRow(QLabel('การเปิดโปรแกรมเมื่อเข้าสู่ Windows ใช้ตัวติดตั้งเริ่มอัตโนมัติที่แยกไว้'))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addRow(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.service.repo.set_setting('watch_enabled', start.isChecked())
            if hasattr(self, 'configure_watcher'):
                self.configure_watcher()

    def open_copy(self, kind):
        path = Path(getattr(self, kind).text())
        try:
            development_target(path)
        except RuntimeError:
            return
        if path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def closeEvent(self, event):
        if self.tray and self.tray.isVisible():
            logging.getLogger('ntp').info('Main window hidden to tray')
            self.hide()
            event.ignore()
        else:
            if self.shutdown(): event.accept()
            else: event.ignore()

    def shutdown(self):
        if self.watcher:
            if not self.watcher.stop():
                self.exit_pending = True
                return False
        if self.busy:
            self.exit_pending = True
            self.statusBar().showMessage('กำลังรอการดำเนินการให้เสร็จก่อนออก')
            return False
        self.pool.waitForDone(30000)
        return True
