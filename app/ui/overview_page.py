"""Modern read-only overview surface; workflow actions are wired by MainWindow."""
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from app.ui.components import SectionContainer, StatusBadge


class OverviewPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        body = QWidget()
        self.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.period = QLabel()
        self.period.setProperty('role', 'sectionTitle')
        layout.addWidget(self.period)

        status = QWidget()
        status_layout = QGridLayout(status)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setHorizontalSpacing(12)
        status_layout.setVerticalSpacing(12)
        self.monitoring_status = StatusBadge()
        self.payroll_status = StatusBadge()
        self.startup_status = StatusBadge()
        self.output_status = StatusBadge()
        for index, badge in enumerate((self.monitoring_status, self.payroll_status, self.startup_status, self.output_status)):
            status_layout.addWidget(badge, index // 2, index % 2)
        layout.addWidget(status)

        metrics = QWidget()
        metrics_layout = QHBoxLayout(metrics)
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(12)
        self.employee_card = self._metric('พนักงาน')
        self.review_card = self._metric('รอตรวจสอบ')
        self.payroll_card = self._metric('สถานะเงินเดือน')
        for card in (self.employee_card, self.review_card, self.payroll_card):
            metrics_layout.addWidget(card, 1)
        layout.addWidget(metrics)

        self.next_action = SectionContainer('ขั้นตอนถัดไป')
        self.next_action_text = QLabel('กำลังตรวจสอบข้อมูลของรอบที่เลือก')
        self.next_action_text.setWordWrap(True)
        self.next_action.addWidget(self.next_action_text)
        layout.addWidget(self.next_action)

        sources = SectionContainer('ไฟล์สำเนาที่ใช้')
        self.attendance_source = QLabel()
        self.attendance_source.setWordWrap(True)
        self.payroll_source = QLabel()
        self.payroll_source.setWordWrap(True)
        sources.addWidget(QLabel('ไฟล์บันทึกเวลา'))
        sources.addWidget(self.attendance_source)
        sources.addWidget(QLabel('ไฟล์เงินเดือน'))
        sources.addWidget(self.payroll_source)
        layout.addWidget(sources)

        self.empty_state = SectionContainer('ข้อมูลเงินเดือน')
        self.empty_text = QLabel('ยังไม่มีข้อมูลเงินเดือนสำหรับเดือนนี้')
        self.empty_text.setWordWrap(True)
        self.empty_state.addWidget(self.empty_text)
        layout.addWidget(self.empty_state)

        self.legacy_button = QPushButton('เปิดเครื่องมือเงินเดือนเพิ่มเติม')
        self.legacy_button.setToolTip('เครื่องมือเดิมสำหรับการเตรียมสำเนา โปรไฟล์ ปฏิทิน และงานขั้นสูง')
        layout.addWidget(self.legacy_button)
        layout.addStretch()

    @staticmethod
    def _metric(title):
        card = SectionContainer(title)
        value = QLabel('—')
        value.setProperty('role', 'sectionTitle')
        value.setObjectName(f'{title}_value')
        card.addWidget(value)
        card.value = value
        return card

    def refresh(self, snapshot, *, busy=False, error=''):
        self.period.setText(snapshot.period_label)
        self.monitoring_status.setText(f'การเฝ้าดูไฟล์: {snapshot.monitoring_label}')
        self.payroll_status.setText(f'เงินเดือน: {snapshot.payroll_label}')
        self.startup_status.setText(snapshot.startup_label)
        self.output_status.setText(f'ผลลัพธ์ Excel: {snapshot.output_label}')
        self.employee_card.value.setText('—' if snapshot.employee_count is None else str(snapshot.employee_count))
        self.review_card.value.setText('—' if snapshot.review_count is None else f'{snapshot.review_count} รายการ')
        self.payroll_card.value.setText(snapshot.payroll_label)
        self.attendance_source.setText(snapshot.attendance_label)
        self.payroll_source.setText(snapshot.payroll_label_source)
        if error:
            self.next_action_text.setText(error)
        elif busy:
            self.next_action_text.setText('กำลังประมวลผลข้อมูล โปรดรอผลลัพธ์จากระบบ')
        elif snapshot.payroll_state == 'NO_DRAFT':
            self.next_action_text.setText('ยังไม่มีข้อมูลเงินเดือนสำหรับเดือนนี้ โปรดเลือกไฟล์สำเนาและอ่านข้อมูล')
        else:
            self.next_action_text.setText('แสดงสถานะจากข้อมูลที่บันทึกไว้ของรอบที่เลือก')
        self.empty_state.setVisible(snapshot.payroll_state == 'NO_DRAFT')
