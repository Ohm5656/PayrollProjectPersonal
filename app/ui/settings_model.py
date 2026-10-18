"""Read-only state model for the Settings and first-run presentations.

This module deliberately has no Qt widgets and no command side effects.  In
particular, reading a Settings page must not change the persisted monitoring
preference, create an attendance watcher, or ask the operating system to
install a startup task.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.services.automation_runtime import RuntimeState
from app.services.windows_startup import StartupState, StartupStatus


@dataclass(frozen=True)
class SettingsSnapshot:
    attendance_folder: str
    payroll_folder: str
    template_path: str
    configuration_state: str
    configuration_detail: str
    watch_preference: bool | None
    monitoring_state: str
    monitoring_label: str
    monitoring_detail: str
    startup_state: str
    startup_label: str
    startup_detail: str
    startup_enabled: bool
    startup_repair_available: bool
    copies_only: bool


def _existing_path(value, *, directory=False):
    if not value:
        return False
    path = Path(value)
    return path.is_dir() if directory else path.is_file()


def _configuration(workflow):
    config = workflow.configuration() or {}
    attendance = str(config.get('attendance_folder') or '')
    payroll = str(config.get('payroll_folder') or '')
    template = str(config.get('template_path') or '')
    if not config:
        return attendance, payroll, template, 'NOT_CONFIGURED', 'ยังไม่ได้เลือกโฟลเดอร์ทำงาน'
    required = (attendance, payroll, template)
    if not all(required):
        return attendance, payroll, template, 'INCOMPLETE', 'ข้อมูลโฟลเดอร์ทำงานยังไม่ครบ'
    if not _existing_path(attendance, directory=True) or not _existing_path(payroll, directory=True):
        return attendance, payroll, template, 'MISSING_PATH', 'ไม่พบโฟลเดอร์ทำงานที่บันทึกไว้'
    if not _existing_path(template):
        return attendance, payroll, template, 'MISSING_TEMPLATE', 'ไม่พบไฟล์แม่แบบที่บันทึกไว้'
    return attendance, payroll, template, 'READY', 'โฟลเดอร์ทำงานพร้อมใช้งาน'


def _monitoring(runtime, preference):
    preference_detail = {
        None: 'ยังไม่ได้เลือกการเฝ้าดูไฟล์โดยชัดแจ้ง',
        False: 'ผู้ใช้หยุดการเฝ้าดูไฟล์ไว้',
        True: 'ผู้ใช้เปิดการเฝ้าดูไฟล์ไว้',
    }[preference]
    if runtime is None:
        return 'UNKNOWN', 'ไม่พบ runtime สำหรับตรวจสอบการเฝ้าดูไฟล์', preference_detail
    state = str(runtime.state)
    labels = {
        RuntimeState.DISABLED: 'หยุดเฝ้าดูไฟล์',
        RuntimeState.WATCHING: 'กำลังเฝ้าดูไฟล์',
        RuntimeState.PROCESSING: 'กำลังประมวลผลไฟล์',
        RuntimeState.REVIEW_REQUIRED: 'รอการตรวจสอบ',
        RuntimeState.ERROR: 'การเฝ้าดูไฟล์มีปัญหา',
    }
    return state, labels.get(state, 'ไม่ทราบสถานะการเฝ้าดูไฟล์'), preference_detail


def _startup_labels(status):
    labels = {
        StartupState.VALID: 'เปิด Start with Windows แล้ว',
        StartupState.NOT_INSTALLED: 'ปิด Start with Windows อยู่',
        StartupState.NEEDS_REPAIR: 'Start with Windows ต้องซ่อมแซม',
        StartupState.INVALID_LAUNCH: 'ไม่พร้อมติดตั้ง Start with Windows',
        StartupState.UNAVAILABLE: 'ไม่สามารถตรวจสอบ Task Scheduler ได้',
        StartupState.ERROR: 'ตรวจสอบ Start with Windows ไม่สำเร็จ',
    }
    return labels.get(status.state, 'ไม่ทราบสถานะ Start with Windows')


class SettingsViewModel:
    """Adapt authoritative configuration into a cached Settings snapshot.

    ``validate`` can invoke PowerShell in production, so it is called only on
    the first snapshot and when the user explicitly requests a refresh.  The
    cached result keeps simple UI refreshes free from blocking OS work.
    """
    def __init__(self, workflow, *, runtime=None, startup_service=None):
        self.workflow = workflow
        self.runtime = runtime
        self.startup_service = startup_service
        self._startup_status = None

    def startup_status(self, *, refresh=False):
        if self._startup_status is not None and not refresh:
            return self._startup_status
        if self.startup_service is None:
            self._startup_status = StartupStatus(StartupState.UNAVAILABLE, 'Startup service is unavailable')
            return self._startup_status
        try:
            self._startup_status = self.startup_service.validate()
        except Exception as exc:  # The presentation remains honest on an OS failure.
            self._startup_status = StartupStatus(StartupState.ERROR, str(exc) or 'Unable to validate startup')
        return self._startup_status

    def snapshot(self, *, refresh_startup=False):
        attendance, payroll, template, config_state, config_detail = _configuration(self.workflow)
        preference = self.workflow.repo.setting('watch_enabled', None)
        if preference not in {None, True, False}:
            preference = bool(preference)
        monitoring_state, monitoring_label, monitoring_detail = _monitoring(self.runtime, preference)
        startup = self.startup_status(refresh=refresh_startup)
        return SettingsSnapshot(
            attendance, payroll, template, config_state, config_detail,
            preference, monitoring_state, monitoring_label, monitoring_detail,
            str(startup.state), _startup_labels(startup), startup.message,
            startup.installed, startup.state == StartupState.NEEDS_REPAIR,
            True,
        )
