"""User-only local IPC plus the existing writer/database process lock."""
from hashlib import sha256
import getpass
import json
import logging
from PySide6.QtCore import QObject,QLockFile,Signal
from PySide6.QtNetwork import QLocalServer,QLocalSocket
from app.safety import TEST_ROOT,development_target


class SingleInstance(QObject):
    show_requested=Signal()

    def __init__(self,application,*,directory=None):
        super().__init__(application)
        directory=directory or TEST_ROOT/'app_state'
        path=development_target(directory/'application.lock')
        path.parent.mkdir(parents=True,exist_ok=True)
        self.lock=QLockFile(str(path))
        self.lock.setStaleLockTime(0)
        self.name='ntp-payroll-'+sha256((str(path)+getpass.getuser()).encode()).hexdigest()[:24]
        self.server=QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.UserAccessOption)
        self.server.newConnection.connect(self.receive)
        self.connections=[]
        self.primary=False

    def acquire_or_notify(self, *, show_existing=True):
        if self.lock.tryLock(100):
            self.primary=True
            QLocalServer.removeServer(self.name)  # Only the current lock owner may remove a stale endpoint.
            if not self.server.listen(self.name):
                self.close()
                raise RuntimeError('ไม่สามารถเปิดช่องทางเรียกหน้าต่าง กรุณาลองเปิดโปรแกรมอีกครั้ง')
            return True
        socket=QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(3000):
            raise RuntimeError('โปรแกรมเปิดอยู่แล้ว แต่ยังเรียกหน้าต่างไม่ได้ กรุณารอสักครู่แล้วเปิดอีกครั้ง')
        # A duplicate Scheduled Task launch proves the existing tray process is
        # alive but must not unexpectedly surface its main window.
        request = b'show\n' if show_existing else b'ping\n'
        socket.write(request)
        socket.flush()
        socket.waitForBytesWritten(1000)
        if not socket.canReadLine():socket.waitForReadyRead(5000)
        if not socket.canReadLine() or bytes(socket.readLine())!=b'ok\n':
            raise RuntimeError('โปรแกรมกำลังทำงาน กรุณารอสักครู่แล้วเปิดอีกครั้ง')
        socket.disconnectFromServer()
        logging.getLogger('ntp').info('Second launch signaled existing application; exiting')
        return False

    def receive(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection()
            self.connections.append(socket)
            def read(s=socket):
                if not s.canReadLine():return
                request = bytes(s.readLine())
                if request==b'show\n':
                    logging.getLogger('ntp').info('Existing application received show request')
                    self.show_requested.emit()
                    s.write(b'ok\n')
                    s.flush()
                elif request==b'ping\n':
                    logging.getLogger('ntp').info('Existing application received silent startup probe')
                    s.write(b'ok\n')
                    s.flush()
                s.disconnectFromServer()
            socket.readyRead.connect(read)
            def cleanup(s=socket):
                if s in self.connections:self.connections.remove(s)
                s.deleteLater()
            socket.disconnected.connect(cleanup)
            read()

    def close(self):
        if self.primary:
            for socket in list(self.connections):
                socket.disconnectFromServer()
                socket.deleteLater()
            self.connections.clear()
            self.server.close()
            QLocalServer.removeServer(self.name)
            self.lock.unlock()
            self.primary=False
