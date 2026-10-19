# คู่มือการรับรอง Test Candidate

## ก่อนเริ่ม

ใช้เฉพาะไฟล์ทดสอบและข้อมูลพนักงานสมมติ ห้ามคัดลอกสมุดงานเงินเดือนจริง
มาทดสอบ และห้ามเปิดใช้งาน Monitoring, ยืนยันเงินเดือน, เขียน Excel,
ล็อกรอบ หรือ Windows startup. ปิด candidate จาก Tray > Exit ก่อนลบไฟล์
ทดสอบใด ๆ.

## เปิดและยืนยันโหมดทดสอบ

หลัง build ให้เปิด `NTP Payroll Assistant - Test Candidate.exe` จากโฟลเดอร์
`dist` โปรแกรมต้องแสดงคำว่า QA/โหมดทดสอบ และมีข้อมูลสมมติเท่านั้น. หากไม่
เห็นสถานะดังกล่าว ให้หยุดทดสอบและแจ้งผู้พัฒนา ไม่ต้องลองเปิดไฟล์เงินจริง.

## ตรวจหน้าจอและ Tray

1. เปิด Overview, Review, History, Problems และ Settings ตรวจภาษาไทย การเลื่อน และข้อความไม่ถูกตัด
2. เปลี่ยนเดือนกันยายน ตุลาคม และเดือนที่ไม่มี draft; ตารางพนักงานและสถานะต้องเปลี่ยนตาม โดยไม่มีการคำนวณหรือเขียนไฟล์
3. เปิด Employee/History/Job detail แล้วปิด ตรวจว่าไม่ได้เปลี่ยนรอบเงินเดือนโดยอัตโนมัติ
4. ใช้ Tab, Shift+Tab, Enter, Space และปุ่มลูกศร ตรวจ focus order และ keyboard navigation
5. กด X เพื่อตรวจ hide-to-Tray, Restore จาก tray menu และ Exit; ห้ามพบการเริ่ม Monitoring หรือ Task Scheduler
6. ปรับขนาดหน้าต่างและ Windows DPI ที่ใช้งานจริง ตรวจข้อความไทยและตาราง

## ตรวจ installer อย่างปลอดภัย

เมื่อมี Inno Setup build สำเร็จแล้วเท่านั้น ให้ตรวจ metadata และ shortcut
ใน Windows disposable account/VM. ห้ามติดตั้งทับ application จริง. ตรวจว่า
installer ไม่เปิดโปรแกรม ไม่สร้าง Scheduled Task และ uninstall ไม่ลบฐานข้อมูล
หรือหลักฐาน backup โดยอัตโนมัติ.

## Excel และผลเงินเดือน

Excel COM ต้องใช้ Microsoft Excel Desktop และ workbook สมมติที่สร้างใหม่
เท่านั้น. ตรวจยอดตัวอย่างกับกติกาที่เจ้าของธุรกิจอนุมัติ, ตรวจ backup ก่อน
การเขียน, และตรวจว่า restore ไปยังปลายทางใหม่เท่านั้น. หากยอดไม่ตรงหรือมี
ข้อสงสัย ให้หยุดโปรแกรมจาก Tray > Exit, เก็บ log ใน candidate sandbox และ
แจ้ง issue พร้อมขั้นตอนทำซ้ำ; ห้ามยืนยันหรือแก้ไฟล์เงินจริงด้วยโปรแกรม.
