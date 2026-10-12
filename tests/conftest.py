"""All workbook tests use isolated copies beneath test_workspace."""
from pathlib import Path
import shutil
import tempfile

import pytest

from app.excel.workbook_source import discover_workbooks, file_hash, filename_month

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / 'reference_data'
WORKSPACE = ROOT / 'test_workspace'


@pytest.fixture(scope='session', autouse=True)
def protect_references():
    before = {p.relative_to(REFERENCE).as_posix(): (file_hash(p), p.stat().st_mtime_ns)
              for p in discover_workbooks(REFERENCE)}
    yield
    after = {p.relative_to(REFERENCE).as_posix(): (file_hash(p), p.stat().st_mtime_ns)
             for p in discover_workbooks(REFERENCE)}
    assert before == after, 'Source workbook content, inventory or modification time changed'


@pytest.fixture(scope='session')
def copied_reference(protect_references):
    WORKSPACE.mkdir(exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix='regression_', dir=WORKSPACE)).resolve()
    assert WORKSPACE.resolve() in destination.parents
    for path in discover_workbooks(REFERENCE):
        target = destination / path.relative_to(REFERENCE)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        assert file_hash(target) == file_hash(path)
    return destination


@pytest.fixture
def workbook_workspace():
    WORKSPACE.mkdir(exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix='case_', dir=WORKSPACE)).resolve()
    assert WORKSPACE.resolve() in destination.parents
    return destination


@pytest.fixture(scope='session')
def historical_data(copied_reference):
    from app.analysis.historical import inspect_all
    return inspect_all(copied_reference)


@pytest.fixture
def edit_attendance_copy(copied_reference, workbook_workspace):
    """Copy first; every mutation/save is guarded inside test_workspace."""
    from openpyxl import load_workbook
    source = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    target = workbook_workspace / source.name
    shutil.copy2(source, target)
    def edit(change):
        assert WORKSPACE.resolve() in target.resolve().parents
        assert REFERENCE.resolve() not in target.resolve().parents
        book = load_workbook(target)
        try:
            change(book['ดนุกานต์'])
            book.save(target)
        finally:
            book.close()
        return target
    return edit


@pytest.fixture(scope='session')
def parsed_history(copied_reference):
    from app.excel.attendance_reader import read_attendance
    return {filename_month(p): read_attendance(p) for p in discover_workbooks(copied_reference / 'attendance')}
