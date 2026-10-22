# งานที่ยังต้องทำด้วยคน — Final Acceptance

**สถานะ ณ 22 ตุลาคม 2026:** ระบบผ่านการทดสอบอัตโนมัติและข้อมูลสมมติแล้ว
แต่ยังห้ามเปิดใช้งาน production, ห้ามใช้ไฟล์เงินจริง และห้าม bypass Windows
security ทุกกรณี

เอกสารนี้มีเฉพาะงานที่ Codex ทำแทนไม่ได้จริง ๆ เท่านั้น งานทดสอบอัตโนมัติ,
การตรวจ hash/signature แบบอ่านอย่างเดียว, source Excel COM และการตรวจ UI
แบบ native Qt ได้ทำและบันทึกไว้แล้วใน
[รายงาน automated completion](03-automated-completion-report.md).

## 1. ยืนยัน UI และ System Tray บนเดสก์ท็อปจริง

**ผู้รับผิดชอบ:** ผู้ทดสอบ Windows
**เหตุผลที่ต้องทำเอง:** ต้องกดผ่าน notification area, ดูจอ/DPI จริง และยืนยัน
ความรู้สึกการใช้งาน ซึ่ง Qt automation ทำแทนไม่ได้อย่างน่าเชื่อถือ

ใช้เฉพาะ QA mode และข้อมูลสมมติ:

```powershell
Set-Location 'C:\Users\NTP\Downloads\NTP payroll'
& '.\.venv\Scripts\python.exe' -X utf8 -m app.main --qa-ui
```

- [ ] เปิด Overview, Review, History, Problems, Settings และดูข้อความไทย,
  scrolling, ตาราง และ empty state ที่ DPI/จอจริง
- [ ] เปลี่ยน ก.ย. -> ต.ค. -> พ.ย.; พ.ย. ต้องไม่มีแถว/selection เก่าค้าง
- [ ] ทดสอบ Tab, Shift+Tab, Enter, Space และปุ่มลูกศร โดยไม่กดคำนวณ,
  ยืนยัน, เขียน Excel, lock/reopen/retry หรือ Resume Monitoring
- [ ] กด X แล้วตรวจว่าซ่อนใน tray; ทดลอง Tray > Open/Restore และ Tray > Exit
  ว่าเป็น session เดิมและปิดสะอาด
- [ ] บันทึกเพียง PASS/FAIL และภาพข้อมูลสมมติเท่านั้น

## 2. อนุมัติกฎเงินเดือนและบัญชี

**ผู้รับผิดชอบ:** เจ้าของธุรกิจ/ผู้มีอำนาจด้านเงินเดือน
**เหตุผลที่ต้องทำเอง:** การคำนวณด้วยข้อมูลสมมติพิสูจน์ implementation ไม่ได้
เป็นการอนุมัติอัตรา, กฎ, หรือยอดเงินจริง

- [ ] อนุมัติฐานเงินเดือน, OT ปกติ/วันหยุด, วันลา, เบี้ยขยัน, allowance,
  deduction, ภาษี/ประกันสังคม, rounding และกรณีพิเศษ
- [ ] ยืนยัน payslip, ยอดรวม และกฎวันจ่าย รวมถึงรอบธันวาคม -> มกราคม
- [ ] ลงนามอนุมัติเป็นลายลักษณ์อักษรก่อนเริ่ม UAT แบบ copy-only

## 3. ซ้อมการกู้คืนและกำหนดเจ้าของ backup

**ผู้รับผิดชอบ:** ผู้ปฏิบัติการและเจ้าของข้อมูล
**เหตุผลที่ต้องทำเอง:** ต้องตัดสินใจ retention, escalation และผู้รับผิดชอบจริง

- [ ] ใช้ workbook สมมติใหม่ สร้าง backup แล้วตรวจ SHA-256
- [ ] Restore ไปยังปลายทางใหม่เท่านั้น (ห้าม overwrite ต้นฉบับ)
- [ ] ยืนยันขั้นตอนเมื่อเกิด ambiguous/failed write ว่าจะไม่ auto-retry
- [ ] ระบุผู้รับผิดชอบ retention, backup และ escalation อย่างชัดเจน

## 4. อนุมัติ trusted code signing และ Windows policy

**ผู้รับผิดชอบ:** release owner และ Windows administrator
**เหตุผลที่ต้องทำเอง:** ต้องใช้อัตลักษณ์ signing ที่เชื่อถือได้และ/หรือ policy
approval ที่เป็นสิทธิ์ขององค์กร

- [ ] เลือกและอนุมัติ Microsoft Trusted Signing หรือ CA ที่องค์กรยอมรับ
- [ ] เซ็นและ timestamp EXE, bundled DLL/Python extension, installer และ
  uninstaller ตาม release process ที่อนุมัติ
- [ ] ตรวจ Authenticode และ SHA-256 ชุดใหม่หลัง signing
- [ ] ให้ administrator ยืนยันว่า signing identity ผ่าน App Control policy

ห้ามปิด Smart App Control/App Control/SmartScreen, เพิ่ม exclusion,
แก้ registry/policy หรือสร้าง certificate ที่ไม่น่าเชื่อถือเพื่อเลี่ยงการบล็อก

## 5. ทดสอบ installer และ package ที่เซ็นแล้วใน disposable environment

**ผู้รับผิดชอบ:** release/QA operator ที่ได้รับอนุมัติ
**เหตุผลที่ต้องทำเอง:** ต้องเป็นเครื่องหรือ VM ที่อนุญาตให้ติดตั้ง/ถอนติดตั้งได้
และ frozen EXE ปัจจุบันถูก Code Integrity บล็อก

- [ ] ใช้ Windows VM/account แยกที่ไม่มีข้อมูลเงินจริง
- [ ] ทดสอบ install, launch, upgrade และ uninstall ของ artifact ที่เซ็นแล้ว
- [ ] ตรวจว่าการถอนติดตั้งรักษา candidate state ตามสัญญา และไม่สร้าง
  Scheduled Task โดยไม่ตั้งใจ
- [ ] ทำ packaged Excel COM กับ workbook สมมติใหม่และ Excel instance ที่
  application สร้างเอง
- [ ] ทดสอบ compatibility บนเครื่องสะอาดที่ไม่มี Python project

## 6. อนุมัติการเปิดใช้ production (อนาคตเท่านั้น)

**ผู้รับผิดชอบ:** เจ้าของธุรกิจและผู้มีอำนาจ deploy
**เหตุผลที่ต้องทำเอง:** เป็นการตัดสินใจเชิงธุรกิจและมีสิทธิ์เปลี่ยนผลกระทบจริง

- [ ] ต้องผ่านและเก็บหลักฐานของข้อ 1–5 ก่อน
- [ ] อนุมัติ real-data UAT แบบ copy-only แยกต่างหากก่อน และยืนยัน path
  ของสำเนา/ฐานข้อมูลที่แยกจากของจริง
- [ ] ออกคำสั่งอนุมัติ production เป็นลายลักษณ์อักษร

**จนกว่าจะครบทุกข้อ: ห้ามเปิด production activation, production write หรือ
monitoring กับโฟลเดอร์งานจริง**
