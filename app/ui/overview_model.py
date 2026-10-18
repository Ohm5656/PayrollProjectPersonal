"""Read-only presentation model for the Overview dashboard.

The model intentionally reads existing services only.  It is not a second
payroll engine and never starts monitoring, mutates a run, or touches Excel.
"""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.services.automation_runtime import RuntimeState
from app.services.windows_startup import StartupState


THAI_MONTHS = (
    'มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน',
    'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม',
)


@dataclass(frozen=True)
class OverviewSnapshot:
    year: int
    month: int
    period_label: str
    payroll_state: str
    payroll_label: str
    employee_count: int | None
    review_count: int | None
    monitoring_state: str
    monitoring_label: str
    monitoring_detail: str
    startup_state: str
    startup_label: str
    output_label: str
    job_state: str | None
    job_updated_at: str | None
    attendance_path: str | None
    payroll_path: str | None
    attendance_label: str
    payroll_label_source: str


@dataclass(frozen=True)
class OverviewAction:
    """The one explicit, state-safe action offered by the Overview page."""
    action_id: str | None
    label: str | None
    detail: str
    enabled: bool
    visible: bool = True


def overview_action(snapshot, *, has_sources, writer_available, busy):
    """Map persisted payroll state to one action without performing it."""
    state = snapshot.payroll_state
    if state == 'NO_DRAFT':
        detail = ('เลือกไฟล์สำเนาบันทึกเวลาและไฟล์เงินเดือน แล้วอ่านข้อมูลเพื่อเตรียมฉบับร่าง'
                  if has_sources else 'โปรดเลือกไฟล์สำเนาบันทึกเวลาและไฟล์เงินเดือนก่อน')
        return OverviewAction('read', 'อ่านข้อมูลและเตรียมฉบับร่าง', detail,
                              bool(has_sources) and not busy)
    if state in {'DRAFT', 'NEEDS_REVIEW'}:
        return OverviewAction('review', 'ตรวจสอบรายการ',
                              'ตรวจสอบและแก้ไขรายการที่ต้องยืนยันก่อนดำเนินการต่อ', not busy)
    if state == 'READY':
        return OverviewAction('confirm', 'ยืนยันเงินเดือน',
                              'ข้อมูลพร้อมยืนยันแล้ว การยืนยันยังไม่เขียนข้อมูลลง Excel', not busy)
    if state == 'CONFIRMED':
        detail = ('ยืนยันแล้ว พร้อมเขียนลงไฟล์สำเนา'
                  if writer_available else 'ยังไม่มีบริการเขียนไฟล์สำเนา จึงไม่สามารถเขียน Excel ได้')
        return OverviewAction('write', 'เขียนลงไฟล์สำเนา', detail,
                              bool(writer_available) and not busy)
    if state == 'WRITTEN':
        return OverviewAction('lock', 'ปิดรอบเงินเดือน',
                              'ตรวจสอบไฟล์สำเนาแล้วจึงปิดรอบเงินเดือน', not busy)
    if state == 'LOCKED':
        return OverviewAction(None, None, 'รอบเงินเดือนถูกปิดแล้ว', False, visible=False)
    return OverviewAction(None, None, 'ไม่สามารถระบุขั้นตอนถัดไปของรอบที่เลือกได้', False, visible=False)


def thai_period(year, month):
    if not 1 <= int(month) <= 12:
        raise ValueError('Month must be between 1 and 12')
    return f'{THAI_MONTHS[int(month) - 1]} {int(year) + 543}'


def _source_label(path):
    if not path:
        return 'ยังไม่ได้เลือกไฟล์สำเนา'
    source = Path(path)
    if not source.is_file():
        return f'{source.name or source} — ไม่พบไฟล์สำเนา'
    updated = datetime.fromtimestamp(source.stat().st_mtime).strftime('%d/%m/%Y %H:%M')
    return f'{source.name} — แก้ไขล่าสุด {updated}'


def _monitoring(runtime):
    if runtime is None:
        return 'UNKNOWN', 'ไม่สามารถตรวจสอบสถานะการเฝ้าดูได้', 'ไม่มี runtime ที่เชื่อมต่อกับหน้าต่าง'
    state = str(runtime.state)
    labels = {
        RuntimeState.DISABLED: ('หยุดเฝ้าดูไฟล์', 'การหยุดเฝ้าดูเป็นการตั้งค่าแยกจากการเริ่มพร้อม Windows'),
        RuntimeState.WATCHING: ('กำลังเฝ้าดูไฟล์', 'ระบบกำลังทำงานเบื้องหลังตามการตั้งค่าปัจจุบัน'),
        RuntimeState.PROCESSING: ('กำลังประมวลผลไฟล์', 'กำลังอ่านและตรวจสอบไฟล์สำเนา'),
        RuntimeState.REVIEW_REQUIRED: ('ต้องตรวจสอบผลการประมวลผล', 'มีข้อมูลที่ต้องให้ผู้ใช้ตรวจสอบ'),
        RuntimeState.ERROR: ('การเฝ้าดูไฟล์มีปัญหา', 'ดูรายละเอียดการกู้คืนใน Phase D.5'),
    }
    label, detail = labels.get(state, ('ไม่สามารถตรวจสอบสถานะการเฝ้าดูได้', 'runtime ส่งสถานะที่ไม่รู้จัก'))
    return state, label, detail


def _startup(startup_service):
    if startup_service is None:
        return 'UNKNOWN', 'ไม่สามารถตรวจสอบสถานะการเริ่มพร้อม Windows ได้'
    try:
        status = startup_service.validate()
    except Exception:
        return 'ERROR', 'ไม่สามารถตรวจสอบสถานะการเริ่มพร้อม Windows ได้'
    if status.message.startswith('โหมดทดสอบ:'):
        return str(status.state), status.message
    labels = {
        StartupState.VALID: 'เริ่มพร้อม Windows: เปิดใช้งานแล้ว',
        StartupState.NOT_INSTALLED: 'เริ่มพร้อม Windows: ปิดอยู่',
        StartupState.NEEDS_REPAIR: 'เริ่มพร้อม Windows: ต้องซ่อมแซม',
        StartupState.UNAVAILABLE: 'ไม่สามารถตรวจสอบสถานะการเริ่มพร้อม Windows ได้',
        StartupState.INVALID_LAUNCH: 'เริ่มพร้อม Windows: การตั้งค่าไม่พร้อมใช้งาน',
        StartupState.ERROR: 'ไม่สามารถตรวจสอบสถานะการเริ่มพร้อม Windows ได้',
    }
    return str(status.state), labels.get(status.state, 'ไม่สามารถตรวจสอบสถานะการเริ่มพร้อม Windows ได้')


class OverviewViewModel:
    """Adapts authoritative persisted/runtime values into dashboard text."""
    def __init__(self, service, *, runtime=None, writer=None, startup_service=None):
        self.service = service
        self.runtime = runtime
        self.writer = writer
        self.startup_service = startup_service

    def snapshot(self, year, month, *, selected_sources=None):
        """Read data only; selected sources fill gaps before a draft exists."""
        run, draft = self.service.current(int(year), int(month))
        sources = selected_sources or {}
        attendance_path = draft.source_path if draft else sources.get('attendance')
        payroll_path = draft.payroll_path if draft else sources.get('payroll')
        payroll_state = str(run['state']) if run else 'NO_DRAFT'
        payroll_labels = {
            'NO_DRAFT': 'ยังไม่มีข้อมูลเงินเดือนสำหรับเดือนนี้',
            'DRAFT': 'ฉบับร่างเงินเดือน',
            'NEEDS_REVIEW': 'ต้องตรวจสอบรายการเงินเดือน',
            'READY': 'พร้อมยืนยันเงินเดือน',
            'CONFIRMED': 'ยืนยันเงินเดือนแล้ว',
            'WRITTEN': 'บันทึกลงไฟล์สำเนาแล้ว',
            'LOCKED': 'ปิดรอบเงินเดือนแล้ว',
        }
        employee_count = sum(bool(employee.employee_id) for employee in draft.employees) if draft else None
        review_count = len(draft.issues) if draft else None
        monitoring_state, monitoring_label, monitoring_detail = _monitoring(self.runtime)
        startup_state, startup_label = _startup(self.startup_service)
        job = self._job_for_period(int(year), int(month))
        output_label = self._output_label(payroll_state)
        return OverviewSnapshot(
            int(year), int(month), thai_period(year, month), payroll_state,
            payroll_labels.get(payroll_state, 'ไม่สามารถตรวจสอบสถานะเงินเดือนได้'),
            employee_count, review_count, monitoring_state, monitoring_label, monitoring_detail,
            startup_state, startup_label, output_label,
            str(job['state']) if job else None, job.get('updated_at') if job else None,
            attendance_path, payroll_path, _source_label(attendance_path), _source_label(payroll_path),
        )

    def _job_for_period(self, year, month):
        if self.runtime is None:
            return None
        jobs = getattr(self.runtime, 'jobs', None)
        if jobs is None:
            return None
        for job in jobs.latest():
            if job.get('period_year') == year and job.get('period_month') == month:
                return job
        return None

    def _output_label(self, payroll_state):
        if self.writer is None:
            return 'ยังไม่พร้อมเขียนไฟล์สำเนา'
        if payroll_state in {'WRITTEN', 'LOCKED'}:
            return 'บันทึกลงไฟล์สำเนาแล้ว'
        if payroll_state == 'CONFIRMED':
            return 'ยืนยันแล้ว รอเขียนลงไฟล์สำเนา'
        return 'โหมดเขียนได้เฉพาะไฟล์สำเนา'
