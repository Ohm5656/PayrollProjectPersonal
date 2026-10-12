"""One GUI-thread owner and one path for showing/restoring the main window."""
import logging
import os
from PySide6.QtCore import QObject,QThread,Signal,Slot,Qt


class WindowController(QObject):
    requested=Signal(str)

    def __init__(self,application,factory):
        super().__init__(application)
        self.application,self.factory=application,factory
        self.window=None
        self.logger=logging.getLogger('ntp')
        self.requested.connect(self._show,Qt.QueuedConnection)
        application.window_controller=self

    def ensure_window(self):
        if QThread.currentThread()!=self.application.thread():
            raise RuntimeError('Main window creation requires the GUI thread')
        if self.window is None:
            self.window=self.factory()
            self.application.main_window=self.window
            self.window.setAttribute(Qt.WA_DeleteOnClose,False)
            self.logger.info('Main window created pid=%s',os.getpid())
        return self.window

    def show_main_window(self,reason='open'):
        if QThread.currentThread()!=self.application.thread():
            self.requested.emit(str(reason))
            return
        self._show(str(reason))

    @Slot(str)
    def _show(self,reason):
        try:
            window=self.ensure_window()
            was_hidden,was_minimized=not window.isVisible(),window.isMinimized()
            window.setWindowState(window.windowState() & ~Qt.WindowMinimized)
            window.showNormal()
            window.show()
            window.raise_()
            window.activateWindow()
            native_visible=None
            if os.name=='nt' and self.application.platformName()=='windows':
                import win32gui,win32con,win32process
                handle=int(window.winId())
                if win32process.GetWindowThreadProcessId(handle)[1]!=os.getpid():
                    raise RuntimeError('Window handle is not owned by this application')
                if not win32gui.IsWindowVisible(handle) or win32gui.IsIconic(handle):
                    win32gui.ShowWindow(handle,win32con.SW_RESTORE)
                try:win32gui.SetForegroundWindow(handle)
                except Exception:self.logger.info('Windows foreground request deferred by foreground policy')
                native_visible=bool(win32gui.IsWindowVisible(handle))
            self.logger.info('Main window shown/restored reason=%s hidden_before=%s minimized_before=%s qt_visible=%s native_visible=%s',
                reason,was_hidden,was_minimized,window.isVisible(),native_visible)
        except Exception:
            self.logger.exception('show_main_window failed reason=%s',reason)

