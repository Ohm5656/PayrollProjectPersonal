import pytest
from app.excel.atomic_file import atomic_replace
from app.excel.excel_gateway import reserved_copy


@pytest.mark.parametrize('name',['เดือน 8.xlsx','เงินเดือนพนักงาน สิงหาคม.xlsx','copy.xlsx','รายได้สุทธิ งวดที่ ๘.xlsx'])
def test_exact_unicode_destination_while_reserved(workbook_workspace,name):
    target = workbook_workspace/name
    target.write_bytes(b'original saved copy')
    source = workbook_workspace/'staged.xlsx'
    source.write_bytes(b'validated replacement')
    with reserved_copy(target):
        atomic_replace(source,target)
    assert target.read_bytes() == b'validated replacement'
    assert list(workbook_workspace.iterdir()) == [target]
