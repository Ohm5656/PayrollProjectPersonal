"""Read-only operational health model for the Problems page."""
from dataclasses import dataclass
from pathlib import Path

from app.services.automation_job_service import AutomationJobService, AutomationJobState
from app.services.automation_runtime import RuntimeState
from app.services.workflow_service import WorkflowService
from app.ui.history_model import thai_period, thai_timestamp


@dataclass(frozen=True)
class HealthStatus:
    key: str
    state: str
    label: str
    detail: str
    requires_action: bool = False


@dataclass(frozen=True)
class ProblemJob:
    id: str
    state: str
    state_label: str
    period_label: str
    updated_at: str
    title: str
    detail: str
    failure_code: str | None
    retryable: bool


@dataclass(frozen=True)
class ProblemsSnapshot:
    monitoring: HealthStatus
    jobs: HealthStatus
    configuration: HealthStatus
    writes: HealthStatus
    attention: tuple[ProblemJob, ...]
    recent_jobs: tuple[ProblemJob, ...]
    staged_writes: tuple[dict, ...]


FAILURE_GUIDANCE = {
    'SOURCE_MISSING': ('ไม่พบไฟล์ต้นทาง', 'ตรวจสอบว่าไฟล์บันทึกเวลายังอยู่ในโฟลเดอร์ที่ตั้งค่าไว้'),
    'SOURCE_INVALID': ('ไฟล์ต้นทางไม่พร้อมใช้งาน', 'ตรวจสอบว่าไฟล์ Excel สมบูรณ์และปิดจากโปรแกรมอื่นแล้ว'),
    'SOURCE_CHANGED': ('ไฟล์ต้นทางมีการเปลี่ยนแปลง', 'ระบบสร้างงานใหม่สำหรับข้อมูลปัจจุบันแล้ว แต่ยังไม่ยืนยันว่าประมวลผลสำเร็จ'),
    'SOURCE_CHANGED_OFFLINE': ('ไฟล์ต้นทางเปลี่ยนระหว่างที่โปรแกรมปิดอยู่', 'ตรวจสอบไฟล์ปัจจุบันก่อนเริ่มการประมวลผลใหม่'),
    'CONFIGURATION_CHANGED': ('การตั้งค่าปัจจุบันไม่ตรงกับงานเดิม', 'ตรวจสอบโฟลเดอร์และเทมเพลตก่อนลองดำเนินการอีกครั้ง'),
    'INTERRUPTED': ('การประมวลผลครั้งก่อนหยุดก่อนเสร็จ', 'ตรวจสอบข้อมูลต้นทางก่อนลองประมวลผลอีกครั้ง'),
}

STATE_LABELS = {
    AutomationJobState.PENDING: 'รอประมวลผล',
    AutomationJobState.PROCESSING: 'กำลังประมวลผล',
    AutomationJobState.REVIEW_REQUIRED: 'ต้องตรวจสอบ',
    AutomationJobState.COMPLETED: 'เสร็จแล้ว',
    AutomationJobState.FAILED: 'มีปัญหา',
}


def _period(job):
    year, month = job.get('period_year'), job.get('period_month')
    return thai_period(year, month) if year is not None and month is not None else 'ไม่ระบุรอบเงินเดือน'


class ProblemsViewModel:
    """Adapts persisted jobs and runtime health without changing any state."""
    def __init__(self, service, *, runtime=None):
        self.service = service
        self.runtime = runtime
        self.workflow = WorkflowService(service)
        self.jobs = runtime.jobs if runtime is not None else AutomationJobService(service.repo)

    def snapshot(self, *, limit=50):
        recent = self._jobs(limit)
        staged = self._staged_writes()
        presented = tuple(self.job(job) for job in recent)
        attention = tuple(item for item in presented if item.state in {
            AutomationJobState.FAILED, AutomationJobState.PENDING,
            AutomationJobState.PROCESSING, AutomationJobState.REVIEW_REQUIRED,
        })
        return ProblemsSnapshot(
            self._monitoring(), self._jobs_health(recent), self._configuration(),
            self._writes_health(staged), attention, presented, staged,
        )

    def job(self, job):
        state = str(job.get('state') or 'UNKNOWN')
        failure_code = job.get('failure_code')
        if state == AutomationJobState.FAILED:
            title, fallback = FAILURE_GUIDANCE.get(
                failure_code, ('งานเบื้องหลังไม่สำเร็จ', 'ตรวจสอบรายละเอียดทางเทคนิคและข้อมูลต้นทางก่อนดำเนินการต่อ'))
            detail = job.get('failure_message') or fallback
        elif state == AutomationJobState.REVIEW_REQUIRED:
            title, detail = 'งานต้องตรวจสอบ', 'ตรวจสอบรายการเงินเดือนก่อนยืนยันหรือเขียนไฟล์'
        elif state == AutomationJobState.PENDING:
            title, detail = 'งานกำลังรอประมวลผล', 'ระบบยังไม่ได้บันทึกผลสำเร็จของงานนี้'
        elif state == AutomationJobState.PROCESSING:
            title, detail = 'กำลังประมวลผลข้อมูล', 'รอผลลัพธ์ที่บันทึกโดยระบบก่อนดำเนินการต่อ'
        elif state == AutomationJobState.COMPLETED:
            title, detail = 'งานเสร็จแล้ว', 'การเสร็จของงานไม่ได้หมายถึงการยืนยันหรือเขียนเงินเดือนแล้ว'
        else:
            title, detail = 'สถานะงานไม่รู้จัก', 'ไม่สามารถจัดประเภทสถานะนี้ได้อย่างปลอดภัย'
        return ProblemJob(
            str(job.get('id') or ''), state, STATE_LABELS.get(state, 'ไม่ทราบสถานะ'), _period(job),
            thai_timestamp(job.get('updated_at')), title, detail, failure_code,
            state == AutomationJobState.FAILED and bool(job.get('id')),
        )

    def _jobs(self, limit):
        try:
            return tuple(self.jobs.latest(limit=max(1, min(int(limit), 50))))
        except Exception:
            return ()

    def _staged_writes(self):
        try:
            return tuple(self.jobs.staged_write_inspection())
        except Exception:
            return ()

    def _monitoring(self):
        enabled = bool(self.service.repo.setting('watch_enabled', False))
        if self.runtime is None:
            if not enabled:
                return HealthStatus('monitoring', 'PAUSED', 'หยุดเฝ้าดูไฟล์ตามการตั้งค่าของผู้ใช้',
                                    'ยังไม่มี runtime ที่เชื่อมต่อกับหน้านี้', False)
            return HealthStatus('monitoring', 'UNKNOWN', 'ไม่สามารถตรวจสอบสถานะการเฝ้าดูได้',
                                'ไม่พบ runtime สำหรับยืนยันสถานะปัจจุบัน', True)
        state = str(self.runtime.state)
        if not enabled and state != RuntimeState.ERROR:
            return HealthStatus('monitoring', 'PAUSED', 'หยุดเฝ้าดูไฟล์ตามการตั้งค่าของผู้ใช้',
                                'การหยุดเฝ้าดูไม่ใช่ข้อผิดพลาดของระบบ', False)
        if state == RuntimeState.ERROR:
            fault = getattr(self.runtime, '_health_fault', None)
            detail = fault[1] if fault else 'การเฝ้าดูไฟล์รายงานข้อผิดพลาด'
            return HealthStatus('monitoring', state, 'การเฝ้าดูไฟล์มีปัญหา', detail, True)
        labels = {
            RuntimeState.WATCHING: ('กำลังเฝ้าดูไฟล์', 'การเฝ้าดูทำงานตามการตั้งค่าปัจจุบัน'),
            RuntimeState.PROCESSING: ('กำลังประมวลผลไฟล์', 'รอผลลัพธ์ของงานที่กำลังดำเนินการ'),
            RuntimeState.REVIEW_REQUIRED: ('มีผลลัพธ์ที่ต้องตรวจสอบ', 'การเฝ้าดูยังแยกจากรายการตรวจสอบเงินเดือน'),
            RuntimeState.DISABLED: ('หยุดเฝ้าดูไฟล์', 'runtime รายงานว่าไม่ได้เฝ้าดูไฟล์'),
        }
        label, detail = labels.get(state, ('ไม่สามารถตรวจสอบสถานะการเฝ้าดูได้', 'runtime ส่งสถานะที่ไม่รู้จัก'))
        return HealthStatus('monitoring', state, label, detail, state not in {RuntimeState.WATCHING, RuntimeState.DISABLED})

    def _jobs_health(self, jobs):
        failed = sum(str(job.get('state')) == AutomationJobState.FAILED for job in jobs)
        review = sum(str(job.get('state')) == AutomationJobState.REVIEW_REQUIRED for job in jobs)
        processing = sum(str(job.get('state')) == AutomationJobState.PROCESSING for job in jobs)
        if failed:
            return HealthStatus('jobs', 'FAILED', f'พบงานที่มีปัญหา {failed} รายการ', 'เลือกงานเพื่อดูแนวทางที่ปลอดภัย', True)
        if review:
            return HealthStatus('jobs', 'REVIEW_REQUIRED', f'มีงานต้องตรวจสอบ {review} รายการ', 'ไม่ใช่ข้อผิดพลาดของการเฝ้าดูไฟล์', True)
        if processing:
            return HealthStatus('jobs', 'PROCESSING', f'กำลังประมวลผล {processing} รายการ', 'รอผลลัพธ์ที่บันทึกโดยระบบ', False)
        return HealthStatus('jobs', 'CLEAR', 'ไม่พบปัญหาในรายการงานล่าสุด', 'แสดงเฉพาะงานล่าสุดแบบจำกัดจำนวน', False)

    def _configuration(self):
        config = self.workflow.configuration()
        if not self.workflow.configured():
            return HealthStatus('configuration', 'UNAVAILABLE', 'ยังไม่ได้ตั้งค่าโฟลเดอร์ทำงาน',
                                'ตั้งค่าโฟลเดอร์และเทมเพลตก่อนใช้งานการเฝ้าดูไฟล์', True)
        try:
            available = (Path(config['attendance_folder']).is_dir() and Path(config['payroll_folder']).is_dir()
                         and Path(config['template_path']).is_file())
        except (TypeError, KeyError):
            available = False
        if not available:
            return HealthStatus('configuration', 'UNAVAILABLE', 'ไม่สามารถเข้าถึงการตั้งค่าโฟลเดอร์ได้',
                                'ตรวจสอบโฟลเดอร์ต้นทาง ปลายทาง และไฟล์เทมเพลต', True)
        return HealthStatus('configuration', 'AVAILABLE', 'การตั้งค่าโฟลเดอร์พร้อมใช้งาน',
                            'ตรวจสอบแบบอ่านอย่างเดียวจากการตั้งค่าปัจจุบัน', False)

    @staticmethod
    def _writes_health(staged):
        if staged:
            return HealthStatus('writes', 'STAGED_REQUIRES_REVIEW', 'พบรายการเขียน Excel ที่ต้องตรวจสอบ',
                                'ระบบจะไม่กู้คืน เขียนทับ หรือลบข้อมูลให้อัตโนมัติ', True)
        return HealthStatus('writes', 'CLEAR', 'ไม่พบรายการเขียน Excel ที่ค้างตรวจสอบ',
                            'แสดงเฉพาะรายการ STAGED ที่บันทึกไว้', False)
