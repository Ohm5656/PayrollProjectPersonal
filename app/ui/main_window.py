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

from app.domain import FINAL_STATES, PayrollState, ReviewIssue, THAI_FIELDS, decimal_value, issue_key
from app.excel.workbook_source import discover_workbooks, file_hash, filename_month
from app.safety import REFERENCE_ROOT, TEST_ROOT, development_target
from app.ui.review import DecisionDialog, EmployeeReview, PayslipMappingDialog, ReviewCenter, ZeroManualReview, money
from app.ui.presentation import text,error_text
from app.ui.components import NavigationButton, PageHeader
from app.ui.overview_model import OverviewViewModel, overview_action, thai_period
from app.ui.overview_page import OverviewPage
from app.ui.review_queue_model import ReviewQueueModel
from app.ui.review_queue_page import ReviewQueuePage
from app.ui.employee_detail_page import EmployeeDetailPage
from app.ui.history_page import HistoryPage
from app.ui.history_detail_page import HistoryDetailPage
from app.ui.history_model import HistoryViewModel
from app.ui.problems_model import ProblemsViewModel
from app.ui.problems_page import ProblemsPage
from app.ui.problems_detail_page import ProblemJobDetailPage, StagedWriteInspectionPage
from app.ui.settings_model import SettingsViewModel
from app.ui.settings_page import SettingsPage
from app.services.payroll_service import PayrollStateError
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
        self.problems_model = ProblemsViewModel(service, runtime=runtime)
        self.settings_model = SettingsViewModel(self.workflow, runtime=runtime,
                                                startup_service=self.startup_service)
        self.draft, self.run, self.busy = None, None, False
        self._source_period = None
        self._employee_detail_period = None
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
            'overview': ('ภาพรวม', 'สถานะของรอบเงินเดือนที่เลือกและขั้นตอนถัดไปที่ปลอดภัย'),
            'review': ('รอตรวจสอบ', 'รายการที่ต้องตรวจสอบก่อนยืนยันเงินเดือนของรอบที่เลือก'),
            'history': ('ประวัติ', 'ค้นหาและตรวจสอบเหตุการณ์ที่บันทึกไว้แบบอ่านอย่างเดียว'),
            'problems': ('ปัญหาและการกู้คืน', 'ตรวจสอบงานเบื้องหลัง การตั้งค่า และแนวทางแก้ไขอย่างปลอดภัย'),
            'settings': ('ตั้งค่า', 'โฟลเดอร์ทำงาน การเริ่มพร้อม Windows และสถานะการเฝ้าดูไฟล์'),
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
        self.month.setAccessibleName('เลือกเดือนของรอบเงินเดือน')
        self.year.setAccessibleName('เลือกปี ค.ศ. ของรอบเงินเดือน')
        self.month.valueChanged.connect(self._period_changed)
        self.year.valueChanged.connect(self._period_changed)
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
        # Reuse the authoritative controls above in the shell context.  The
        # legacy recovery surface consequently has no separate period state.
        self.period_context = QWidget()
        period_context_layout = QHBoxLayout(self.period_context)
        period_context_layout.setContentsMargins(0, 0, 0, 0)
        period_context_layout.setSpacing(8)
        context_label = QLabel('รอบเงินเดือน')
        context_label.setProperty('role', 'supporting')
        self.period_context_label = QLabel()
        self.period_context_label.setProperty('role', 'sectionTitle')
        period_context_layout.addWidget(context_label)
        period_context_layout.addWidget(self.month)
        period_context_layout.addWidget(self.year)
        period_context_layout.addWidget(self.period_context_label)
        period_context_layout.addStretch()
        self._content_layout.insertWidget(1, self.period_context)
        self._update_period_context()
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
        self.employee_detail_page = EmployeeDetailPage()
        self.employee_detail_page.back_requested.connect(lambda: self.navigate_to(self._detail_return_page))
        self.employee_detail_page.field_review_requested.connect(self._review_employee_field)
        self.employee_detail_page.profile_requested.connect(self.profile_dialog)
        self.employee_detail_page.calendar_requested.connect(self.calendar_review)
        self.employee_detail_page.zero_review_requested.connect(self._review_employee_zeros)
        self._detail_return_page = 'overview'
        self.history_page = HistoryPage(service.repo)
        self.history_page.event_activated.connect(self._history_event_selected)
        self.history_detail_page = HistoryDetailPage()
        self.history_detail_page.back_requested.connect(lambda: self.navigate_to('history'))
        self.history_detail_page.period_requested.connect(self._open_history_period)
        self.problems_page = ProblemsPage(self.problems_model)
        self.problems_page.job_selected.connect(self._problem_job_selected)
        self.problems_page.staged_writes_requested.connect(self._show_staged_writes)
        self.problem_detail_page = ProblemJobDetailPage()
        self.problem_detail_page.back_requested.connect(lambda: self.navigate_to('problems'))
        self.problem_detail_page.retry_requested.connect(self._retry_problem_job)
        self.staged_write_page = StagedWriteInspectionPage()
        self.staged_write_page.back_requested.connect(lambda: self.navigate_to('problems'))
        self.settings_page = SettingsPage(self.settings_model)
        self.settings_page.save_requested.connect(self._save_settings)
        self.settings_page.repair_requested.connect(self._repair_startup)
        self._page_indexes = {'overview': self.page_host.addWidget(self.overview_page),
                              'legacy': self.page_host.addWidget(self.compatibility_scroll),
                              'employee_detail': self.page_host.addWidget(self.employee_detail_page),
                              'history_detail': self.page_host.addWidget(self.history_detail_page),
                              'problem_detail': self.page_host.addWidget(self.problem_detail_page),
                              'staged_writes': self.page_host.addWidget(self.staged_write_page)}
        for page_id, action_text, action in (
            ('review', '', None),
            ('history', 'เปิดประวัติการตรวจสอบปัจจุบัน', self.history),
            ('problems', '', None),
            ('settings', '', None),
        ):
            page = (self.review_queue_page if page_id == 'review' else self.history_page if page_id == 'history'
                    else self.problems_page if page_id == 'problems' else self.settings_page)
            self._page_indexes[page_id] = self.page_host.addWidget(page)
        self.navigate_to('overview')
        # Initial presentation must not hydrate a persisted draft implicitly.
        # Loading is deliberately reserved for an explicit period-selector
        # change, so canceling a protected workflow cannot restore an old
        # write target merely by opening this window.
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
        if (hasattr(self, 'settings_page') and self.page_host.currentWidget() is self.settings_page
                and page_id != 'settings' and self.settings_page.is_dirty()):
            answer = QMessageBox.question(
                self, 'มีการเปลี่ยนแปลงที่ยังไม่บันทึก',
                'ต้องการละทิ้งการเปลี่ยนแปลงการตั้งค่าหรือไม่?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                for candidate, button in self.navigation_buttons.items():
                    button.setChecked(candidate == 'settings')
                self.navigation_buttons['settings'].setFocus(Qt.OtherFocusReason)
                return False
        self.page_host.setCurrentIndex(self._page_indexes[page_id])
        for candidate, button in self.navigation_buttons.items():
            button.setChecked(candidate == page_id)
        title, subtitle = self.page_metadata[page_id]
        self.page_header.set_content(title, subtitle)
        if page_id == 'review':
            self.refresh_review_queue()
        elif page_id == 'history':
            self.history_page.refresh()
        elif page_id == 'problems':
            self.problems_page.refresh()
        elif page_id == 'settings':
            self.settings_page.load()
        self.navigation_buttons[page_id].setFocus(Qt.OtherFocusReason)
        return True

    def show_legacy_workflow(self):
        """Keep every unmigrated payroll operation reachable during D.2."""
        self.page_host.setCurrentIndex(self._page_indexes['legacy'])
        for candidate, button in self.navigation_buttons.items():
            button.setChecked(candidate == 'overview')
        self.page_header.set_content('เครื่องมือเพิ่มเติม', 'การดำเนินการขั้นสูงสำหรับการทดสอบ การกู้คืน และงานเฉพาะกรณี')

    def _update_period_context(self):
        if hasattr(self, 'period_context_label'):
            self.period_context_label.setText(thai_period(self.year.value(), self.month.value()))

    def _period_changed(self, *_):
        """Refresh the currently selected persisted period without side effects."""
        self._update_period_context()
        self._load_selected_period_presentation()

    def _selected_period(self):
        return self.year.value(), self.month.value()

    def _draft_matches_selected_period(self, draft=None):
        candidate = self.draft if draft is None else draft
        return bool(candidate and (candidate.year, candidate.month) == self._selected_period())

    def _selected_sources(self):
        """Expose manually selected copies only when they belong to this period.

        A manually selected copy becomes period-scoped once it has prepared a
        draft or was selected/prepared through the current UI.  On a later
        period change, stale paths remain untouched as preferences but are not
        represented as usable inputs for the new period.
        """
        if self._source_period and self._source_period != self._selected_period():
            return {}
        return {'attendance': self.attendance.text(), 'payroll': self.payroll.text()}

    def _load_selected_period_presentation(self):
        """Read and render only persisted state for the selected period."""
        self.run, self.draft = self.service.current(*self._selected_period())
        if self._employee_detail_period and self._employee_detail_period != self._selected_period():
            self._employee_detail_period = None
            if self.page_host.currentIndex() == self._page_indexes.get('employee_detail'):
                self.navigate_to(self._detail_return_page)
        self._render_legacy_summary(self.draft, self.run)
        self._render_employee_table(self.draft)
        self.update_buttons()
        self.refresh_overview()
        self.refresh_review_queue()

    def refresh_overview(self, *_):
        sources = self._selected_sources()
        snapshot = self.overview_model.snapshot(
            self.year.value(), self.month.value(),
            selected_sources=sources,
        )
        self.overview_page.refresh(snapshot, busy=self.busy)
        action = overview_action(
            snapshot,
            has_sources=bool(sources.get('attendance') and sources.get('payroll')),
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
        if issue.kind.startswith('SOURCE_') and issue.critical:
            QMessageBox.information(self, 'ต้องแก้ไขไฟล์สำเนา',
                'ข้อมูลในไฟล์ Excel ต้องได้รับการแก้ไขก่อน\nกรุณาแก้ไขไฟล์สำเนาและอ่านข้อมูลอีกครั้ง')
            return
        run, draft = self.service.current(self.year.value(), self.month.value())
        if not draft or issue.key not in {candidate.key for candidate in draft.issues}:
            self.statusBar().showMessage('รายการตรวจสอบเปลี่ยนแล้ว กรุณาเลือกใหม่')
            self.refresh_review_queue()
            return
        dialog_type = PayslipMappingDialog if issue.kind == 'PAYSLIP_MAPPING' else DecisionDialog
        if dialog_type(self.service, draft, issue, actor=self.actor.text(), parent=self).exec() == QDialog.Accepted:
            self._recalculate_after_review(draft)

    def show_employee_detail(self, employee_id, *, return_page='overview'):
        """Load evidence for the selected period; rendering has no mutation side effect."""
        run, draft = self.service.current(self.year.value(), self.month.value())
        employee = next((candidate for candidate in (draft.employees if draft else ())
                         if candidate.employee_id == employee_id), None)
        if not employee:
            self.statusBar().showMessage('ไม่พบข้อมูลพนักงานสำหรับรอบที่เลือก')
            return False
        self._detail_return_page = return_page
        self._employee_detail_period = self._selected_period()
        self.run, self.draft = run, draft
        self.employee_detail_page.refresh(draft, employee, run)
        self.page_host.setCurrentIndex(self._page_indexes['employee_detail'])
        self.page_header.set_content('รายละเอียดพนักงาน', 'แสดงหลักฐานและยอดเงินจากฉบับร่างของรอบที่เลือก')
        return True

    def _review_employee_field(self, field):
        employee = self.employee_detail_page._employee
        if not employee or not employee.employee_id or not self.draft:
            return
        issue = ReviewIssue(issue_key('FIELD', employee.employee_id, field), 'FIELD', employee.employee_id,
                            employee.sheet, None, None, 'ยืนยันหรือแก้ไขจำนวน', field=field)
        if DecisionDialog(self.service, self.draft, issue, actor=self.actor.text(), parent=self).exec() == QDialog.Accepted:
            self._recalculate_after_review(self.draft)

    def _review_employee_zeros(self):
        employee = self.employee_detail_page._employee
        if not employee or not self.draft:
            return
        if ZeroManualReview(self.service, self.draft, employee, actor=self.actor.text(), parent=self).exec() == QDialog.Accepted:
            self._recalculate_after_review(self.draft)

    def _recalculate_after_review(self, draft):
        """Refresh queue only from the service result after an existing dialog persisted."""
        year, month = draft.year, draft.month
        def done(result):
            if (year, month) != (self.year.value(), self.month.value()):
                self.statusBar().showMessage('การตรวจสอบเสร็จแล้วสำหรับรอบอื่น กรุณาเลือกรอบนั้นเพื่อดูผล')
                self.refresh_review_queue()
                return
            self.show_result(result)
            self.refresh_review_queue()
        self.work(lambda: self.service.prepare(Path(draft.source_path), Path(draft.payroll_path),
                                               force=True, year=year, month=month), done)

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
        self._render_employee_table(None)
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
        self._source_period = self._selected_period()
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
            self._source_period = self._selected_period()
            self.clear_source_selection()
            self.statusBar().showMessage('เตรียมสำเนาแล้ว กดอ่านข้อมูลเพื่อเริ่มตรวจสอบ')
            self.update_manual_runtime_sources()
        self.work(copy, loaded)

    def read_draft(self):
        if not self.attendance.text() or not self.payroll.text():
            self.statusBar().showMessage('กรุณาเลือกไฟล์สำเนาทั้งสองไฟล์')
            return
        if self._source_period and self._source_period != self._selected_period():
            self.statusBar().showMessage('ไฟล์สำเนาที่เลือกเป็นคนละรอบ กรุณาเลือกหรือเตรียมสำเนาสำหรับรอบนี้')
            return
        attendance_path, payroll_path = Path(self.attendance.text()), Path(self.payroll.text())
        year, month = self.year.value(), self.month.value()
        self.service.repo.set_setting('actor', self.actor.text())
        self.work(lambda: self.service.prepare(attendance_path, payroll_path, force=True, year=year, month=month), self.show_result)

    def show_result(self, result):
        self.run, self.draft = result['run'], result['draft']
        self._source_period = (self.draft.year, self.draft.month)
        if self.runtime:
            self.runtime.review_resolved(self.run)
        self.render()
        if result.get('difference'):
            self.notify.emit('พบการแก้ไขบันทึกเวลาหลังยืนยันเงินเดือน', 'เดือนที่ยืนยันแล้วคงข้อมูลเดิม กรุณาดูส่วนต่างก่อนเปิดเดือนใหม่')

    def render(self):
        draft = self.draft
        if not draft:
            return
        self.year.blockSignals(True)
        self.month.blockSignals(True)
        self.year.setValue(draft.year)
        self.month.setValue(draft.month)
        self.year.blockSignals(False)
        self.month.blockSignals(False)
        self._update_period_context()
        self._render_legacy_summary(draft, self.run)
        self._render_employee_table(draft)
        self.state_changed.emit('review' if self.run['state'] == PayrollState.NEEDS_REVIEW else 'ready')
        self.statusBar().showMessage(f'เดือน {draft.month}/{draft.year + 543} — {STATE_TEXT[self.run["state"]]}')
        self.update_buttons()
        self.refresh_overview()
        self.refresh_review_queue()

    def _render_legacy_summary(self, draft, run):
        """Keep compatibility values aligned with the visible selected period."""
        if not draft or not run:
            for card in self.cards.values():
                card.setText('—')
            return
        self.cards['attendance'].setText(Path(draft.source_path).name)
        source=Path(draft.source_path)
        saved=datetime.fromtimestamp(source.stat().st_mtime,timezone(timedelta(hours=7))).strftime('%d/%m/%Y %H:%M:%S') if source.is_file() else 'ไม่พบไฟล์สำเนา'
        self.cards['save'].setText(saved)
        self.cards['employees'].setText(str(sum(bool(e.employee_id) for e in draft.employees)))
        self.cards['issues'].setText(str(len(draft.issues)))
        self.cards['state'].setText(STATE_TEXT.get(run['state'], run['state']))

    def _render_employee_table(self, draft):
        """Render selected-period employees or clear every stale row/selection."""
        self.table.clearContents()
        self.table.clearSelection()
        self.table.setCurrentItem(None)
        if not draft:
            self.table.setRowCount(0)
            return
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
        if not self.draft or self.busy:
            return
        employee = self.draft.employees[row]
        if employee.employee_id:
            self.show_employee_detail(employee.employee_id)
        else:
            self.review()

    def selected_employee(self):
        if self.page_host.currentIndex() == self._page_indexes.get('employee_detail'):
            return self.employee_detail_page._employee if self._employee_detail_period == self._selected_period() else None
        if not self._draft_matches_selected_period() or self.table.currentRow() < 0:
            return None
        row = self.table.currentRow()
        return self.draft.employees[row] if row < len(self.draft.employees) else None

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
        year, month = self.year.value(), self.month.value()
        # The selector is the source of truth.  A cached draft can belong to a
        # different month after the user has browsed the application.
        run, draft = self.service.current(year, month)
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
        if not latest['fields']:
            layout.addWidget(QLabel('ไม่มีส่วนต่างจากแหล่งข้อมูลที่บันทึกไว้สำหรับรอบนี้'))
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
            try:
                self.service.reopen(year, month, reason=reason.text(), actor=self.actor.text())
            except PayrollStateError as exc:
                self.statusBar().showMessage(error_text(str(exc)))
                return
            self.run, self.draft = self.service.current(year, month)
            self._refresh_period_views()

    def lock(self):
        year, month = self.year.value(), self.month.value()
        run, draft = self.service.current(year, month)
        if not run or run['state'] != PayrollState.WRITTEN:
            self.statusBar().showMessage('ต้องเขียนและตรวจสอบไฟล์สำเร็จก่อนล็อกเดือน')
            return
        answer = QMessageBox.question(
            self, 'ยืนยันการล็อกรอบเงินเดือน',
            f'ล็อกรอบ {month}/{year + 543} แล้วจะไม่สามารถแก้ไขได้จนกว่าจะมีขั้นตอนเปิดรอบใหม่',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.service.lock(year, month, actor=self.actor.text())
        except PayrollStateError as exc:
            self.statusBar().showMessage(error_text(str(exc)))
            return
        self.run, self.draft = self.service.current(year, month)
        self._refresh_period_views()

    def _refresh_period_views(self):
        """Refresh read models after a deliberate lifecycle transition only."""
        if self.draft:
            self.render()
        self.refresh_review_queue()
        self.history_page.refresh()

    def history(self):
        self.navigate_to('history')

    def _problem_job_selected(self, job_id):
        job = self.problems_model.jobs.get(job_id)
        if not job:
            self.statusBar().showMessage('ไม่พบรายการงานที่เลือก')
            return
        retry_allowed = False
        if self.runtime:
            retry_allowed, _ = self.runtime.retry_eligibility(job_id)
        self.problem_detail_page.refresh(job, self.problems_model.job(job), retry_allowed=retry_allowed)
        self.page_host.setCurrentIndex(self._page_indexes['problem_detail'])
        self.page_header.set_content('รายละเอียดปัญหา', 'แสดงข้อมูลที่บันทึกไว้และแนวทางดำเนินการอย่างปลอดภัย')

    def _show_staged_writes(self):
        snapshot = self.problems_model.snapshot(limit=50)
        self.staged_write_page.refresh(snapshot.staged_writes)
        self.page_host.setCurrentIndex(self._page_indexes['staged_writes'])
        self.page_header.set_content('ตรวจสอบการเขียน Excel', 'รายการค้างตรวจสอบแบบอ่านอย่างเดียว')

    def _retry_problem_job(self, job_id):
        if not self.runtime or self.busy:
            return
        job = self.runtime.jobs.get(job_id)
        allowed, reason = self.runtime.retry_eligibility(job_id)
        if not job or not allowed:
            self.statusBar().showMessage(reason or 'ไม่สามารถลองงานนี้ใหม่ได้')
            return
        source_name = Path(job.get('source_path') or '').name or 'ไม่ระบุไฟล์ต้นทาง'
        answer = QMessageBox.question(
            self, 'ยืนยันการลองประมวลผลใหม่',
            f'ลองประมวลผลงานนี้อีกครั้งหรือไม่?\nไฟล์ต้นทาง: {source_name}\nรอบ: '
            f'{self.problems_model.job(job).period_label}\nระบบจะตรวจสอบไฟล์และการตั้งค่าก่อนเริ่มงาน',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel,
        )
        if answer != QMessageBox.Yes:
            return
        self.problem_detail_page.retry.setEnabled(False)
        self.work(lambda: self.runtime.retry_job(job_id),
                  lambda result: self._retry_problem_finished(job_id, result))

    def _retry_problem_finished(self, job_id, result):
        actual = self.runtime.jobs.get(job_id) if self.runtime else None
        self.problems_page.refresh()
        self.refresh_overview()
        self.refresh_review_queue()
        if actual:
            allowed, _ = self.runtime.retry_eligibility(job_id)
            self.problem_detail_page.refresh(actual, self.problems_model.job(actual), retry_allowed=allowed)
        replacement = result.get('changed_source_job') if isinstance(result, dict) else None
        if replacement:
            self.statusBar().showMessage(
                f'ไฟล์ต้นทางมีการเปลี่ยนแปลง: สร้างงานใหม่สถานะ {replacement.get("state")} แล้ว '
                'ยังไม่ได้ยืนยันว่าประมวลผลสำเร็จ')
        elif actual:
            self.statusBar().showMessage(f'ผลการลองใหม่ที่บันทึกไว้: {actual.get("state")}')

    def _history_event_selected(self, event_id):
        row = self.service.repo.audit_event(event_id)
        if not row:
            self.statusBar().showMessage('ไม่พบประวัติรายการที่เลือก')
            return
        event = HistoryViewModel().event(row)
        timeline = ()
        if row.get('year') is not None and row.get('month') is not None:
            timeline = HistoryViewModel().events(self.service.repo.audit_events(
                limit=100, year=row['year'], month=row['month']))
        self.history_detail_page.refresh(event.__dict__, employee_name=self.service.repo.employee_name(row.get('employee_id')),
                                         timeline=timeline)
        self.page_host.setCurrentIndex(self._page_indexes['history_detail'])
        self.page_header.set_content('รายละเอียดประวัติ', 'แสดงเฉพาะข้อมูลที่บันทึกไว้ และไม่เปลี่ยนรอบเงินเดือนจนกว่าจะเลือกเปิดรอบ')

    def _open_history_period(self, year, month):
        self.year.setValue(year)
        self.month.setValue(month)
        self.navigate_to('overview')

    def settings(self):
        self.navigate_to('settings')

    def _save_settings(self, values):
        """Persist folders, then perform only the explicit startup request.

        A Task Scheduler failure is deliberately not disguised as a rollback:
        the persisted folder configuration remains visible as a partial result.
        """
        try:
            self.workflow.configure(values['attendance_folder'], values['payroll_folder'], values['template_path'])
        except Exception as exc:
            self.settings_page.operation_finished(f'ยังไม่ได้บันทึกโฟลเดอร์ทำงาน: {exc}', success=False, reload=False)
            return False

        messages, success = ['บันทึกโฟลเดอร์ทำงานแล้ว'], True
        if self.runtime:
            # reconfigure preserves watch_enabled; it must never act like an
            # implicit resume_monitoring call from the old modal Settings UI.
            if not self.runtime.reconfigure():
                success = False
                messages.append('บันทึกแล้ว แต่ไม่สามารถนำการตั้งค่าใหม่ไปใช้กับการเฝ้าดูไฟล์ได้')
        self.manual_recovery.setVisible(False)

        status = self.startup_service.validate()
        desired, result = bool(values['start_with_windows']), None
        if desired and not status.enabled:
            if status.state.name == 'NEEDS_REPAIR':
                success = False
                messages.append('Start with Windows ยังต้องซ่อมแซม; กรุณากดปุ่มซ่อมแซมโดยชัดแจ้ง')
            else:
                result = self.startup_service.install()
        elif not desired and status.installed:
            result = self.startup_service.remove()
        if result is not None:
            if result.success:
                messages.append('อัปเดต Start with Windows แล้ว')
            else:
                success = False
                messages.append(f'บันทึกโฟลเดอร์แล้ว แต่ Start with Windows ไม่สำเร็จ: {result.status.message}')
        self.settings_page.operation_finished(' • '.join(messages), success=success)
        return success

    def _repair_startup(self):
        """Repair is a separately confirmed, explicit user action."""
        result = self.startup_service.repair()
        if result.success:
            self.settings_page.operation_finished('ซ่อมแซม Start with Windows แล้ว', success=True)
            return True
        self.settings_page.operation_finished(
            f'ไม่สามารถซ่อมแซม Start with Windows ได้: {result.status.message}', success=False,
        )
        return False

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
            if getattr(wizard, 'monitoring_choice_persisted', False):
                if self.runtime and self.service.repo.setting('watch_enabled', None) is True:
                    self.runtime.resume_monitoring()
            else:
                # Compatibility for a custom/older setup implementation. The
                # shipped wizard above always persists an explicit choice.
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
