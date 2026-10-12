from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
import logging
from app.ui.lifecycle import WindowController


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
    def __init__(self, window, application, *, show_main_window=None):
        super().__init__(status_icon('#31955b'), window)
        self.window, self.application = window, application
        self.controller=None if show_main_window else WindowController(application,lambda:window)
        self.restore=show_main_window or self.controller.show_main_window
        menu = QMenu(window)
        self.menu=menu
        for text, callback in [('เปิด NTP Payroll Assistant', self.open_main),
                               ('ตรวจสอบเงินเดือน', window.review),
                               ('เปิดไฟล์บันทึกเวลา', lambda: window.open_copy('attendance')),
                               ('เปิดไฟล์เงินเดือน', lambda: window.open_copy('payroll')),
                               ('ดูประวัติ', window.history), ('ตั้งค่า', window.settings), ('ออก', self.exit)]:
            action = QAction(text, menu)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.setContextMenu(menu)
        self.activated.connect(self.activation)
        window.state_changed.connect(self.state)
        window.notify.connect(self.message)
        window.exit_when_idle.connect(self.exit)
        self.state('ready')
        self.last_message = None

    def open_main(self):
        logging.getLogger('ntp').info('Tray Open action triggered')
        self.restore('tray_open')

    def activation(self,reason):
        logging.getLogger('ntp').info('Tray activation: %s',reason.name)
        if reason==QSystemTrayIcon.Context:
            logging.getLogger('ntp').info('Tray context menu exists=%s visible=%s',self.contextMenu() is not None,self.menu.isVisible())
        if reason in (QSystemTrayIcon.Trigger,QSystemTrayIcon.DoubleClick):
            self.restore('tray_'+reason.name)

    def state(self, state):
        color, text = {'ready': ('#31955b', 'พร้อมใช้งาน'), 'review': ('#dfa929', 'ต้องตรวจสอบ'),
                       'processing': ('#dfa929', 'กำลังประมวลผล'), 'error': ('#d54b47', 'ข้อผิดพลาด')}[state]
        self.setIcon(status_icon(color))
        self.setToolTip('NTP Payroll Assistant — ' + text)

    def message(self, title, message):
        key = (title, message)
        if key != self.last_message:
            self.last_message = key
            self.showMessage(title, message, QSystemTrayIcon.Warning, 6000)

    def exit(self):
        logging.getLogger('ntp').info('Application exit requested from tray')
        if not self.window.shutdown():
            return
        self.hide()
        self.application.quit()
