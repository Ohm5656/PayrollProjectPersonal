# แพ็กเกจตรวจรับโดยมนุษย์ — NTP Payroll Assistant

**ใช้หลังจาก Automated Engineering Completion เท่านั้น**

เอกสารนี้รวมเฉพาะสิ่งที่การทดสอบอัตโนมัติพิสูจน์แทนคนไม่ได้แล้ว ห้ามใช้
ข้อมูลพนักงานจริง ห้ามเปิด production write ห้ามเปิด monitoring กับโฟลเดอร์จริง
และห้ามปิดหรือ bypass Windows security เพื่อให้โปรแกรมทำงาน

หากขั้นตอนใดให้ผล **FAIL** หรือ **NOT VERIFIED** ให้หยุดที่ขั้นนั้น เก็บหลักฐาน
ที่ไม่มีข้อมูลส่วนบุคคล แล้วส่งกลับเพื่อวิเคราะห์ก่อนเริ่มขั้นต่อไป

## A. เริ่ม QA อย่างปลอดภัย

### ข้อกำหนดก่อนเริ่ม

- ใช้เครื่อง Windows และบัญชีที่อนุญาตให้ทดสอบเท่านั้น
- ใช้ข้อมูล/ไฟล์ Excel สมมติใหม่เท่านั้น ไม่ใช้ workbook, database หรือโฟลเดอร์จริง
- หากมี QA session ของตนเองอยู่ ให้ปิดด้วย Tray > Exit ก่อนเปิดรอบใหม่
- ปิด Excel ของผู้ใช้ก่อนทดสอบ Excel COM; ห้ามปิด Excel ของบุคคลอื่น
- ห้ามกด คำนวณ, ยืนยัน, เขียน Excel, lock/reopen/retry หรือ Resume Monitoring
  ระหว่างตรวจ UI

### คำสั่งเปิด Source QA

```powershell
Set-Location 'C:\Users\NTP\Downloads\NTP payroll'
& '.\.venv\Scripts\python.exe' -X utf8 -m app.main --qa-ui
```

ผลที่คาดหวัง:

- โปรแกรมเปิดเป็น QA mode พร้อมข้อมูลสมมติและ workspace แยกใหม่
- Monitoring ต้องปิดอยู่ และการตั้งค่า Windows startup ต้องแสดงว่า QA mode
  ไม่อนุญาตให้ติดตั้ง
- ไม่มีการอ่าน/เขียนฐานข้อมูลหรือ workbook ปกติ

จบการทดสอบด้วย **Tray > Exit** เท่านั้น แล้วตรวจว่าไม่มีหน้าต่าง QA เหลืออยู่

## B. แบบตรวจ UI และ System Tray

| รหัส | ผู้รับผิดชอบ | วัตถุประสงค์/ขั้นตอน | ผลที่คาดหวัง | หลักฐาน | PASS / FAIL / NOT VERIFIED |
| --- | --- | --- | --- | --- | --- |
| UI-01 | Windows tester | เปิด Overview, Review, History, Problems, Settings | ข้อความไทย ตาราง card และ empty state อ่านได้ ไม่มีพื้นหลังดำ/ข้อความทับกัน | ภาพข้อมูลสมมติ, ความละเอียด/DPI |  |
| UI-02 | Windows tester | เปลี่ยน ก.ย. -> ต.ค. -> พ.ย. แล้วกลับเดือนเดิม | ตาราง, status และ action ตรงเดือน; พ.ย. ไม่มีแถวหรือ selection ค้าง | บันทึกผล |  |
| UI-03 | Windows tester | เปิด/ปิด Employee Detail, History Detail, Job/Problem Detail | dialog เปิดและปิดได้; การดูข้อมูลไม่เปลี่ยน payroll period หรือสถานะ | บันทึกผล |  |
| UI-04 | Windows tester | ใช้ Tab, Shift+Tab, Enter, Space และลูกศร; ปรับ 1920x1080, 1366x768, 1024x768, 900x700 และ DPI จริง | focus เห็นชัด, control เข้าถึงได้, ข้อความไม่ถูกตัด, ไม่มี action อันตรายทำงานเอง | ความละเอียด/DPI, ภาพสมมติ |  |
| TRAY-01 | Windows tester | กด X, คลิก icon ใน notification area, Tray > Open/Restore, Tray > Exit | X ซ่อน session เดิม, restore ไม่สร้างหน้าต่างซ้ำ, Exit ปิดสะอาดและไม่เริ่ม monitoring | บันทึกผล |  |

**ลงชื่อผู้ทดสอบ UI:** ____________________  **วันที่/เวลา:** ____________________

## C. ใบอนุมัติกฎเงินเดือน (ใช้ตัวอย่างสมมติ)

การทดสอบเทคนิคยืนยันว่า engine เก็บ Decimal, review gate, source hash และ
workflow ได้ตาม requirement แต่ไม่สามารถตัดสินกฎของกิจการแทนเจ้าของได้

| รหัส | ตัวอย่างสมมติให้เจ้าของตัดสิน | คำถาม/ผลที่ต้องอนุมัติ | การตัดสินใจ/อัตราที่อนุมัติ | ลายเซ็น |
| --- | --- | --- | --- | --- |
| PAY-01 | พนักงาน A เงินเดือน 20,000 บาท ทำ OT วันทำงาน 2 ชั่วโมง | นิยามชั่วโมง, อัตรา OT, rounding และเอกสารอ้างอิงคืออะไร |  |  |
| PAY-02 | พนักงาน A ทำงานวันหยุด/มีวันลา | แยก OT วันหยุด, งานวันหยุด, วันลา และ review-required อย่างไร |  |  |
| PAY-03 | พนักงาน A มีเบี้ยขยัน, ค่าเดินทาง, allowance และโบนัสพิเศษ | รายการใดเกิดอัตโนมัติ รายการใดต้องกรอก/อนุมัติ และ carry-forward ได้หรือไม่ |  |  |
| PAY-04 | พนักงาน A มีหักครั้งเดียวและหักประจำ | ข้อจำกัดยอดติดลบ, ลำดับการหัก, ภาษี/ประกันสังคม และเหตุผลที่ต้องบันทึก |  |  |
| PAY-05 | เดือนธันวาคม 2569 | ยืนยัน payroll period, payslip, payment date เดือนถัดไป และวิธีปิด/เปิดรอบ |  |  |
| PAY-06 | ชื่อซ้ำ, ไม่พบพนักงาน, attendance ขาด หรือ source เปลี่ยน | ต้องหยุดให้ review เมื่อใด และใครมีสิทธิ์ตัดสิน |  |  |

**เจ้าของกฎเงินเดือน:** ____________________  **วันที่:** ____________________

ก่อน copy-only UAT ด้วยข้อมูลจริง ต้องมีหนังสืออนุมัติแยกต่างหากและใช้สำเนา
attendance/payroll/database ที่ยืนยัน path แล้วเท่านั้น

## D. Backup และ Recovery Acceptance

| รหัส | ผู้รับผิดชอบ | ขั้นตอน | ผลที่คาดหวัง | หลักฐาน | PASS / FAIL / NOT VERIFIED |
| --- | --- | --- | --- | --- | --- |
| REC-01 | Operator | ใช้ workbook สมมติใหม่ สร้าง backup ก่อน write | มี backup และ SHA-256 ตรงกับต้นฉบับก่อน write | path, hash, เวลา |  |
| REC-02 | Operator | restore backup ไปปลายทางใหม่ที่ยังไม่มีไฟล์ | เปิดไฟล์สำเนาได้ สูตร/layout ถูกต้อง; ต้นฉบับไม่ถูก overwrite | path ใหม่, hash, ภาพสมมติ |  |
| REC-03 | Operator | ทดสอบ source/revision เปลี่ยนและกรณี failed/ambiguous write ตามคู่มือ QA | ระบบหยุด/review อย่างปลอดภัย ไม่ destructive retry | audit/log ที่ไม่ระบุข้อมูลจริง |  |
| REC-04 | Data owner | ตัดสิน retention, owner และ escalation | มีชื่อผู้รับผิดชอบและช่วงเก็บ backup ที่อนุมัติ | เอกสารอนุมัติ |  |

**ผู้ปฏิบัติการ:** ____________________  **Data owner:** ____________________

## E. Trusted deployment และ installer

สถานะปัจจุบัน: canonical EXE และ installer **ยัง unsigned**; Windows Code
Integrity บล็อก frozen EXE ก่อนเริ่มทำงาน ห้ามแก้ policy, เพิ่ม exclusion,
trust self-signed certificate หรือ bypass การบล็อก

| รหัส | ผู้รับผิดชอบ | ขั้นตอน | ผลที่คาดหวัง | หลักฐาน | PASS / FAIL / NOT VERIFIED |
| --- | --- | --- | --- | --- | --- |
| REL-01 | Release owner | อนุมัติ Microsoft Trusted Signing หรือ trusted CA และ protected release agent/HSM | มี signing identity ที่องค์กรอนุมัติ; ไม่มี key/secret อยู่ใน repo | เลขอนุมัติ |  |
| REL-02 | Release engineer | เซ็น/timestamp EXE, DLL/PYD, installer และ uninstaller แล้วรัน `packaging\verify_signatures.ps1 -RequireTrustedSignature` | native binary ทุกไฟล์เป็น Valid และมี timestamp; hash ชุดใหม่ถูกบันทึก | JSON verification + hashes |  |
| REL-03 | Windows administrator | ยืนยัน publisher/trusted-signing identity ผ่าน App Control ของเครื่อง/องค์กร | ไม่มีการใช้ policy exception หรือ security bypass | หนังสือยืนยัน |  |
| REL-04 | Release/QA operator | ใน Windows VM/account ที่อนุมัติและไม่มีข้อมูลจริง: install, launch, upgrade, uninstall และ packaged Excel COM | installer/state retention/tray/COM ผ่าน โดยใช้ workbook สมมติ | รายงาน VM + evidence |  |

คำสั่งตรวจ artifact หลังมี signed build (อ่านอย่างเดียว):

```powershell
& '.\packaging\verify_signatures.ps1' -ArtifactPath '<signed-distribution-or-installer>' -RequireTrustedSignature
```

## F. แบบฟอร์ม Final Acceptance Evidence

| หมวด | รหัสที่ต้องผ่าน | ผู้รับผิดชอบ | สถานะรวม | หลักฐานอ้างอิง | ลายเซ็น/วันที่ |
| --- | --- | --- | --- | --- | --- |
| UI และ Tray | UI-01 ถึง UI-04, TRAY-01 | Windows tester |  |  |  |
| กฎเงินเดือน | PAY-01 ถึง PAY-06 | Payroll owner |  |  |  |
| Recovery | REC-01 ถึง REC-04 | Operator/Data owner |  |  |  |
| Trusted release | REL-01 ถึง REL-04 | Release owner/Admin |  |  |  |
| Copy-only real-data UAT | อนุมัติแยกก่อนเริ่ม | Payroll owner |  |  |  |
| Production authorization | อนุมัติแยกหลังทุกหมวดผ่าน | Authorized owner |  |  |  |

จนกว่าทุกหมวดที่เกี่ยวข้องจะผ่านพร้อมหลักฐาน: **READY FOR PRODUCTION
ACTIVATION: NO**
