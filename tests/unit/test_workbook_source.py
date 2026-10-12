from pathlib import Path

import pytest

from app.excel.workbook_source import WorkbookReadError, WorkbookSnapshot, discover_workbooks, safe_output_path


def test_excel_temporary_files_ignored(workbook_workspace):
    (workbook_workspace / '~$attendance.xlsx').write_bytes(b'temporary')
    (workbook_workspace / 'UPPER.XLSX').write_bytes(b'inventory only')
    assert [p.name for p in discover_workbooks(workbook_workspace)] == ['UPPER.XLSX']


def test_invalid_package_fails_without_excel(workbook_workspace):
    path = workbook_workspace / 'corrupt.xlsx'
    path.write_bytes(b'not a ZIP package')
    with pytest.raises(WorkbookReadError, match='Invalid XLSX'):
        with WorkbookSnapshot.read(path).open():
            pytest.fail('Corrupt package was opened')


def test_locked_read_is_reported_without_retries_or_excel(copied_reference, monkeypatch):
    path = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    def denied(_):
        raise PermissionError('simulated sharing violation')
    monkeypatch.setattr(Path, 'read_bytes', denied)
    with pytest.raises(WorkbookReadError, match='safely read'):
        WorkbookSnapshot.read(path)


def test_changed_file_is_not_a_stable_snapshot(copied_reference, monkeypatch):
    from types import SimpleNamespace
    path = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    original = Path.stat
    reads = 0
    # Snapshot resolves once; avoid recursively resolving in the patched stat.
    resolved = path.resolve()
    def stable_patch(self, *args, **kwargs):
        nonlocal reads
        actual = original(self, *args, **kwargs)
        if self == resolved:
            reads += 1
            return SimpleNamespace(st_mtime_ns=reads, st_size=actual.st_size)
        return actual
    monkeypatch.setattr(Path, 'stat', stable_patch)
    with pytest.raises(WorkbookReadError, match='changed during reading'):
        WorkbookSnapshot.read(path)


def test_path_traversal_cannot_write_reference(copied_reference):
    target = copied_reference / 'attendance' / '..' / 'report.json'
    with pytest.raises(ValueError, match='read-only'):
        safe_output_path(target, copied_reference)


def test_actual_windows_sharing_lock_is_respected(copied_reference):
    import ctypes
    from ctypes import wintypes
    import os
    if os.name != 'nt':
        pytest.skip('Windows sharing-mode test requires Windows')
    path = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
    assert handle != wintypes.HANDLE(-1).value, f'Cannot create test sharing lock: {ctypes.get_last_error()}'
    try:
        with pytest.raises(WorkbookReadError, match='safely read'):
            WorkbookSnapshot.read(path)
    finally:
        assert kernel.CloseHandle(handle)
