from app.excel.package_values import CELL
from app.excel.package_values import preserve_package_values
from app.excel.payroll_writer import CellWrite
from app.safety import SafetyError
from zipfile import ZipFile
from io import BytesIO
import pytest


def test_self_closing_cells_do_not_consume_next_cell():
    text = '<c r="A1" s="1"/><c r="B1" s="2"><v>5</v></c><c r="C1" s="2"/>'
    assert [m.group(0) for m in CELL.finditer(text)] == [
        '<c r="A1" s="1"/>', '<c r="B1" s="2"><v>5</v></c>', '<c r="C1" s="2"/>']


def package(sheet):
    content=BytesIO()
    with ZipFile(content,'w') as book:
        book.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="test" sheetId="1" r:id="rId1"/></sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        book.writestr('xl/worksheets/sheet1.xml',sheet)
        book.writestr('xl/styles.xml',b'unchanged original styles')
    return content.getvalue()


def test_approved_value_can_fill_absent_blank_input_without_regenerating_layout(workbook_workspace):
    start='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:C1"/><sheetData><row r="1" ht="20"><c r="A1" s="4"><v>1</v></c><c r="C1" s="4"><v>3</v></c></row></sheetData></worksheet>'
    original=package(start)
    saved=workbook_workspace/'calculated.xlsx'
    saved.write_bytes(package(start.replace('<c r="C1"','<c r="B1"><v>7</v></c><c r="C1"')))
    preserve_package_values(original,saved,[CellWrite('test','B1',7)])
    with ZipFile(saved) as result:
        assert result.read('xl/worksheets/sheet1.xml').decode()==start.replace('<c r="C1"','<c r="B1"><v>7</v></c><c r="C1"')
        assert result.read('xl/styles.xml')==b'unchanged original styles'


def test_absent_input_outside_template_bounds_is_rejected(workbook_workspace):
    sheet='<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:C1"/><sheetData><row r="1"><c r="A1"><v>1</v></c></row></sheetData></worksheet>'
    original=package(sheet)
    saved=workbook_workspace/'calculated.xlsx'
    saved.write_bytes(package(sheet.replace('</row>','<c r="Z1"><v>7</v></c></row>')))
    with pytest.raises(SafetyError,match='bounds'):
        preserve_package_values(original,saved,[CellWrite('test','Z1',7)])
