"""Record the real exit status of an already-running local validation process."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime,timezone
import json
from pathlib import Path
from time import monotonic
from app.safety import development_target


def record_exit(pid,destination):
    destination=development_target(Path(destination))
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.GetExitCodeProcess.argtypes=[wintypes.HANDLE,ctypes.POINTER(wintypes.DWORD)]
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    handle=kernel.OpenProcess(0x1000|0x100000,False,pid)
    if not handle: raise OSError('Validation process is no longer available to observe')
    try:
        created,ended,user,system=(wintypes.FILETIME() for _ in range(4))
        if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(ended),ctypes.byref(user),ctypes.byref(system)):
            raise OSError('Cannot identify validation process creation time')
        deadline=monotonic()+1800
        while kernel.WaitForSingleObject(handle,1000)==0x102:
            if monotonic()>deadline: raise TimeoutError('Validation process did not complete within observation limit')
        result=wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle,ctypes.byref(result)): raise OSError('Cannot record validation exit status')
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(json.dumps({'pid':pid,'creation_filetime':(created.dwHighDateTime<<32)|created.dwLowDateTime,
            'exit_code':result.value,'recorded_at':datetime.now(timezone.utc).isoformat()},indent=2)+'\n',encoding='utf-8')
        return result.value
    finally:kernel.CloseHandle(handle)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    print('Actual pytest process exit:',record_exit(args.pid,args.output))
