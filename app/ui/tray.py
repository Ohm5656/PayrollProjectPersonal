from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
import logging
from app.services.automation_runtime import RuntimeState


def status_icon(color):
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(3, 3, 26, 26)
    painter.end()
    return QIcon(pixmap)


class PayrollTray(QSystemTrayIcon):
    def __init__(self, runtime, application, *, show_main_window, get_window=None):
        super().__init__(status_icon('#808080'), application)
        self.runtime, self.application = runtime, application
        self.restore = show_main_window
        self.get_window = get_window
        menu = QMenu()
        self.menu=menu
        for text, callback in [('เปิด NTP Payroll Assistant', self.open_main),
                               ('ตรวจสอบเงินเดือน', self.open_review),
                               ('เปิดไฟล์บันทึกเวลา', lambda: self.open_copy('attendance')),
                               ('เปิดไฟล์เงินเดือน', lambda: self.open_copy('payroll')),
                               ('ดูประวัติ', self.open_history), ('ตั้งค่า', self.open_settings)]:
            action = QAction(text, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        menu.addSeparator()
        self.pause_action = QAction('หยุดเฝ้าดูชั่วคราว', menu)
        self.pause_action.triggered.connect(self.runtime.pause_monitoring)
        menu.addAction(self.pause_action)
        self.resume_action = QAction('เริ่มเฝ้าดูอีกครั้ง', menu)
        self.resume_action.triggered.connect(self.runtime.resume_monitoring)
        menu.addAction(self.resume_action)
        menu.addSeparator()
        action = QAction('ออก', menu)
        action.triggered.connect(self.exit)
        menu.addAction(action)
        self.setContextMenu(menu)
        self.activated.connect(self.activation)
        runtime.state_changed.connect(self.state)
        runtime.notification.connect(self.message)
        runtime.shutdown_ready.connect(self.exit)
        self.state(runtime.state)
        self.last_message = None

    def open_main(self):
        logging.getLogger('ntp').info('Tray Open action triggered')
        self.restore('tray_open')

    def _window(self, reason):
        self.restore(reason)
        return self.get_window() if self.get_window else None

    def open_review(self):
        window = self._window('tray_review')
        if window:
            window.review()

    def open_copy(self, kind):
        window = self._window('tray_open_' + kind)
        if window:
            window.open_copy(kind)

    def open_history(self):
        window = self._window('tray_history')
        if window:
            window.history()

    def open_settings(self):
        window = self._window('tray_settings')
        if window:
            window.settings()

    def activation(self,reason):
        logging.getLogger('ntp').info('Tray activation: %s',reason.name)
        if reason==QSystemTrayIcon.Context:
            logging.getLogger('ntp').info('Tray context menu exists=%s visible=%s',self.contextMenu() is not None,self.menu.isVisible())
        if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick):
            self.restore('tray_'+reason.name)

    def state(self, state):
        state = str(state).upper()
        color, text = {
            RuntimeState.DISABLED: ('#808080', 'หยุดเฝ้าดู'),
            RuntimeState.WATCHING: ('#31955b', 'กำลังเฝ้าดูไฟล์'),
            RuntimeState.PROCESSING: ('#dfa929', 'กำลังประมวลผล'),
            RuntimeState.REVIEW_REQUIRED: ('#dfa929', 'ต้องตรวจสอบ'),
            RuntimeState.ERROR: ('#d54b47', 'ข้อผิดพลาด'),
        }[state]
        self.setIcon(status_icon(color))
        self.setToolTip('NTP Payroll Assistant — ' + text)
        self.pause_action.setEnabled(state in {RuntimeState.WATCHING, RuntimeState.PROCESSING, RuntimeState.REVIEW_REQUIRED, RuntimeState.ERROR})
        self.resume_action.setEnabled(state in {RuntimeState.DISABLED, RuntimeState.ERROR})

    def message(self, title, message):
        key = (title, message)
        if key != self.last_message:
            self.last_message = key
            self.showMessage(title, message, QSystemTrayIcon.Warning, 6000)

    def exit(self):
        logging.getLogger('ntp').info('Application exit requested from tray')
        if not self.runtime.shutdown():
            return
        self.hide()
        self.application.quit()
