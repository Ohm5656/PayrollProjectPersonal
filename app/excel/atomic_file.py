"""Replace a validated copy while our destination reservation remains held."""
from pathlib import Path
import os

from app.safety import SafetyError, development_target


def atomic_replace(source: Path, destination: Path):
    source, destination = development_target(source), development_target(destination)
    if os.name != 'nt':
        os.replace(source, destination)
        return
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    class RenameInfo(ctypes.Structure):
        _fields_ = [('Flags', wintypes.DWORD), ('RootDirectory', wintypes.HANDLE),
                    ('FileNameLength', wintypes.DWORD), ('FileName', wintypes.WCHAR * 1)]
    name = str(destination).encode('utf-16-le')
    offset = RenameInfo.FileName.offset
    # SetFileInformationByHandle's DOS-path conversion can read a trailing
    # WCHAR despite FileNameLength. Reserve an explicit zero terminator so a
    # non-ASCII name cannot gain memory bytes as an extra filename character.
    size = max(ctypes.sizeof(RenameInfo), offset + len(name) + ctypes.sizeof(wintypes.WCHAR))
    buffer = ctypes.create_string_buffer(size)
    info = ctypes.cast(buffer, ctypes.POINTER(RenameInfo)).contents
    info.Flags = 0x1 | 0x2  # REPLACE_IF_EXISTS | POSIX_SEMANTICS (Windows 10+).
    info.RootDirectory = None
    info.FileNameLength = len(name)
    ctypes.memmove(ctypes.addressof(buffer) + offset, name, len(name))
    handle = kernel.CreateFileW(str(source), 0x10000 | 0x100000, 0x1 | 0x2 | 0x4, None, 3, 0x80, None)
    if handle == wintypes.HANDLE(-1).value:
        raise SafetyError(f'Cannot reserve staged file for replacement: {ctypes.get_last_error()}')
    try:
        if not kernel.SetFileInformationByHandle(handle, 22, buffer, size):
            raise SafetyError(f'Atomic copy replacement failed safely: {ctypes.get_last_error()}')
    finally:
        kernel.CloseHandle(handle)
