"""Translate presentation without changing persisted enums or evidence."""
LABELS={'DRAFT':'ฉบับร่าง','READY':'พร้อมยืนยัน','NEEDS_REVIEW':'ต้องตรวจสอบ','REVIEW_REQUIRED':'ต้องตรวจสอบ',
 'UNKNOWN_RULE':'ยังไม่มีเงื่อนไขที่ยืนยัน','AUTO_CALCULATED':'คำนวณจากบันทึกเวลา','RECURRING':'ค่าประจำ',
 'MANUAL':'ยืนยันจำนวนในเดือนนี้','AUTO_REUSE':'ใช้ค่าประจำเดิม','ALWAYS_SUGGEST':'เสนอค่าเดิมให้ยืนยัน',
 'NEVER_REUSE':'ไม่ใช้ค่าเดิมอัตโนมัติ','ONE_TIME':'รายการครั้งเดียว','CONFIRMED':'ยืนยันเงินเดือนแล้ว',
 'WRITTEN':'บันทึกลง Excel แล้ว','LOCKED':'ปิดรอบเดือนแล้ว',
 'DRAFT_CALCULATED':'คำนวณฉบับร่าง','PAYROLL_CONFIRMED':'ยืนยันเงินเดือน','MONTH_REOPENED':'เปิดรอบเดือนใหม่',
 'MONTH_LOCKED':'ปิดรอบเดือน','REVIEW_DECISION':'บันทึกการตรวจสอบ','PROFILE_CONFIRMED':'ยืนยันค่าประจำ',
 'CALENDAR_CONFIRMED':'ยืนยันปฏิทิน','RULE_CONFIRMED':'ยืนยันเงื่อนไข','ALIAS_CONFIRMED':'ยืนยันชื่อพนักงาน',
 'EMPLOYEE_CREATED':'เพิ่มพนักงาน','VALUE_REMEMBERED':'จำค่าประจำ','HISTORY_IMPORTED':'อ่านข้อมูลย้อนหลัง',
 'WORKBOOK_BACKUP':'สำรองไฟล์','WORKBOOK_WRITTEN':'บันทึกเงินเดือนลง Excel','WORKBOOK_WRITE_FAILED':'บันทึกไฟล์ไม่สำเร็จ',
 'SINGLE_EMPLOYEE_COPY_TEST':'ทดสอบสำเนารายคน','ATTENDANCE_CHANGED_AFTER_CONFIRMATION':'พบข้อมูลเปลี่ยนหลังยืนยัน',
 'Sum of validated numeric daily attendance values':'รวมยอดรายวันที่ตรวจสอบแล้ว',
 'Previous month is a suggestion only':'ค่าเดือนก่อนเป็นข้อเสนอ รอผู้ใช้ยืนยัน',
 'Explicit AUTO_REUSE policy':'ใช้ค่าประจำเดิมตามนโยบายที่ยืนยัน',
 'Confirmed employee recurring profile':'ใช้ค่าประจำพนักงานที่ยืนยันแล้ว',
 'Monthly manual value; never automatically carried forward':'รายการเดือนนี้ต้องยืนยันใหม่ ไม่ยกยอดมาอัตโนมัติ',
 'No attendance required; confirm this monthly amount':'พนักงานไม่ต้องใช้บันทึกเวลา โปรดยืนยันยอดเดือนนี้',
 'Only confirmed OT classifications and work-day decisions':'ใช้ประเภท OT และวันทำงานที่ยืนยันแล้ว',
 'Employee bonus configuration, confirmed required workdays and confirmed leave rules':'ใช้เบี้ยขยัน ปฏิทิน และผลการลาที่ตรวจสอบแล้ว',
 'Preview of validated existing Excel arithmetic; Excel recalculation must agree':'คำนวณตามสูตรเดิมในไฟล์เงินเดือน และตรวจยอดก่อนบันทึก'}


def text(value):return LABELS.get(str(value),str(value))


def issue_text(issue):
    if issue.kind.startswith('SOURCE_') and not any('\u0e00'<=c<='\u0e7f' for c in issue.message):
        return 'ข้อมูลบันทึกเวลาต้องตรวจสอบ (ชีต '+str(issue.sheet or '')+' ช่อง '+str(issue.cell or '')+')'
    return text(issue.message)


def raw_evidence(issue):return 'ต้องยืนยันช่องในใบเงินเดือน' if issue.kind=='PAYSLIP_MAPPING' else issue.raw_text


def error_text(message):
    if any('\u0e00'<=c<='\u0e7f' for c in message):return message
    return 'ดำเนินการไม่สำเร็จ กรุณาตรวจไฟล์สำเนาและรายการที่ต้องตรวจสอบ รายละเอียดอยู่ในไฟล์บันทึกของโปรแกรม'
