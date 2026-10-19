"""Read-only deployment readiness assessment; never grants write permission."""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sqlite3

from app.safety import TEST_ROOT
from app.db.migrations import MIGRATIONS
from app.services.monthly_workflow import validate_workflow_configuration


@dataclass(frozen=True)
class ReadinessCheck:
    id: str
    status: str
    summary_th: str
    next_step_th: str
    evidence: str
    read_only: bool = True


@dataclass(frozen=True)
class ReadinessReport:
    created_at: str
    checks: tuple[ReadinessCheck, ...]


class ReadinessService:
    def __init__(self, workflow, *, runtime=None, database_path=None, excel_probe=None, disk_usage=shutil.disk_usage):
        self.workflow, self.runtime = workflow, runtime
        self.database_path = Path(database_path) if database_path else None
        self.excel_probe, self.disk_usage = excel_probe, disk_usage

    def assess(self):
        checks = [self._boundary(), self._workflow(), self._database(), self._disk(), self._monitoring(), self._excel()]
        return ReadinessReport(datetime.now(timezone.utc).isoformat(), tuple(checks))

    def _boundary(self):
        return ReadinessCheck('COPY_ONLY_BOUNDARY', 'PASS', 'ระบบจำกัดการเขียนไว้ในพื้นที่ทดสอบ', 'ยังไม่ได้รับอนุมัติใช้งานจริง', str(TEST_ROOT))

    def _workflow(self):
        config = self.workflow.configuration() or {}
        try:
            validate_workflow_configuration(config.get('attendance_folder'), config.get('payroll_folder'), config.get('template_path'))
        except Exception as exc:
            return ReadinessCheck('WORKFLOW_CONFIGURATION', 'FAIL', 'โฟลเดอร์สำหรับทดสอบไม่พร้อมใช้งาน', 'ตรวจสอบโฟลเดอร์และไฟล์แม่แบบ', type(exc).__name__)
        return ReadinessCheck('WORKFLOW_CONFIGURATION', 'PASS', 'การตั้งค่าไฟล์ทดสอบพร้อมใช้งาน', 'คงการทำงานแบบสำเนาทดสอบ', 'validated paths')

    def _database(self):
        if self.database_path is None or not self.database_path.is_file():
            return ReadinessCheck('DATABASE_SCHEMA', 'NOT_VERIFIED', 'ยังไม่ได้ตรวจสอบฐานข้อมูลแบบอ่านอย่างเดียว', 'เลือกฐานข้อมูลทดสอบที่มีอยู่', 'no database path')
        try:
            uri = self.database_path.resolve().as_uri() + '?mode=ro'
            with sqlite3.connect(uri, uri=True) as con:
                integrity = con.execute('PRAGMA integrity_check').fetchone()[0]
                versions = {row[0] for row in con.execute('SELECT version FROM schema_migrations')}
            known = {version for version, _ in MIGRATIONS}
            status = 'PASS' if integrity == 'ok' and versions == known else 'FAIL'
            return ReadinessCheck('DATABASE_SCHEMA', status, 'ฐานข้อมูลทดสอบตรวจสอบความสมบูรณ์แล้ว' if status == 'PASS' else 'ฐานข้อมูลทดสอบมีปัญหา', 'หยุดและตรวจสอบฐานข้อมูล' if status == 'FAIL' else 'ใช้เฉพาะฐานข้อมูลทดสอบ', f'integrity={integrity}; migrations={versions}')
        except Exception as exc:
            return ReadinessCheck('DATABASE_SCHEMA', 'NOT_VERIFIED', 'ไม่สามารถตรวจสอบฐานข้อมูลแบบอ่านอย่างเดียว', 'ห้ามเปิดฐานข้อมูลปกติเพื่อตรวจสอบ', type(exc).__name__)

    def _disk(self):
        config = self.workflow.configuration() or {}
        folder = config.get('payroll_folder')
        if not folder or not Path(folder).is_dir():
            return ReadinessCheck('DISK_SPACE', 'NOT_VERIFIED', 'ยังไม่มีโฟลเดอร์ผลลัพธ์สำหรับตรวจพื้นที่ว่าง', 'กำหนดโฟลเดอร์ทดสอบก่อน', 'missing output folder')
        free = self.disk_usage(folder).free
        return ReadinessCheck('DISK_SPACE', 'PASS' if free >= 10 * 1024 * 1024 else 'WARNING', 'มีพื้นที่ว่างสำหรับสำเนาทดสอบ' if free >= 10 * 1024 * 1024 else 'พื้นที่ว่างอาจไม่เพียงพอ', 'เพิ่มพื้นที่ว่างก่อนทดสอบ' if free < 10 * 1024 * 1024 else 'ดำเนินการกับสำเนาทดสอบเท่านั้น', str(free))

    def _monitoring(self):
        state = str(getattr(self.runtime, 'state', 'UNKNOWN')) if self.runtime else 'UNKNOWN'
        status = 'PASS' if state == 'DISABLED' else 'WARNING' if state in {'WATCHING', 'PROCESSING'} else 'NOT_VERIFIED'
        return ReadinessCheck('MONITORING_STATE', status, 'การเฝ้าดูไฟล์หยุดอยู่' if status == 'PASS' else 'ไม่สามารถยืนยันสถานะการเฝ้าดูไฟล์' if status == 'NOT_VERIFIED' else 'พบการเฝ้าดูไฟล์กำลังทำงาน', 'หยุดการเฝ้าดูไฟล์ก่อนตรวจความพร้อม' if status != 'PASS' else 'ไม่เปิดการเฝ้าดูไฟล์อัตโนมัติ', state)

    def _excel(self):
        if self.excel_probe is None:
            return ReadinessCheck('EXCEL_COM', 'NOT_VERIFIED', 'ยังไม่ได้ตรวจสอบ Excel แบบแยก instance', 'ทดสอบด้วย Excel instance ที่ระบบเป็นเจ้าของเท่านั้น', 'probe unavailable')
        try:
            version = self.excel_probe()
            return ReadinessCheck('EXCEL_COM', 'PASS', 'Excel พร้อมสำหรับการทดสอบแบบแยก instance', 'ใช้เฉพาะไฟล์สังเคราะห์', str(version))
        except Exception as exc:
            return ReadinessCheck('EXCEL_COM', 'NOT_VERIFIED', 'Excel ไม่พร้อมสำหรับการประมวลผล', 'ตรวจสอบ Excel โดยไม่เชื่อมต่อกับ Excel ของผู้ใช้', type(exc).__name__)
