"""Existing payslip labels and exact full-name identities; no layout redesign."""
from dataclasses import dataclass, replace
from decimal import Decimal
from hashlib import sha256
import re

from app.domain import ReviewIssue, encode, issue_key, normalized_name
from app.excel.formulas import arithmetic, row_values
from app.excel.payroll_reader import numeric, label, TemplateError
from app.excel.payroll_writer import CellWrite
from app.excel.workbook_source import WorkbookSnapshot
from app.excel.workbook_validator import equivalent
from app.safety import SafetyError


def income_field(text):
    value = label(text)
    if value.startswith('เงินเดือนค่าจ้าง'): return 'base'
    if value.startswith('ค่าล่วงเวลาวันหยุด') or (value.startswith('ค่าล่วงเวลา') and '3x' in value.replace(' ', '')): return 'holiday_ot_money'
    if value.startswith('ค่าล่วงเวลา'): return 'normal_money'
    if value.startswith('ค่าทำงานวันหยุด'): return 'holiday_money'
    if value.startswith('เบี้ยขยัน'): return 'bonus'
    if value.startswith('ค่าเดินทาง'): return 'travel'
    if value.startswith('เบี้ยเลี้ยง'): return 'allowance'
    if value.startswith('ค่าโทรศัพท์'): return 'phone'
    if value.startswith('ค่าตำแหน่ง'): return 'position'
    if value.startswith('คืนวันลาพักร้อน') or value.startswith('คืนพักร้อน'): return 'annual_leave_return'
    if value.startswith('โบนัส'): return 'special_bonus'
    return None


def deduction_field(text):
    value = label(text)
    if 'ภาษี' in value: return 'tax'
    if 'ประกันสังคม' in value: return 'social_security'
    if 'เงินกู้' in value: return 'loan'
    if 'เบิกล่วงหน้า' in value: return 'advance'
    if 'เครื่องมือหาย' in value: return 'tool_loss'
    if 'ที่พัก' in value or 'ค่าน้ำ' in value or 'ค่าไฟ' in value: return 'housing'
    return None


@dataclass(frozen=True)
class SlipSlot:
    side: str
    label: str
    address: str
    field: str | None
    value: Decimal | None
    formula: str | None
    label_address: str | None = None


@dataclass(frozen=True)
class Payslip:
    sheet: str
    full_name: str
    slots: tuple[SlipSlot, ...]
    totals: dict
    signature: str
    period_cell: str | None = None
    payment_date_cell: str | None = None
    literal_totals: tuple = ()


class PayslipReviewError(SafetyError):
    def __init__(self, slip, details):
        self.slip = slip
        self.details = details
        super().__init__('ต้องตรวจรูปแบบใบเงินเดือน: ' + details)


class PayslipAdapter:
    def __init__(self, slips):
        self.slips = slips

    @classmethod
    def read(cls, path):
        slips = []
        with WorkbookSnapshot.read(path).open() as (book, cached):
            for sheet in book:
                markers = [c for row in sheet for c in row if isinstance(c.value, str) and 'PAYSLIP' in c.value.upper().replace(' ', '')]
                if not markers:
                    continue
                if len(markers) != 1:
                    raise TemplateError('Payslip marker is ambiguous')
                name_labels = [c for row in sheet for c in row if isinstance(c.value, str) and 'emp.' in label(c.value)]
                if len(name_labels) != 1:
                    raise TemplateError('Payslip employee label is missing or ambiguous')
                name_label = name_labels[0]
                right = [c.value for c in sheet[name_label.row] if c.column > name_label.column and c.value is not None]
                if not right or not isinstance(right[0], str):
                    raise TemplateError('Payslip lacks a full employee identity')
                name = re.split(r'\(|เลขที่|เลขบัญชี', right[0])[0].strip()
                if len(normalized_name(name).split()) < 2:
                    raise TemplateError('Payslip identity is incomplete')
                slots = []
                for side, title, classify in [('income', 'รายได้ (Income)', income_field),
                                               ('deduction', 'รายการหัก (Deduction)', deduction_field)]:
                    headers = [c for row in sheet for c in row if label(c.value).replace(' ', '') == label(title).replace(' ', '')]
                    if len(headers) != 1:
                        raise TemplateError('Payslip section header is ambiguous')
                    header = headers[0]
                    merges = [r for r in sheet.merged_cells.ranges if r.min_row == header.row and r.min_col == header.column]
                    if len(merges) != 1 or merges[0].max_col <= header.column:
                        raise TemplateError('Payslip amount column cannot be proved from the section header')
                    value_col = merges[0].max_col
                    for row_number in range(header.row + 1, sheet.max_row + 1):
                        text = sheet.cell(row_number, header.column).value
                        if text is None:
                            continue
                        if not isinstance(text, str):
                            raise TemplateError('Payslip item label is not text')
                        if any(token in label(text) for token in ('เงินได้สะสม', 'ภาษีสะสม', 'ประกันสังคมสะสม', 'กองทุนสำรอง')):
                            break
                        cell = sheet.cell(row_number, value_col)
                        raw = cached[sheet.title][cell.coordinate].value if cell.data_type == 'f' else cell.value
                        slots.append(SlipSlot(side, text, cell.coordinate, classify(text), numeric(raw), cell.value if cell.data_type == 'f' else None,
                                              sheet.cell(row_number, header.column).coordinate))
                totals = {}
                literal_totals = []
                for field, text in [('income', 'รวมเงินได้'), ('deductions', 'รวมเงินหัก'), ('net', 'เงินได้สุทธิ')]:
                    labels = [c for row in sheet for c in row if label(c.value) == label(text)]
                    if len(labels) != 1:
                        raise TemplateError('Payslip summary header is ambiguous')
                    target_label = labels[0]
                    destinations = [c for c in sheet[target_label.row] if c.column > target_label.column and (c.data_type == 'f' or numeric(c.value) is not None)]
                    if not destinations:
                        raise TemplateError('Payslip total must have an existing numeric or formula destination')
                    # The summary is the first formula adjacent to its label.
                    # Additional calculation notes farther right are not summary
                    # values. All three summary destinations must align vertically.
                    destination = min(destinations, key=lambda c: c.column)
                    totals[field] = destination.coordinate
                    if destination.data_type != 'f':
                        literal_totals.append(field)
                from openpyxl.utils.cell import coordinate_from_string
                if len({coordinate_from_string(address)[0] for address in totals.values()}) != 1:
                    raise TemplateError('Payslip summary amount columns do not align')
                signature = sha256(encode([(s.side, re.sub(r'\(.*?\)', '', label(s.label)), s.address) for s in slots]).encode('utf-8')).hexdigest()
                metadata = {}
                for key, token in [('period_cell', 'period'), ('payment_date_cell', '(date)')]:
                    labels = [c for row in sheet for c in row if isinstance(c.value, str) and token in label(c.value)]
                    if len(labels) != 1:
                        raise TemplateError('Payslip period/payment-date label is ambiguous')
                    meta_label = labels[0]
                    right = [c for c in sheet[meta_label.row] if c.column > meta_label.column and c.value is not None]
                    if len(right) != 1 or right[0].data_type == 'f':
                        raise TemplateError('Payslip metadata must have a unique existing input cell')
                    metadata[key] = right[0].coordinate
                slips.append(Payslip(sheet.title, name, tuple(slots), totals, signature, literal_totals=tuple(literal_totals), **metadata))
        return cls(tuple(slips))

    def employee(self, full_name):
        matches = [slip for slip in self.slips if normalized_name(slip.full_name) == normalized_name(full_name)]
        if len(matches) != 1:
            raise TemplateError('Payslip full name must match exactly one existing sheet')
        return matches[0]

    def plan_employee(self, employee, payroll_person, *, mapping=None):
        slip = self.employee(employee.name)
        proposed = {key: value.final_value for key, value in employee.values.items()}
        resolver = row_values(payroll_person, proposed)
        amounts = {}
        for field, cell in payroll_person.cells.items():
            amounts[field] = resolver(cell.coordinate)
        mapping = mapping or {}
        assignments = mapping.get('assignments', {})
        overrides = mapping.get('amounts', {})
        groups, consumed = {}, set()
        for slot in slip.slots:
            fields = assignments.get(slot.address, [slot.field] if slot.field else [])
            if any(field not in payroll_person.cells for field in fields):
                if slot.address not in assignments and (slot.value in (None, 0) or slot.address in overrides):
                    fields = []
                else:
                    raise PayslipReviewError(slip, 'พบรายการที่ไม่มีในหัวตารางเงินเดือน')
            for field in fields:
                groups.setdefault(field, []).append(slot)
                consumed.add(field)
        relevant = {'base','phone','position','bonus','travel','allowance','normal_money','holiday_money','holiday_ot_money',
                    'housing','social_security','advance','loan','tax','tool_loss','special_bonus','annual_leave_return','no_leave_award','advance_return'}
        missing = [field for field in relevant & amounts.keys() if amounts[field] != 0 and field not in consumed]
        if missing:
            raise PayslipReviewError(slip, 'ไม่มีช่องปลายทางที่ยืนยันสำหรับ ' + ', '.join(sorted(missing)))
        wanted = {slot.address: Decimal(0) for slot in slip.slots}
        for field, slots in groups.items():
            value = amounts.get(field, Decimal(0))
            if len(slots) == 1:
                wanted[slots[0].address] += value
            else:
                allocations = [Decimal(str(overrides[s.address])) if s.address in overrides else s.value or Decimal(0) for s in slots]
                if not equivalent(sum(allocations), value):
                    raise PayslipReviewError(slip, 'ยอดแยกหลายช่องไม่ตรงยอดรวม ต้องยืนยันการแบ่ง ' + field)
                if any(len(assignments.get(s.address, [s.field])) > 1 for s in slots):
                    raise PayslipReviewError(slip, 'ไม่รองรับการแบ่งและรวมหลายรายการในช่องเดียวกันโดยไม่มีรายละเอียด')
                for slot, amount in zip(slots, allocations):
                    wanted[slot.address] += amount
        changes, expected = [], []
        for slot in slip.slots:
            fields = assignments.get(slot.address, [slot.field] if slot.field else [])
            fields = [field for field in fields if field in payroll_person.cells]
            if not fields and slot.value in (None, 0) and slot.address not in overrides:
                expected.append((slip.sheet, slot.address, slot.value))
                continue
            if not fields:
                if slot.value not in (None, 0) and slot.address not in overrides:
                    raise PayslipReviewError(slip, 'มีจำนวนเดิมในช่องที่ไม่ทราบความหมาย ' + slot.address)
                wanted[slot.address] = Decimal(str(overrides[slot.address])) if slot.address in overrides else slot.value or Decimal(0)
            value = wanted[slot.address]
            if slot.value is None and value == 0 and not slot.formula:
                expected.append((slip.sheet, slot.address, None))
                continue
            if slot.formula:
                if not equivalent(slot.value, value):
                    raise PayslipReviewError(slip, 'ช่องจำนวนเงินเป็นสูตร ต้องตรวจสอบโดยไม่ทับสูตร')
            elif not equivalent(slot.value, value):
                changes.append(CellWrite(slip.sheet, slot.address, value))
            expected.append((slip.sheet, slot.address, value))
            if slot.field in {'normal_money', 'holiday_money', 'holiday_ot_money'} and slot.label_address:
                pattern = r'(\(\s*)(\d+(?:\.\d+)?)(\s*x\s*)(\d*(?:\.\d+)?)(\s*\))'
                match = re.search(pattern, slot.label, re.I)
                if match:
                    quantity_field = {'normal_money':'normal_ot', 'holiday_money':'holiday_days', 'holiday_ot_money':'holiday_ot'}[slot.field]
                    factor = match[2]
                    if slot.field == 'holiday_money':
                        places = len(factor.partition('.')[2])
                        factor = format(amounts['holiday_rate'], f'.{places}f')  # Display precision of the existing caption only.
                    quantity = format(amounts[quantity_field].normalize(), 'f')
                    caption = slot.label[:match.start()] + match[1] + factor + match[3] + quantity + match[5] + slot.label[match.end():]
                    if caption != slot.label:
                        changes.append(CellWrite(slip.sheet, slot.label_address, caption))
                        expected.append((slip.sheet, slot.label_address, caption))
        # Every component and the existing summary formulas must agree with the
        # same approved payroll, including legacy combined/split rows.
        income = amounts['income']
        net = amounts['net']
        income_sum = sum((wanted[s.address] for s in slip.slots if s.side == 'income'), Decimal(0))
        deductions = sum((wanted[s.address] for s in slip.slots if s.side == 'deduction'), Decimal(0))
        if not equivalent(income_sum, income) or not equivalent(income_sum - deductions, net):
            raise PayslipReviewError(slip, 'รายการรายได้/หักในสลิปไม่ตรงรายได้สุทธิที่ยืนยัน')
        expected += [(slip.sheet, slip.totals['income'], income),
                     (slip.sheet, slip.totals['deductions'], income - net), (slip.sheet, slip.totals['net'], net)]
        for field in slip.literal_totals:
            changes.append(CellWrite(slip.sheet, slip.totals[field], {'income': income, 'deductions': income-net, 'net': net}[field]))
        return tuple(changes), tuple(expected)


def configured_mapping(repo, draft, employee, slip):
    key = issue_key('PAYSLIP_MAPPING', employee.employee_id, slip.signature)
    decision = repo.decisions(draft.source_hash).get(key)
    return decision or repo.rule('PAYSLIP_MAPPING', slip.signature, employee.employee_id)


def preflight_payslips(draft, payroll, repo):
    try:
        slips = PayslipAdapter.read(payroll.path)
    except TemplateError as exc:
        issue = ReviewIssue(issue_key('PAYSLIP_STRUCTURE', str(payroll.path)), 'PAYSLIP_STRUCTURE', None,
            None, None, None, str(exc))
        return replace(draft, global_issues=(*draft.global_issues, issue))
    updated = []
    for employee in draft.employees:
        if not employee.ready:
            updated.append(employee)
            continue
        try:
            from app.excel.payroll_writer import build_plan
            build_plan(draft, payroll, [employee.employee_id], validate_target=False)
            slip = slips.employee(employee.name)
            slips.plan_employee(employee, payroll.employee(employee.name), mapping=configured_mapping(repo, draft, employee, slip))
            updated.append(employee)
        except (PayslipReviewError, TemplateError, SafetyError) as exc:
            signature = exc.slip.signature if isinstance(exc, PayslipReviewError) else 'identity'
            issue = ReviewIssue(issue_key('PAYSLIP_MAPPING', employee.employee_id, signature), 'PAYSLIP_MAPPING', employee.employee_id,
                exc.slip.sheet if isinstance(exc, PayslipReviewError) else None, None, None, str(exc), raw_text=signature)
            updated.append(replace(employee, issues=(*employee.issues, issue)))
    return replace(draft, employees=tuple(updated))
