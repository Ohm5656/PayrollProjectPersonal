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
    QApplication, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.domain import FINAL_STATES, PayrollState, THAI_FIELDS, decimal_value
from app.excel.workbook_source import discover_workbooks, file_hash, filename_month
from app.safety import REFERENCE_ROOT, TEST_ROOT, development_target
from app.ui.review import EmployeeReview, ReviewCenter, money
from app.ui.presentation import text,error_text
from app.ui.components import NavigationButton, PageHeader
from app.ui.overview_model import OverviewViewModel, overview_action
from app.ui.overview_page import OverviewPage
from app.ui.review_queue_model import ReviewQueueModel
from app.ui.review_queue_page import ReviewQueuePage
from app.services.workflow_service import WorkflowService
from app.services.windows_startup import WindowsStartupService

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

    def __init__(self, service, *, writer=None, runtime=None, parent=None, startup_service=None):
        super().__init__(parent)
        self.service, self.writer = service, writer
        self.runtime = runtime
        self.workflow = runtime.workflow if runtime else WorkflowService(service)
        self.startup_service = startup_service or WindowsStartupService()
        self.overview_model = OverviewViewModel(service, runtime=runtime, writer=writer,
                                                 startup_service=self.startup_service)
        self.review_queue_model = ReviewQueueModel()
        self.draft, self.run, self.busy = None, None, False
        self.tray = getattr(QApplication.instance(), 'payroll_tray', None)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.jobs = []
        self.exit_pending = False
        self.watched_result.connect(self.receive_watched_result)
        self.watched_error.connect(self.receive_watched_error)
        if self.runtime:
            self.runtime.state_changed.connect(self.runtime_state_changed)
            self.runtime.processing_finished.connect(self.receive_watched_result)
            self.runtime.runtime_error.connect(self.receive_watched_error)
            self.runtime.register_shutdown_participant(self.shutdown_ui)
        self.setWindowTitle('NTP Payroll Assistant')
        self.resize(1130, 720)
        self.setMinimumSize(860, 620)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)

        self.sidebar = QWidget()
        self.sidebar.setObjectName('sidebar')
        self.sidebar.setMinimumWidth(220)
        self.sidebar.setMaximumWidth(240)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(8)
        brand = QLabel('NTP Payroll')
        brand.setProperty('role', 'sectionTitle')
        sidebar_layout.addWidget(brand)
        product = QLabel('Payroll Assistant')
        product.setProperty('role', 'supporting')
        sidebar_layout.addWidget(product)
        sidebar_layout.addSpacing(16)

        self.navigation_buttons = {}
        self.page_metadata = {
            'overview': ('ภาพรวม', 'พื้นที่ทำงานเงินเดือนปัจจุบัน (จะย้ายเป็น Overview เต็มรูปแบบใน Phase D.2)'),
            'review': ('รอตรวจสอบ', 'เปิดศูนย์ตรวจสอบรายการปัจจุบัน; Review Queue เต็มรูปแบบอยู่ใน Phase D.3'),
            'history': ('ประวัติ', 'เปิดประวัติการตรวจสอบปัจจุบัน; หน้าประวัติใหม่อยู่ใน Phase D.4'),
            'problems': ('ปัญหาและการกู้คืน', 'สถานะและการกู้คืนเชิงลึกจะย้ายใน Phase D.5'),
            'settings': ('ตั้งค่า', 'เปิดหน้าตั้งค่าปัจจุบัน; หน้าตั้งค่าใหม่อยู่ใน Phase D.6'),
        }
        for page_id, label in (('overview', 'ภาพรวม'), ('review', 'รอตรวจสอบ'), ('history', 'ประวัติ'),
                               ('problems', 'ปัญหาและการกู้คืน'), ('settings', 'ตั้งค่า')):
            button = NavigationButton(page_id, label, self.sidebar)
            button.clicked.connect(lambda checked=False, target=page_id: self.navigate_to(target))
            sidebar_layout.addWidget(button)
            self.navigation_buttons[page_id] = button
        sidebar_layout.addStretch()
        tray_hint = QLabel('การเฝ้าดูไฟล์ควบคุมจากเมนู Tray')
        tray_hint.setProperty('role', 'supporting')
        tray_hint.setWordWrap(True)
        sidebar_layout.addWidget(tray_hint)
        shell.addWidget(self.sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        self._content_layout = content_layout
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(16)
        self.page_header = PageHeader()
        content_layout.addWidget(self.page_header)
        self.page_host = QStackedWidget()
        content_layout.addWidget(self.page_host, 1)
        shell.addWidget(content, 1)

        self.compatibility_page = QWidget()
        layout = QVBoxLayout(self.compatibility_page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        self.settings_button = QPushButton('ตั้งค่าโฟลเดอร์')
        self.settings_button.clicked.connect(self.settings)
        layout.addWidget(self.settings_button)
        self.month8_uat_button = QPushButton('เตรียมทดสอบเดือน 8 (สำเนา)')
        self.month8_uat_button.clicked.connect(self.prepare_month8_uat)
        layout.addWidget(self.month8_uat_button)
        self.uat_indicator = QLabel('')
        self.uat_indicator.setProperty('semantic', 'warning')
        layout.addWidget(self.uat_indicator)
        if self.workflow.configuration() and self.workflow.configuration().get('mode') == 'UAT_MONTH8':
            self.uat_indicator.setText('โหมดทดสอบสำเนา — งวด สิงหาคม 2569 • จ่าย 5 กันยายน 2569')
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
        self.month.valueChanged.connect(self.refresh_overview)
        self.month.valueChanged.connect(self.refresh_review_queue)
        self.year.valueChanged.connect(self.refresh_overview)
        self.year.valueChanged.connect(self.refresh_review_queue)
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
        self.manual_recovery = QGroupBox('เลือกไฟล์เอง (กู้คืน/ทดสอบขั้นสูง)')
        manual_layout = QVBoxLayout(self.manual_recovery)
        manual_layout.addLayout(period)
        manual_layout.addLayout(sources)
        self.manual_recovery.setVisible(not self.workflow.configured())
        layout.addWidget(self.manual_recovery)
        self._legacy_cards = QWidget()
        self._legacy_cards.setVisible(False)
        cards = QGridLayout(self._legacy_cards)
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
        # These values remain as compatibility state for existing handlers.
        # The Overview is the sole visible dashboard presentation in Phase D.2.
        layout.addWidget(self._legacy_cards)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(['ชื่อพนักงาน', 'OT ปกติ (ชม.)', 'OT วันหยุด (ชม.)', 'เบี้ยเลี้ยง', 'ค่าเดินทาง', 'เบี้ยขยัน', 'รายการพิเศษ (จำนวน)', 'สถานะ'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self.employee_review)
        actions = QHBoxLayout()
        self.read_button = QPushButton('อ่านข้อมูล / คำนวณฉบับร่าง')
        self.read_button.setProperty('role', 'primary')
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
            if callback == self.single_employee_test:
                self.single_test_button = button
            button.clicked.connect(callback)
            second.addWidget(button)
        layout.addWidget(advanced)

        self.compatibility_scroll = QScrollArea()
        self.compatibility_scroll.setWidgetResizable(True)
        self.compatibility_scroll.setWidget(self.compatibility_page)
        self.overview_page = OverviewPage()
        self.overview_page.attach_employee_table(self.table)
        self.overview_page.legacy_button.clicked.connect(self.show_legacy_workflow)
        self.review_queue_page = ReviewQueuePage()
        self.review_queue_page.overview_requested.connect(lambda: self.navigate_to('overview'))
        self.review_queue_page.issue_activated.connect(self._review_issue_selected)
        self._page_indexes = {'overview': self.page_host.addWidget(self.overview_page),
                              'legacy': self.page_host.addWidget(self.compatibility_scroll)}
        for page_id, action_text, action in (
            ('review', '', None),
            ('history', 'เปิดประวัติการตรวจสอบปัจจุบัน', self.history),
            ('problems', '', None),
            ('settings', 'เปิดหน้าตั้งค่าปัจจุบัน', self.settings),
        ):
            page = self.review_queue_page if page_id == 'review' else self._placeholder_page(page_id, action_text, action)
            self._page_indexes[page_id] = self.page_host.addWidget(page)
        self.navigate_to('overview')
        self.refresh_overview()
        self.refresh_review_queue()
        self._apply_responsive_shell()
        self.statusBar().showMessage('เลือกเดือนและเตรียมสำเนาข้อมูลเพื่อเริ่มทดสอบ')
        self.update_buttons()
        if self.runtime:
            self.runtime_state_changed(self.runtime.state)
            if self.runtime.last_result:
                self.show_result(self.runtime.last_result)

    def _placeholder_page(self, page_id, action_text='', action=None):
        """Honest routing placeholder until the destination is migrated."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        message = QLabel(self.page_metadata[page_id][1])
        message.setProperty('role', 'supporting')
        message.setWordWrap(True)
        layout.addWidget(message)
        if action:
            button = QPushButton(action_text)
            button.setProperty('role', 'primary')
            button.clicked.connect(action)
            layout.addWidget(button)
        layout.addStretch()
        return page

    def navigate_to(self, page_id):
        """Switch presentation pages without touching runtime or payroll state."""
        if page_id not in self._page_indexes:
            raise ValueError(f'Unknown application page: {page_id}')
        self.page_host.setCurrentIndex(self._page_indexes[page_id])
        for candidate, button in self.navigation_buttons.items():
            button.setChecked(candidate == page_id)
        title, subtitle = self.page_metadata[page_id]
        self.page_header.set_content(title, subtitle)
        if page_id == 'review':
            self.refresh_review_queue()
        self.navigation_buttons[page_id].setFocus(Qt.OtherFocusReason)

    def show_legacy_workflow(self):
        """Keep every unmigrated payroll operation reachable during D.2."""
        self.page_host.setCurrentIndex(self._page_indexes['legacy'])
        self.page_header.set_content('เครื่องมือเงินเดือน', 'เครื่องมือเดิมที่ยังไม่ได้ย้ายเข้าสู่ Overview')

    def refresh_overview(self, *_):
        snapshot = self.overview_model.snapshot(
            self.year.value(), self.month.value(),
            selected_sources={'attendance': self.attendance.text(), 'payroll': self.payroll.text()},
        )
        self.overview_page.refresh(snapshot, busy=self.busy)
        action = overview_action(
            snapshot,
            has_sources=bool(self.attendance.text() and self.payroll.text()),
            writer_available=self.writer is not None,
            busy=self.busy,
        )
        self.overview_page.set_primary_action(
            label=action.label,
            detail=action.detail,
            enabled=action.enabled,
            visible=action.visible,
            callback=(lambda action_id=action.action_id: self._run_overview_action(action_id))
            if action.action_id else None,
            busy=self.busy,
        )

    def refresh_review_queue(self, *_):
        run, draft = self.service.current(self.year.value(), self.month.value())
        snapshot = self.review_queue_model.snapshot(draft, year=self.year.value(), month=self.month.value())
        self.review_queue_page.refresh(snapshot)

    def _review_issue_selected(self, issue):
        """Decision routing is added in D.3.4; selection itself is read-only."""
        self.statusBar().showMessage(f'เลือก {issue.kind}; เปิดการตัดสินใจจากรายการนี้')

    def _load_selected_period(self):
        """Use the persisted run for the selected period before an explicit action."""
        self.run, self.draft = self.service.current(self.year.value(), self.month.value())

    def _run_overview_action(self, action_id):
        """Run only the action the user explicitly clicked for the selected period."""
        if self.busy:
            return
        if action_id == 'read':
            self.read_draft()
            return
        self._load_selected_period()
        state = str(self.run['state']) if self.run else 'NO_DRAFT'
        expected_states = {
            'review': {'DRAFT', 'NEEDS_REVIEW'},
            'confirm': {'READY'},
            'write': {'CONFIRMED'},
            'lock': {'WRITTEN'},
        }
        if state not in expected_states.get(action_id, set()):
            self.refresh_overview()
            return
        if action_id == 'review' and self.draft:
            self.review()
        elif action_id == 'confirm' and self.draft:
            self.confirm()
        elif action_id == 'write' and self.writer and self.draft:
            self.write()
        elif action_id == 'lock' and self.draft:
            self.lock()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'sidebar'):
            self._apply_responsive_shell()

    def _apply_responsive_shell(self):
        """Keep labels readable while reserving space for legacy payroll UI."""
        compact = self.width() < 1024
        sidebar_width = 180 if compact else 220
        self.sidebar.setMinimumWidth(sidebar_width)
        self.sidebar.setMaximumWidth(sidebar_width if compact else 240)
        margins = 12 if compact else 24
        self._content_layout.setContentsMargins(margins, 16 if compact else 20, margins, 16 if compact else 20)

    def runtime_state_changed(self, state):
        messages = {'DISABLED': 'หยุดเฝ้าดูไฟล์', 'WATCHING': 'กำลังเฝ้าดูโฟลเดอร์บันทึกเวลาที่ตั้งค่าไว้',
                    'PROCESSING': 'กำลังอ่านและตรวจสอบไฟล์บันทึกเวลา', 'REVIEW_REQUIRED': 'มีรายการที่ต้องตรวจสอบ',
                    'ERROR': 'เกิดข้อผิดพลาดในการทำงานอัตโนมัติ'}
        self.state_changed.emit(str(state).lower())
        self.statusBar().showMessage(messages.get(str(state), str(state)))
        self.refresh_overview()

    def receive_watched_result(self, result):
        if not self.workflow.configured() and Path(result['draft'].source_path) != Path(self.attendance.text()): return
        if not self.workflow.configured() and Path(result['draft'].payroll_path) != Path(self.payroll.text()): return
        # Refresh current persisted revision, since a manual job may have
        # completed after the watcher result was queued on the GUI thread.
        result = dict(result)
        result['run'], result['draft'] = self.service.current(result['draft'].year, result['draft'].month)
        if (result['draft'].year, result['draft'].month) != (self.year.value(), self.month.value()):
            self.statusBar().showMessage(
                f'มีผลลัพธ์ใหม่สำหรับเดือน {result["draft"].month}/{result["draft"].year + 543}; '
                'เลือกรอบนั้นเพื่อดูรายละเอียด'
            )
            self.refresh_overview()
            if self.exit_pending and not self.busy:
                self._notify_shutdown_ready()
            return
        self.show_result(result)
        if self.exit_pending and not self.busy:
            self._notify_shutdown_ready()

    def receive_watched_error(self, message):
        self.state_changed.emit('error')
        self.statusBar().showMessage(message)
        self.refresh_overview()
        if self.exit_pending and not self.busy:
            self._notify_shutdown_ready()

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
        if self.workflow.configuration() and self.workflow.configuration().get('mode') == 'UAT_MONTH8':
            self.single_test_button.setText('ทดสอบพนักงานที่เลือก (UAT เดือน 8)')

    def clear_source_selection(self):
        self.run,self.draft=None,None
        self.table.setRowCount(0)
        for card in self.cards.values(): card.setText('—')
        self.update_buttons()
        self.refresh_overview()

    def prepare_month8_uat(self):
        from app.services.month8_uat import prepare_month8_uat
        def done(result):
            self.manual_recovery.setVisible(False)
            self.uat_indicator.setText('โหมดทดสอบสำเนา — เดือน 8 / 2569')
            if self.runtime:
                self.runtime.resume_monitoring()
            self.statusBar().showMessage('โหมดทดสอบสำเนา — เดือน 8 / 2569: เปิดไฟล์ attendance แล้วกด Save')
        self.work(lambda: prepare_month8_uat(self.workflow), done)

    def work(self, task, success):
        if self.busy:
            return
        self.busy = True
        self.update_buttons()
        self.refresh_overview()
        self.state_changed.emit('processing')
        job = Job(task)
        self.jobs.append(job)
        def done(result):
            self.busy = False
            self.jobs.remove(job)
            success(result)
            self.update_buttons()
            self.refresh_overview()
            if self.exit_pending:
                self._notify_shutdown_ready()
        def failed(message):
            self.busy = False
            self.jobs.remove(job)
            self.update_buttons()
            self.refresh_overview()
            self.state_changed.emit('error')
            self.statusBar().showMessage(error_text(message))
            if self.runtime:
                self.runtime.notification.emit('ดำเนินการไม่สำเร็จ', error_text(message))
            else:
                self.notify.emit('ดำเนินการไม่สำเร็จ', error_text(message))
            if self.exit_pending:
                self._notify_shutdown_ready()
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
        self.update_manual_runtime_sources()

    def update_manual_runtime_sources(self):
        if not self.runtime or not self.attendance.text() or not self.payroll.text():
            return
        try:
            self.runtime.configure_manual_sources(self.attendance.text(), self.payroll.text(),
                                                  self.year.value(), self.month.value())
        except Exception as exc:
            self.receive_watched_error(str(exc))

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
            self.update_manual_runtime_sources()
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
        if self.runtime:
            self.runtime.review_resolved(self.run)
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
            special = [v for k, v in employee.values.items() if k not in {'travel', 'allowance', 'bonus', 'base', 'normal_ot', 'holiday_ot', 'holiday_days'} and v.final_value not in (None, 0)]
            texts = [employee.name, self._hours(amount('normal_ot')), self._hours(amount('holiday_ot')),
                self._amount(amount('allowance')), self._amount(amount('travel')), self._amount(amount('bonus')),
                f'{len(special)} รายการ', status]
            for column, text in enumerate(texts):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if 1 <= column <= 6:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if column == 6:
                    item.setToolTip(', '.join(THAI_FIELDS.get(v.field, v.field) for v in special) or 'ไม่มีรายการพิเศษ')
                self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()
        self.state_changed.emit('review' if self.run['state'] == PayrollState.NEEDS_REVIEW else 'ready')
        self.statusBar().showMessage(f'เดือน {draft.month}/{draft.year + 543} — {STATE_TEXT[self.run["state"]]}')
        self.update_buttons()
        self.refresh_overview()

    @staticmethod
    def _amount(value):
        return '—' if value is None else f'{value:,.2f}'

    @staticmethod
    def _hours(value):
        if value is None:
            return '—'
        return format(value, 'f').rstrip('0').rstrip('.') or '0'

    def review(self):
        self.navigate_to('review')

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
        self.navigate_to('history')
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
        self.navigate_to('settings')
        from app.ui.setup_wizard import SetupWizard
        wizard = SetupWizard(self.workflow, self)
        if wizard.exec() == QDialog.Accepted:
            self.manual_recovery.setVisible(False)
            if self.runtime:
                # Folder settings may have changed, but Settings must never
                # turn paused monitoring back on merely because it was saved.
                # reconfigure() preserves the persisted watch_enabled intent.
                self.runtime.reconfigure()
        return

    def _resume_monitoring_after_first_setup(self):
        """Keep first-run convenience without overriding an explicit pause."""
        if self.runtime and self.service.repo.setting('watch_enabled', None) is None:
            return self.runtime.resume_monitoring()
        return False

    def first_run_setup(self):
        """Show setup only on an interactive first launch, never in Qt tests."""
        if self.workflow.configured():
            return
        from PySide6.QtWidgets import QApplication
        if QApplication.instance() and QApplication.instance().platformName() in {'offscreen', 'minimal'}:
            return
        from app.ui.setup_wizard import SetupWizard
        wizard = SetupWizard(self.workflow, self)
        if wizard.exec() == QDialog.Accepted:
            self.manual_recovery.setVisible(False)
            self._resume_monitoring_after_first_setup()

    def legacy_settings(self):
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
            if self.runtime:
                (self.runtime.resume_monitoring if start.isChecked() else self.runtime.pause_monitoring)()
            else:
                self.service.repo.set_setting('watch_enabled', start.isChecked())

    def open_copy(self, kind):
        self.navigate_to('overview')
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
            if self.runtime:
                stopped = self.runtime.shutdown()
            else:
                stopped = self.shutdown_ui()
            if stopped: event.accept()
            else: event.ignore()

    def shutdown(self):
        """Compatibility wrapper; watcher shutdown belongs to AutomationRuntime."""
        return self.shutdown_ui()

    def shutdown_ui(self):
        if self.busy:
            self.exit_pending = True
            self.statusBar().showMessage('กำลังรอการดำเนินการให้เสร็จก่อนออก')
            return False
        self.pool.waitForDone(30000)
        return True

    def _notify_shutdown_ready(self):
        if self.runtime:
            self.runtime.notify_shutdown_ready()
        else:
            self.exit_when_idle.emit()
