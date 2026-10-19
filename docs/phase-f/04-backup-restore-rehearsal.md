# Backup and Restore Rehearsal

Restore is allowed only from a hash-verified backup into a fresh isolated
destination. Existing targets, missing/corrupt evidence and ambiguous staging
must stop for user review. SQLite rehearsal uses SQLite's backup API then a
read-only integrity check; it never copies an active database over itself.

Thai operator checklist: ตรวจ hash ของ backup → เลือกปลายทางใหม่ในพื้นที่ทดสอบ
→ เปิดสำเนาที่กู้คืนเพื่อตรวจ → หยุดหาก hash ไม่ตรงหรือมีหลายตัวเลือก → ขออนุมัติ
ก่อนการกู้คืนใด ๆ นอกพื้นที่ทดสอบ.
