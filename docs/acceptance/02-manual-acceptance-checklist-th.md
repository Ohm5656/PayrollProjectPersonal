# รายการตรวจรับด้วยตนเอง — Final Acceptance

เอกสารนี้ใช้หลัง Technical Final Acceptance เท่านั้น และไม่ได้อนุญาตให้เปิด
production, เขียนไฟล์เงินจริง, เปิด monitoring หรือเปลี่ยน Windows security
policy โดยอัตโนมัติ

## ก่อนเริ่ม

- [ ] ใช้ข้อมูลพนักงานสมมติและไฟล์สำเนาที่ได้รับอนุมัติเท่านั้น
- [ ] ปิด Excel ของผู้ใช้ก่อนทดสอบ Excel native
- [ ] ปิด candidate ที่กำลังทำงานผ่าน Tray > Exit ก่อนเริ่มรอบใหม่
- [ ] ยืนยันว่าไม่ใช้ workbook, database หรือ reference data จริง
- [ ] ห้ามกดคำนวณ ยืนยัน เขียน Excel ล็อกรอบ เปิดรอบใหม่ Retry หรือ Resume
  Monitoring ระหว่างตรวจ UI
- [ ] ห้ามปิด Smart App Control, App Control, SmartScreen หรือเพิ่ม exclusion

## A. Windows UI, Tray และ DPI

เปิด source QA mode:

```powershell
Set-Location 'C:\Users\NTP\Downloads\NTP payroll'
& '.\.venv\Scripts\python.exe' -X utf8 -m app.main --qa-ui
```

- [ ] Overview, Review, History, Problems และ Settings เปิดได้
- [ ] เปลี่ยนเดือน กันยายน → ตุลาคม → พฤศจิกายน แล้วตารางพนักงาน, status
  และปุ่ม action ต้องตรงกับรอบที่เลือก
- [ ] เดือนที่ไม่มี draft ต้องไม่มีพนักงานหรือ selection เก่าค้างอยู่
- [ ] เปิด/ปิด Employee Detail, History Detail และ Job Detail แล้วรอบที่เลือก
  ไม่เปลี่ยนเอง
- [ ] Review ว่างแสดง empty state; History/Problems ค้นหา กรอง และเปลี่ยนหน้าได้
  โดยไม่เกิดการเขียนข้อมูล
- [ ] Thai text อ่านได้ ไม่ทับ/ไม่ถูกตัด และ scroll ได้
- [ ] ทดสอบ Tab, Shift+Tab, Enter, Space และปุ่มลูกศร; focus ต้องเป็นลำดับและ
  ไม่มี action อันตรายถูกเรียกเอง
- [ ] ปรับขนาด 1920×1080, 1366×768, 1024×768, 900×700 และ DPI จริง;
  ตรวจ header ตาราง และข้อความ
- [ ] กด X แล้วซ่อน Tray โดยไม่เริ่ม monitoring
- [ ] Tray > Open/Restore ต้องกลับหน้าต่างเดิม ไม่สร้างหน้าต่างซ้ำ
- [ ] Tray > Exit ต้องปิดสะอาด และเปิดซ้ำเพื่อตรวจ single-instance
- [ ] บันทึก PASS / FAIL / NOT VERIFIED พร้อมภาพที่ไม่มีข้อมูลจริง

## B. เจ้าของธุรกิจ — กฎเงินเดือนและบัญชี

- [ ] ยืนยันพนักงานและฐานเงินเดือน
- [ ] อนุมัติ OT ปกติ, OT วันหยุด, งานวันหยุด และกฎปัดเศษ
- [ ] อนุมัติปฏิทิน, การลา, เบี้ยขยัน, allowance, deduction, ภาษี และประกันสังคม
- [ ] ตรวจยอดรายบุคคล, payslip, ยอดรวมเดือน และวันจ่าย
- [ ] ตรวจกรณีธันวาคม → มกราคม
- [ ] ลงชื่อรับรองกฎก่อนอนุญาต UAT ข้อมูลจริงแบบ copy-only

ผล automated synthetic test ไม่ใช่การอนุมัติกฎธุรกิจจริง

## C. Backup และ Recovery

- [ ] ใช้ workbook สมมติใหม่ ทำ backup ก่อนเขียน และตรวจ SHA-256
- [ ] Restore ไปปลายทางใหม่เท่านั้น; ห้าม overwrite ไฟล์เดิม
- [ ] ตรวจ SQLite snapshot ใน workspace ทดสอบ
- [ ] ทดสอบ source/revision เปลี่ยนแล้วระบบปฏิเสธชัดเจน
- [ ] ทดสอบ failed/ambiguous write และยืนยันว่าไม่มี destructive auto-retry
- [ ] ตกลงผู้รับผิดชอบ retention, backup และ escalation

## D. UAT ข้อมูลจริงแบบ copy-only

ต้องมีอนุญาตแยกต่างหาก

- [ ] เจ้าของข้อมูลอนุมัติเป็นลายลักษณ์อักษร
- [ ] สร้างสำเนา attendance/payroll ที่แยกจากต้นฉบับ
- [ ] ใช้ database/workspace แยกและยืนยัน path
- [ ] ตรวจผลกับยอดที่อนุมัติก่อนเขียนไฟล์
- [ ] ใช้ Excel instance ที่โปรแกรมสร้างเองกับ workbook สำเนาเท่านั้น
- [ ] เก็บหลักฐาน backup/hash โดยไม่ commit ข้อมูลเงินเดือนจริง

## E. Installer และ executable ที่ trusted

ปัจจุบัน EXE/installer เป็น unsigned และ frozen EXE ถูก Windows Application
Control บล็อก ห้าม bypass

- [ ] Release owner อนุมัติ Microsoft Trusted Signing หรือ trusted CA
- [ ] ผู้ดูแล Windows ยืนยันว่า signing identity ผ่าน policy
- [ ] เซ็น/timestamp EXE, DLL/Python extension, installer และ uninstaller
- [ ] ตรวจ Authenticode และ hash ใหม่หลัง signing
- [ ] ใช้ disposable Windows VM/account ที่ได้รับอนุมัติทดสอบ install, launch,
  upgrade และ uninstall
- [ ] ตรวจ packaged Excel COM ด้วย workbook สมมติใหม่
- [ ] ตรวจ clean-machine compatibility โดยไม่ติดตั้ง Python project

## F. อนุมัติ deploy ในอนาคต

- [ ] ทุกหัวข้อ A–E ผ่านพร้อมหลักฐาน
- [ ] ไม่มี critical defect เปิดอยู่
- [ ] เจ้าของธุรกิจอนุมัติ UAT และกฎเงินเดือน
- [ ] ผู้ปฏิบัติงานอนุมัติ backup/recovery และ retention
- [ ] ผู้ดูแล Windows อนุมัติ trusted deployment
- [ ] มีคำสั่งอนุมัติ production เป็นลายลักษณ์อักษร

จนกว่าจะครบทุกข้อ: **ห้ามเปิดใช้งาน production**
