"""Isolated Excel ownership. Never attaches to an existing Excel application."""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import gc
import os
import json
import logging
import threading
from datetime import datetime,timezone
from app.safety import TEST_ROOT

# Process IDs can be reused, so an owned identity always contains both values.
# A just-quit instance may remain in the system snapshot for a moment.  Do not
# mistake that known test-owned instance for a user's pre-existing Excel.
OWNED_EXCEL_IDENTITIES=set()


def release_metadata(proxy):
    """Release dynamic ITypeInfo/ITypeComp while the owned server is alive.

    Clearing _oleobj_ alone leaves CDispatch._lazydata_ alive in caller-held
    Workbook wrappers. Those interfaces otherwise release after Excel.Quit.
    """
    state=proxy.__dict__
    for child in list(state.get('_mapCachedItems_',{}).values()):
        release_metadata(child)
        child.__dict__['_oleobj_']=None
    state['_mapCachedItems_']={}
    state['_lazydata_']=None
    state['_enum_']=None

from app.safety import SafetyError, development_target


class ExcelUnavailable(RuntimeError):
    pass


class FileInUse(SafetyError):
    def __init__(self):
        super().__init__('กรุณาบันทึกการแก้ไขในไฟล์เงินเดือนก่อน และปิดไฟล์สำเนาที่ต้องการให้โปรแกรมบันทึก')


def excel_processes():
    """Read process IDs + creation times; never queries a user's COM workbooks."""
    if os.name != 'nt':
        raise ExcelUnavailable('Windows Excel integration requires Windows')
    import ctypes
    from ctypes import wintypes
    class ProcessEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
            ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
            ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.FILETIME),
        ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME)]
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == wintypes.HANDLE(-1).value:
        raise ExcelUnavailable('Cannot safely record existing Excel processes')
    found = {}
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.szExeFile.casefold() == 'excel.exe':
                handle = kernel.OpenProcess(0x1000, False, entry.th32ProcessID)
                if not handle:
                    raise ExcelUnavailable('Cannot verify an existing Excel process identity')
                try:
                    creation, exit_time, user, system = (wintypes.FILETIME() for _ in range(4))
                    if not kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(user), ctypes.byref(system)):
                        raise ExcelUnavailable('Cannot verify Excel creation time')
                    found[int(entry.th32ProcessID)] = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
                finally:
                    kernel.CloseHandle(handle)
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(snapshot)
    return found


def verify_existing_excel(before):
    after = excel_processes()
    if any(after.get(pid) != created for pid, created in before.items()):
        raise SafetyError('A pre-existing Excel process disappeared or changed; stop integration testing')
    return after


@contextmanager
def reserved_copy(path):
    """Deny other readers/writers while allowing atomic replacement of our copy."""
    path = development_target(path)
    if path.with_name('~$' + path.name).exists():
        raise FileInUse()
    try:
        import win32con
        import win32file
        handle = win32file.CreateFile(str(path), win32con.GENERIC_READ | win32con.GENERIC_WRITE,
            win32con.FILE_SHARE_DELETE, None, win32con.OPEN_EXISTING, win32con.FILE_ATTRIBUTE_NORMAL, None)
    except ImportError as exc:
        raise ExcelUnavailable('pywin32 is not installed') from exc
    except Exception as exc:
        raise FileInUse() from exc
    try:
        size = win32file.GetFileSize(handle)
        chunks = []
        remaining = size
        while remaining:
            _, content = win32file.ReadFile(handle, min(remaining, 1024 * 1024))
            if not content:
                raise SafetyError('Could not read the reserved workbook completely')
            chunks.append(content)
            remaining -= len(content)
        yield b''.join(chunks)
    finally:
        handle.Close()


class ExcelGateway:
    def __init__(self, *, lifecycle_root=None):
        self.app = None
        self.pid = None
        self.pre_existing = {}
        self.books = []
        self._initialized = False
        self.isolated = False
        self.version = None
        self._ole32 = None
        self._process_handle=None
        self.creation_time=None
        self.process_exit_code=None
        self.events=[]
        self.thread_id=None
        self.lifecycle_root = Path(lifecycle_root) if lifecycle_root is not None else TEST_ROOT / 'com_lifecycle'

    def record(self,event,**details):
        entry={'event':event,'pid':self.pid,'creation_time':self.creation_time,'thread_id':threading.get_ident(),
               'timestamp':datetime.now(timezone.utc).isoformat(),**details}
        self.events.append(entry)
        path=development_target(self.lifecycle_root/'events.jsonl')
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('a',encoding='utf-8') as stream:stream.write(json.dumps(entry,ensure_ascii=False)+'\n')
        logging.getLogger('ntp').info('Owned Excel lifecycle %s pid=%s',event,self.pid)

    def __enter__(self):
        import pythoncom
        import win32com.client
        import win32process
        snapshot=excel_processes()
        self.pre_existing={pid:created for pid,created in snapshot.items()
                           if (pid,created) not in OWNED_EXCEL_IDENTITIES}
        # Balance exactly our own apartment initialization. pythoncom may have
        # auto-initialized the importing thread; its main-thread helper can skip
        # a nested initialization and then tear down somebody else's apartment.
        import ctypes
        self._ole32 = ctypes.OleDLL('ole32')
        self._ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        self._ole32.CoInitializeEx.restype = ctypes.c_long
        self._ole32.CoUninitialize.argtypes = []
        self._ole32.CoUninitialize.restype = None
        status = self._ole32.CoInitializeEx(None, 2)
        if status not in (0, 1):
            raise ExcelUnavailable('Cannot initialize an isolated Excel STA apartment')
        self._initialized = True
        self.thread_id=threading.get_ident()
        try:
            app = win32com.client.DispatchEx('Excel.Application')
            self.app = app
            self.pid = int(win32process.GetWindowThreadProcessId(int(app.Hwnd))[1])
            if not self.pid or self.pid in self.pre_existing:
                # Do not set properties, enumerate workbooks, close or Quit here.
                self.app = None
                raise SafetyError('DispatchEx did not produce a separate Excel process; aborted without manipulating it')
            self.isolated = True
            if int(app.Workbooks.Count) != 0:
                self.isolated = False  # Never close an automatically opened, unowned workbook.
                self.app = None
                raise SafetyError('Isolated Excel started with an unowned workbook; no writes allowed')
            import win32api
            self._process_handle=win32api.OpenProcess(0x1000|0x100000,False,self.pid)
            self.creation_time=excel_processes()[self.pid]
            OWNED_EXCEL_IDENTITIES.add((self.pid,self.creation_time))
            self.record('created')
            app.Visible = False
            app.DisplayAlerts = False
            app.EnableEvents = False
            app.AutomationSecurity = 3
            app.AskToUpdateLinks = False
            app.IgnoreRemoteRequests = True
            self.version = str(app.Version)
            return self
        except Exception:
            self._cleanup()
            raise

    @contextmanager
    def open_copy(self, path, *, read_only=False):
        if threading.get_ident()!=self.thread_id:raise SafetyError('Excel proxies cannot cross owner threads')
        path = development_target(path)
        if not self.app or not self.isolated:
            raise SafetyError('An owned isolated Excel instance is required')
        book = self.app.Workbooks.Open(str(path), UpdateLinks=0, ReadOnly=read_only,
            IgnoreReadOnlyRecommended=True, AddToMru=False, Notify=False)
        # Track immediately: an error during validation must still close our copy.
        self.books.append(book)
        self.record('workbook_opened',path=str(path),read_only=read_only)
        try:
            if Path(book.FullName).resolve() != path:
                raise SafetyError('Excel opened a different workbook than the test copy')
            if not read_only and bool(book.ReadOnly):
                raise FileInUse()
            yield book
        finally:
            book.Close(SaveChanges=False)
            self.books.remove(book)
            # The caller may retain the Python wrapper until its frame exits.
            # Release this owned, closed COM pointer before Quit/CoUninitialize.
            release_metadata(book)
            book.__dict__['_oleobj_']=None
            book.__dict__['_olerepr_']=None
            self.record('workbook_closed',path=str(path))

    def _cleanup(self):
        if self._initialized and threading.get_ident()!=self.thread_id:
            raise SafetyError('Excel cleanup must run on its owner thread')
        cleanup_error = None
        try:
            if self.app and self.isolated:
                for book in list(self.books):
                    try:
                        book.Close(SaveChanges=False)
                        release_metadata(book)
                        book.__dict__['_oleobj_']=None
                        book.__dict__['_olerepr_']=None
                    except Exception as exc:
                        cleanup_error = exc
                self.books.clear()
                if not cleanup_error and int(self.app.Workbooks.Count) == 0:
                    quit_owned=self.app.Quit
                    release_metadata(self.app)
                    gc.collect()
                    self.record('metadata_released_before_quit')
                    quit_owned()  # Only a verified newly-created, empty owned instance.
                    del quit_owned
                    self.record('quit_called')
                elif not cleanup_error:
                    cleanup_error = SafetyError('Unowned workbook appeared in the isolated process; Quit was deferred')
        finally:
            self.app = None
            gc.collect()
            if self._initialized:
                self._ole32.CoUninitialize()
                self._initialized = False
            if self._process_handle:
                import win32event,win32process
                try:
                    if win32event.WaitForSingleObject(self._process_handle,10000)!=win32event.WAIT_OBJECT_0:
                        cleanup_error=SafetyError('Owned Excel did not exit within 10 seconds; no process was killed')
                    else:
                        self.process_exit_code=int(win32process.GetExitCodeProcess(self._process_handle))
                        self.record('process_exited',exit_code=self.process_exit_code)
                        if self.process_exit_code!=0:cleanup_error=SafetyError('Owned Excel exited abnormally; validation stopped')
                finally:
                    self._process_handle.Close()
                    self._process_handle=None
        if self.pre_existing:
            verify_existing_excel(self.pre_existing)
        if cleanup_error:
            raise SafetyError('Cannot safely release isolated Excel resources') from cleanup_error

    def __exit__(self, kind, exc, traceback):
        self._cleanup()
