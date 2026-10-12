"""Native Windows smoke driver, restricted to a named payroll app process."""
import argparse
import json
import time
import ctypes
import sys
from ctypes import wintypes
import win32api
from pathlib import Path
import win32gui
import win32con
import win32process
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.safety import development_target


def windows(pid):
    result=[]
    def inspect(hwnd,_):
        if win32process.GetWindowThreadProcessId(hwnd)[1]==pid:
            result.append({'hwnd':hwnd,'title':win32gui.GetWindowText(hwnd),'class':win32gui.GetClassName(hwnd),
                'visible':bool(win32gui.IsWindowVisible(hwnd)),'minimized':bool(win32gui.IsIconic(hwnd)),
                'rect':win32gui.GetWindowRect(hwnd)})
    win32gui.EnumWindows(inspect,None)
    return result


def perform(pid,action):
    rows=windows(pid)
    main=next(r for r in rows if r['title']=='NTP Payroll Assistant')
    tray=next(r for r in rows if r['title']=='QTrayIconMessageWindow')
    def click_icon(button,double=False):
        class Identifier(ctypes.Structure):
            _fields_=[('size',wintypes.DWORD),('hwnd',wintypes.HWND),('uid',wintypes.UINT),('guid',ctypes.c_byte*16)]
        n=Identifier();n.size=ctypes.sizeof(n);n.hwnd=tray['hwnd'];n.uid=0
        get_rect=ctypes.WinDLL('shell32').Shell_NotifyIconGetRect
        get_rect.argtypes=[ctypes.POINTER(Identifier),ctypes.POINTER(wintypes.RECT)]
        def center():
            rect=wintypes.RECT()
            if get_rect(ctypes.byref(n),ctypes.byref(rect)) not in (0,1):raise RuntimeError('Application tray geometry unavailable')
            return ((rect.left+rect.right)//2,(rect.top+rect.bottom)//2)
        def mouse(point,down,up):
            if not (0<=point[0]<win32api.GetSystemMetrics(0) and 0<=point[1]<win32api.GetSystemMetrics(1)):
                raise RuntimeError('Tray target lies outside the primary screen; no click sent')
            win32api.SetCursorPos(point)
            win32api.mouse_event(down,0,0,0,0);win32api.mouse_event(up,0,0,0,0)
        def overflow_window():
            found=[]
            def inspect(hwnd,_):
                if win32gui.IsWindowVisible(hwnd) and 'TopLevelWindowForOverflowXamlIsland' in win32gui.GetClassName(hwnd):
                    found.append(hwnd)
            win32gui.EnumWindows(inspect,None)
            return found[0] if found else None

        overflow=overflow_window()
        if overflow is None:
            # On Windows 11 Shell_NotifyIconGetRect initially reports the
            # overflow chevron, rather than a hidden icon.  Expand it, then
            # ask UI Automation for this application's labelled button.
            mouse(center(),win32con.MOUSEEVENTF_LEFTDOWN,win32con.MOUSEEVENTF_LEFTUP)
            time.sleep(.3)
            overflow=overflow_window()
        if overflow is None:
            raise RuntimeError('Windows notification-area overflow was not found; no icon input sent')
        from pywinauto import Desktop
        candidates=[button_node for button_node in Desktop(backend='uia').window(handle=overflow).descendants()
                    if button_node.element_info.control_type=='Button'
                    and button_node.element_info.name.startswith('NTP Payroll Assistant')]
        if len(candidates)!=1:
            raise RuntimeError(f'Expected exactly one labelled payroll tray button, found {len(candidates)}; no input sent')
        rect=candidates[0].rectangle()
        point=((rect.left+rect.right)//2,(rect.top+rect.bottom)//2)
        # pywinauto may change process DPI context while loading UIA.  Use
        # physical mouse input after retrieving the current UIA rectangle.
        ctypes.windll.user32.SetProcessDPIAware()
        flags=(win32con.MOUSEEVENTF_RIGHTDOWN,win32con.MOUSEEVENTF_RIGHTUP) if button=='right' else (win32con.MOUSEEVENTF_LEFTDOWN,win32con.MOUSEEVENTF_LEFTUP)
        mouse(point,*flags)
        if double:time.sleep(.07);mouse(point,*flags)
    if action in ('close','minimize'):
        if action=='close':win32gui.PostMessage(main['hwnd'],win32con.WM_CLOSE,0,0)
        else:win32gui.ShowWindow(main['hwnd'],win32con.SW_MINIMIZE)
    elif action in ('click','double'):
        click_icon('left',double=action=='double')
    elif action in ('open','exit'):
        click_icon('right')
        time.sleep(.25)
        menus=[r for r in windows(pid) if r['visible'] and r['hwnd'] not in (main['hwnd'],tray['hwnd'])]
        if not menus:raise RuntimeError('Native application context menu was not found; no input sent')
        popup=menus[0]['hwnd']
        if menus[0]['class']!='#32768':
            key=win32con.VK_END if action=='exit' else win32con.VK_HOME
            # This is a real user-equivalent keystroke after the real tray
            # button activated the QMenu.  QMenu receives it as foreground.
            win32api.keybd_event(key,0,0,0); win32api.keybd_event(key,0,win32con.KEYEVENTF_KEYUP,0)
            win32api.keybd_event(win32con.VK_RETURN,0,0,0); win32api.keybd_event(win32con.VK_RETURN,0,win32con.KEYEVENTF_KEYUP,0)
            time.sleep(.5)
            return {'pid':pid,'action':action,'before':rows,'menu':menus,'after':windows(pid),'foreground':win32gui.GetForegroundWindow()}
        menu=win32gui.SendMessage(popup,0x1E1,0,0)  # MN_GETHMENU
        expected='ออก' if action=='exit' else 'เปิด NTP Payroll Assistant'
        items=[(win32gui.GetMenuString(menu,i,win32con.MF_BYPOSITION),win32gui.GetMenuItemID(menu,i)) for i in range(win32gui.GetMenuItemCount(menu))]
        chosen=next(i for text,i in items if text.replace('&','')==expected)
        win32gui.PostMessage(tray['hwnd'],win32con.WM_COMMAND,chosen,0)
        win32gui.PostMessage(popup,win32con.WM_KEYDOWN,win32con.VK_ESCAPE,0)
    time.sleep(.4)
    return {'pid':pid,'action':action,'before':rows,'after':windows(pid),'foreground':win32gui.GetForegroundWindow()}


if __name__=='__main__':
    ctypes.windll.user32.SetProcessDPIAware()
    parser=argparse.ArgumentParser()
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--action',choices=['state','close','minimize','click','double','open','exit'],default='state')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    result=perform(args.pid,args.action)
    if args.output:
        path=development_target(args.output)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
