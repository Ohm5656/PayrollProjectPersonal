from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

from app.domain import MANUAL_FIELDS, RECURRING_FIELDS, THAI_FIELDS, ReusePolicy, decimal_value, issue_key
from app.models import DayType
from app.ui.calendar_review import DAY_LABELS
from app.ui.presentation import text as presentation_text,issue_text,raw_evidence


def money(value):
    return 'รอยืนยัน' if value is None else f'{value:,.2f}'


def thai_date(text):
    if not text:
        return ''
    day = date.fromisoformat(text)
    return f'{day.day:02}/{day.month:02}/{day.year + 543}'


class DecisionDialog(QDialog):
    def __init__(self, service, draft, issue, *, actor='user', parent=None):
        super().__init__(parent)
        self.service, self.draft, self.issue, self.actor = service, draft, issue, actor
        self.setWindowTitle('ตรวจสอบรายการ')
        self.resize(570, 430)
        layout = QVBoxLayout(self)
        summary = QLabel(f'{thai_date(issue.day)}  {issue.sheet or ""}\n{issue_text(issue)}\nข้อความต้นฉบับ: {raw_evidence(issue) or "—"}')
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.PlainText)
        layout.addWidget(summary)
        self.form = QFormLayout()
        layout.addLayout(self.form)
        self.controls = {}
        self.remember = QCheckBox('จำกฎประเภทนี้')
        self.scope = QComboBox()
        self.scope.addItem('เฉพาะพนักงานนี้', issue.employee_id)
        self.scope.addItem('ทั้งบริษัท (ใช้กับพนักงานทุกคน)', '*')
        self.remember.setChecked(False)
        self.scope.setEnabled(False)
        self.remember.toggled.connect(self.scope.setEnabled)
        if issue.kind == 'UNKNOWN_PAYROLL_EMPLOYEE':
            self.form.addRow(QLabel('ยืนยันเพิ่มพนักงานตามชื่อเต็มในไฟล์เงินเดือน: ' + issue.raw_text))
            self.remember.setEnabled(False)
        elif issue.kind == 'IDENTITY':
            combo = self.combo('employee_id', 'พนักงานที่ถูกต้อง', [(e['canonical_name'], e['id']) for e in service.repo.employees()])
            combo.insertItem(0, 'กรุณาเลือก', None)
            combo.setCurrentIndex(0)
            self.exclude = QCheckBox('ไม่ใช้ชีตนี้ในเดือนนี้ (เช่น ชีตเก่าหรือแบบฟอร์มว่าง)')
            self.form.addRow(self.exclude)
            self.exclude.toggled.connect(lambda checked: combo.setEnabled(not checked))
            self.remember.setText('จำชื่อเรียกนี้สำหรับเดือนถัดไป')
        elif issue.kind == 'LEAVE':
            self.combo('leave_type', 'ประเภทลา', [('กรุณาเลือก', None), ('ลาป่วย', 'SICK_LEAVE'),
                ('ลากิจ', 'PERSONAL_LEAVE'), ('ลาพักร้อน', 'ANNUAL_LEAVE'), ('ลาไม่รับค่าจ้าง', 'UNPAID_LEAVE'), ('อื่น ๆ', 'OTHER')])
            self.combo('bonus_effect', 'ผลต่อเบี้ยขยัน', [('กรุณาเลือก', None), ('ตัดเบี้ยขยัน', 'CUT'),
                ('ไม่ตัดเบี้ยขยัน', 'KEEP'), ('กำหนดเอง', 'CUSTOM')])
            self.line('bonus_value', 'จำนวนเบี้ยขยันเมื่อกำหนดเอง')
        elif issue.kind == 'HOLIDAY' or issue.kind.startswith('CALENDAR'):
            self.scope.setEnabled(True)
            self.combo('type', 'สถานะวัน', [(DAY_LABELS[k.value], k.value) for k in DayType if k != DayType.UNKNOWN])
            self.required = QCheckBox('เป็นวันทำงานที่บริษัทกำหนด')
            self.affects = QCheckBox('มีผลต่อเบี้ยขยัน (ต้องยืนยันผลเพิ่มเติม)')
            self.form.addRow(self.required)
            self.form.addRow(self.affects)
        elif issue.kind == 'OT':
            self.combo('category', 'ประเภท OT', [('กรุณาเลือก', None), ('OT ปกติ x1.5', 'NORMAL'), ('OT วันหยุด x3', 'HOLIDAY_OT')])
            self.line('hours', 'จำนวนชั่วโมง', issue.raw_text)
            self.remember.setText('จำกฎสำหรับสถานะวันที่ยืนยันแล้ว')
        elif issue.kind == 'HOLIDAY_WORK':
            self.line('holiday_days', 'จำนวนวันทำงานวันหยุด')
        elif issue.kind == 'FIELD':
            employee = next(e for e in draft.employees if e.employee_id == issue.employee_id)
            value = employee.values[issue.field]
            self.form.addRow('รายการ', QLabel(THAI_FIELDS.get(issue.field, issue.field)))
            self.form.addRow('ยอดจากต้นทาง', QLabel(money(value.source_value)))
            self.form.addRow('ค่าเดือนก่อน', QLabel(money(value.previous_value)))
            self.line('value', 'จำนวนที่ยืนยัน', '' if value.final_value is None else str(value.final_value))
            self.use_previous = QCheckBox('ใช้ค่าเดิม')
            self.use_previous.setChecked(False)  # One-time deductions are never pre-checked.
            self.use_previous.setEnabled(value.previous_value is not None)
            self.use_previous.toggled.connect(lambda checked: self.controls['value'].setText(str(value.previous_value)) if checked else None)
            self.form.addRow(self.use_previous)
            self.remember.setText('บันทึกนโยบายใช้ค่านี้ในเดือนถัดไป')
            self.policy = QComboBox()
            for policy, text in [(ReusePolicy.ALWAYS_SUGGEST, 'เสนอให้ตรวจทุกเดือน'),
                                 (ReusePolicy.AUTO_REUSE, 'ใช้ค่าประจำเดิม'),
                                 (ReusePolicy.NEVER_REUSE, 'ไม่ใช้ค่าเดิมอัตโนมัติ'), (ReusePolicy.ONE_TIME, 'รายการครั้งเดียว')]:
                self.policy.addItem(text, policy.value)
            if issue.field not in RECURRING_FIELDS:
                self.policy.setCurrentIndex(2)
                self.policy.setEnabled(False)
            self.form.addRow('นโยบาย', self.policy)
        else:
            self.form.addRow(QLabel('การรับทราบคำเตือนไม่เปลี่ยนจำนวนเงิน ต้องแก้จำนวนเงินในรายการนั้นแยกต่างหาก'))
        can_remember = issue.kind in {'LEAVE', 'HOLIDAY', 'OT', 'FIELD'} or (issue.kind == 'IDENTITY' and issue.employee_id is None)
        if can_remember:
            layout.addWidget(self.remember)
            if issue.kind not in {'IDENTITY', 'FIELD'}:
                self.form.addRow('ขอบเขตของกฎ', self.scope)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText('เหตุผล/หลักฐานที่ใช้ยืนยัน')
        self.form.addRow('เหตุผล', self.reason)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('บันทึกการตัดสินใจ')
        buttons.button(QDialogButtonBox.Cancel).setText('ยกเลิก')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def combo(self, key, title, items):
        widget = QComboBox()
        for text, value in items:
            widget.addItem(text, value)
        self.controls[key] = widget
        self.form.addRow(title, widget)
        return widget

    def line(self, key, title, text=''):
        widget = QLineEdit(text)
        self.controls[key] = widget
        self.form.addRow(title, widget)
        return widget

    def save(self):
        try:
            self.persist()
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'ยังบันทึกไม่ได้', str(exc))
            return
        self.accept()

    def persist(self):
        with self.service.repo.db.transaction():
            self._persist()

    def _persist(self):
        repo, issue = self.service.repo, self.issue
        if not self.reason.text().strip():
            raise ValueError('กรุณาระบุเหตุผล')
        values = {k: w.currentData() if isinstance(w, QComboBox) else w.text().strip() for k, w in self.controls.items()}
        decision = dict(values)
        if issue.kind == 'UNKNOWN_PAYROLL_EMPLOYEE':
            repo.create_employee(issue.raw_text, actor=self.actor)
            decision = {'roster_confirmed': True}
        elif issue.kind == 'IDENTITY':
            decision = {'exclude': True} if self.exclude.isChecked() else {'employee_id': values['employee_id']}
            if not decision.get('exclude') and not decision.get('employee_id'):
                raise ValueError('กรุณาเลือกพนักงาน')
            if self.remember.isChecked() and not decision.get('exclude'):
                repo.confirm_alias(decision['employee_id'], issue.raw_text, 'attendance_full', actor=self.actor, reason=self.reason.text())
        elif issue.kind == 'LEAVE':
            if not values['leave_type'] or not values['bonus_effect']:
                raise ValueError('ต้องระบุประเภทลาและผลต่อเบี้ยขยัน')
            if values['bonus_effect'] == 'CUSTOM':
                if decimal_value(values['bonus_value']) is None:
                    raise ValueError('ต้องระบุจำนวนเบี้ยขยัน')
            else:
                decision.pop('bonus_value', None)
        elif issue.kind == 'HOLIDAY' or issue.kind.startswith('CALENDAR'):
            scope = self.scope.currentData() or issue.employee_id or '*'
            repo.confirm_calendar(issue.day, values['type'], issue.raw_text or self.reason.text(),
                required_workday=self.required.isChecked(), affects_attendance_bonus=self.affects.isChecked(),
                scope=scope, actor=self.actor)
            decision = {'type': values['type'], 'required_workday': self.required.isChecked(),
                        'affects_attendance_bonus': self.affects.isChecked()}
        elif issue.kind in {'FIELD', 'OT', 'HOLIDAY_WORK'}:
            numeric_key = {'FIELD': 'value', 'OT': 'hours', 'HOLIDAY_WORK': 'holiday_days'}[issue.kind]
            if decimal_value(values[numeric_key]) is None:
                raise ValueError('ต้องระบุจำนวน')
            if issue.kind in {'OT','HOLIDAY_WORK'} and decimal_value(values[numeric_key]) < 0:
                raise ValueError('จำนวนชั่วโมงหรือวันต้องไม่ติดลบ')
            if issue.kind == 'OT' and not values['category']:
                raise ValueError('ต้องระบุประเภท OT')
        else:
            if issue.critical and issue.kind.startswith('SOURCE_'):
                raise ValueError('ต้องแก้ไขข้อมูลในไฟล์สำเนาแล้วอ่านใหม่ ไม่สามารถข้ามข้อผิดพลาดนี้ได้')
            decision = {'acknowledged': True}
        repo.decide(self.draft.source_hash, issue.key, decision, reason=self.reason.text(), actor=self.actor)
        if self.remember.isChecked():
            if issue.kind in {'LEAVE', 'HOLIDAY'}:
                repo.remember_rule(issue.kind, issue.raw_text, decision, scope=self.scope.currentData() or issue.employee_id or '*', actor=self.actor)
            elif issue.kind == 'FIELD':
                repo.remember_value(issue.employee_id, issue.field, values['value'],
                    f'{self.draft.year:04}-{self.draft.month:02}-01', self.policy.currentData(), actor=self.actor)
            elif issue.kind == 'OT':
                calendar = repo.calendar(issue.employee_id, issue.day)
                if not calendar:
                    raise ValueError('ต้องยืนยันสถานะวันก่อนจึงจะจำกฎ OT ได้')
                repo.remember_rule('OT_BY_DAY_TYPE', calendar['type'], {'category': values['category']},
                    scope=self.scope.currentData() or issue.employee_id, actor=self.actor)


class ReviewCenter(QDialog):
    def __init__(self, service, draft, *, actor='user', employee_id=None, on_changed=None, parent=None):
        super().__init__(parent)
        self.service, self.draft, self.actor, self.on_changed = service, draft, actor, on_changed
        self.setWindowTitle('รายการที่ต้องตรวจสอบ')
        self.resize(950, 590)
        layout = QVBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(['พนักงาน / วันที่', 'รายการ', 'ข้อความต้นฉบับ', 'ความสำคัญ'])
        names = {e.employee_id: e.name for e in draft.employees if e.employee_id}
        groups = {}
        for issue in draft.issues:
            if employee_id is not None and issue.employee_id != employee_id:
                continue
            group_key = issue.employee_id or issue.sheet or 'ข้อมูลส่วนกลาง'
            if group_key not in groups:
                group = QTreeWidgetItem([names.get(issue.employee_id, issue.sheet or 'ข้อมูลส่วนกลาง')])
                self.tree.addTopLevelItem(group)
                groups[group_key] = group
            item = QTreeWidgetItem([thai_date(issue.day), issue_text(issue), raw_evidence(issue), 'ต้องยืนยัน' if issue.critical else 'คำเตือน'])
            item.setData(0, Qt.UserRole, issue)
            groups[group_key].addChild(item)
        self.tree.expandAll()
        self.tree.setColumnWidth(0, 220)
        self.tree.setColumnWidth(1, 320)
        self.tree.itemDoubleClicked.connect(self.edit_item)
        layout.addWidget(self.tree)
        button = QPushButton('ตรวจสอบรายการที่เลือก')
        button.clicked.connect(lambda: self.edit_item(self.tree.currentItem()))
        layout.addWidget(button)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)

    def edit_item(self, item, column=0):
        if not item:
            return
        issue = item.data(0, Qt.UserRole)
        if not issue:
            return
        if issue.kind == 'PAYSLIP_MAPPING':
            dialog = PayslipMappingDialog(self.service, self.draft, issue, actor=self.actor, parent=self)
        else:
            dialog = DecisionDialog(self.service, self.draft, issue, actor=self.actor, parent=self)
        if dialog.exec() == QDialog.Accepted:
            if self.on_changed:
                self.on_changed()
            self.accept()


class EmployeeReview(QDialog):
    def __init__(self, service, draft, employee, *, actor='user', on_changed=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('ตรวจสอบเงินเดือน — ' + employee.name)
        self.resize(1050, 520)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('ค่าจากเดือนก่อนและฉบับร่าง — ดับเบิลคลิกรายการเพื่อยืนยันหรือแก้ไข'))
        self.table = QTableWidget(len(employee.values), 7)
        self.table.setHorizontalHeaderLabels(['รายการ', 'ต้นทาง', 'เดือนก่อน', 'ฉบับร่าง', 'ผู้ใช้แก้ไข', 'จำนวนสุดท้าย', 'เหตุผล'])
        self.fields = list(employee.values)
        for row, field in enumerate(self.fields):
            value = employee.values[field]
            for col, text in enumerate([THAI_FIELDS.get(field, field), money(value.source_value), money(value.previous_value),
                money(value.draft_value), money(value.user_override), money(value.final_value), presentation_text(value.reason)]):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, item)
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        def edit(row, column):
            from app.domain import ReviewIssue
            field = self.fields[row]
            issue = ReviewIssue(issue_key('FIELD', employee.employee_id, field), 'FIELD', employee.employee_id,
                employee.sheet, None, None, 'ยืนยันหรือแก้ไขจำนวน', field=field)
            if DecisionDialog(service, draft, issue, actor=actor, parent=self).exec() == QDialog.Accepted:
                if on_changed:
                    on_changed()
                self.accept()
        self.table.cellDoubleClicked.connect(edit)
        zero_button = QPushButton('ตรวจและยืนยันรายการพิเศษที่ไม่มีเงินเดือนนี้')
        def confirm_zeros():
            dialog = ZeroManualReview(service,draft,employee,actor=actor,parent=self)
            if dialog.exec() == QDialog.Accepted:
                if on_changed: on_changed()
                self.accept()
        zero_button.clicked.connect(confirm_zeros)
        layout.addWidget(zero_button)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.reject)
        layout.addWidget(close)


class ZeroManualReview(QDialog):
    """Explicit checked monthly zeros; never auto-copy previous deductions."""
    def __init__(self,service,draft,employee,*,actor='user',parent=None):
        super().__init__(parent)
        self.service,self.draft,self.employee,self.actor=service,draft,employee,actor
        self.setWindowTitle('ยืนยันไม่มีรายการพิเศษ — '+employee.name)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('เลือกรายการที่ตรวจแล้วว่าไม่มีเงินเดือนนี้ การยืนยันนี้ใช้เฉพาะข้อมูลรอบนี้'))
        self.checks={}
        for field,value in employee.values.items():
            if field in MANUAL_FIELDS and value.source_value in (None,0) and value.final_value is None:
                check=QCheckBox(THAI_FIELDS.get(field,field)+' | เดือนก่อน: '+money(value.previous_value))
                self.checks[field]=check
                layout.addWidget(check)
        select=QPushButton('เลือกทุกรายการที่แสดง')
        select.clicked.connect(lambda:[c.setChecked(True) for c in self.checks.values()])
        layout.addWidget(select)
        self.reason=QLineEdit()
        self.reason.setPlaceholderText('เหตุผลที่ยืนยันจำนวนศูนย์')
        layout.addWidget(self.reason)
        buttons=QDialogButtonBox(QDialogButtonBox.Save|QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def persist(self):
        fields=[f for f,c in self.checks.items() if c.isChecked()]
        if not fields or not self.reason.text().strip(): raise ValueError('เลือกรายการและระบุเหตุผลก่อนยืนยัน')
        with self.service.repo.db.transaction():
            for field in fields:
                self.service.repo.decide(self.draft.source_hash,issue_key('FIELD',self.employee.employee_id,field),
                    {'value':'0'},reason=self.reason.text(),actor=self.actor)

    def save(self):
        try:self.persist()
        except ValueError as exc:
            QMessageBox.warning(self,'ยังบันทึกไม่ได้',str(exc))
            return
        self.accept()


class PayslipMappingDialog(QDialog):
    def __init__(self, service, draft, issue, *, actor='user', parent=None):
        super().__init__(parent)
        from app.excel.payslip_adapter import PayslipAdapter, configured_mapping
        from app.excel.payroll_reader import PayrollWorkbookAdapter
        self.service, self.draft, self.issue, self.actor = service, draft, issue, actor
        self.employee = next(e for e in draft.employees if e.employee_id == issue.employee_id)
        payroll = PayrollWorkbookAdapter.read(draft.payroll_path)
        self.person = payroll.employee(self.employee.name)
        self.adapter = PayslipAdapter.read(draft.payroll_path)
        self.slip = self.adapter.employee(self.employee.name)
        configured = configured_mapping(service.repo, draft, self.employee, self.slip) or {}
        self.setWindowTitle('ตรวจสอบช่องใบเงินเดือน — ' + self.employee.name)
        self.resize(1000, 660)
        layout = QVBoxLayout(self)
        message = QLabel(issue.message + '\nยืนยันความหมายของช่องเดิมจากรูปแบบบริษัท หากมีหลายช่องให้ระบุการแบ่งยอด ช่องรวมหลายรายการต้องได้รับการยืนยันโดยผู้ตรวจสอบ')
        message.setWordWrap(True)
        layout.addWidget(message)
        self.table = QTableWidget(len(self.slip.slots), 5)
        self.table.setHorizontalHeaderLabels(['ชื่อช่องเดิม', 'ยอดเดิม', 'รายการที่ช่องนี้ใช้', 'รายการเพิ่มเติมที่รวมในช่องเดียวกัน', 'จำนวนเมื่อแบ่งหลายช่อง/แก้กรณีพิเศษ'])
        self.controls = []
        for row, slot in enumerate(self.slip.slots):
            self.table.setItem(row, 0, QTableWidgetItem(slot.label))
            self.table.setItem(row, 1, QTableWidgetItem(money(slot.value)))
            fields = configured.get('assignments', {}).get(slot.address, [slot.field] if slot.field in self.person.cells else [])
            combos = []
            for column in (2, 3):
                combo = QComboBox()
                combo.addItem('ไม่มีรายการ / คงช่องเดิม', None)
                for field in self.person.cells:
                    if field in THAI_FIELDS and field not in ('normal_ot', 'holiday_ot', 'holiday_days', 'income', 'net'):
                        combo.addItem(THAI_FIELDS[field], field)
                index = column - 2
                if index < len(fields):
                    combo.setCurrentIndex(max(0, combo.findData(fields[index])))
                self.table.setCellWidget(row, column, combo)
                combos.append(combo)
            amount = QLineEdit(str(configured.get('amounts', {}).get(slot.address, '')))
            self.table.setCellWidget(row, 4, amount)
            self.controls.append((slot, combos, amount))
        self.table.resizeColumnsToContents()
        layout.addWidget(self.table)
        self.remember = QCheckBox('จำการจับคู่ช่องสำหรับรูปแบบสลิปนี้และพนักงานนี้ (ไม่จำยอดรายครั้ง)')
        layout.addWidget(self.remember)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText('เหตุผล/ผู้ยืนยันความหมายของช่อง')
        layout.addWidget(self.reason)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def persist(self):
        if not self.reason.text().strip():
            raise ValueError('ต้องระบุเหตุผลยืนยันช่องสลิป')
        mapping = {'assignments': {}, 'amounts': {}}
        for slot, combos, amount in self.controls:
            mapping['assignments'][slot.address] = [c.currentData() for c in combos if c.currentData()]
            if amount.text().strip():
                mapping['amounts'][slot.address] = str(decimal_value(amount.text()))
        self.adapter.plan_employee(self.employee, self.person, mapping=mapping)
        with self.service.repo.db.transaction():
            self.service.repo.decide(self.draft.source_hash, self.issue.key, mapping, reason=self.reason.text(), actor=self.actor)
            if self.remember.isChecked():
                self.service.repo.remember_rule('PAYSLIP_MAPPING', self.slip.signature,
                    {'assignments': mapping['assignments']}, scope=self.employee.employee_id, actor=self.actor)

    def save(self):
        try:
            self.persist()
        except (ValueError, RuntimeError) as exc:
            QMessageBox.warning(self, 'ยังยืนยันไม่ได้', str(exc))
            return
        self.accept()
