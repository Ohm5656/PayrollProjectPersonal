"""User-session desktop application. Development activation is copies-only."""
from logging.handlers import RotatingFileHandler
from pathlib import Path
import argparse
import json
import logging
import os
import sys

from app.db.database import Database
from app.db.repositories import Repository
from app.safety import ROOT, TEST_ROOT, development_target, record_baseline
from app.services.history_service import import_history
from app.services.payroll_service import PayrollService


def configure_logging():
    path = development_target(TEST_ROOT / 'app_state' / 'logs' / 'app.log')
    path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger('ntp')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=3, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    return logger


def main():
    parser = argparse.ArgumentParser(description='NTP Payroll Assistant — safe copy test mode')
    parser.add_argument('--minimized', action='store_true')
    parser.add_argument('--startup', action='store_true')
    parser.add_argument('--smoke-test', action='store_true')
    args = parser.parse_args()
    if args.smoke_test:
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    else:
        # Test-only environment flags must not turn a manual launch invisible.
        if os.environ.get('QT_QPA_PLATFORM') in {'offscreen','minimal'}:
            os.environ.pop('QT_QPA_PLATFORM')
    from PySide6.QtCore import QLockFile, QTimer
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon
    from app.ui.main_window import MainWindow
    from app.ui.tray import PayrollTray
    from app.ui.lifecycle import WindowController
    from app.ui.single_instance import SingleInstance
    application = QApplication(sys.argv[:1])
    application.setApplicationName('NTP Payroll Assistant')
    logger = configure_logging()
    instance=SingleInstance(application)
    try:
        if not instance.acquire_or_notify():return 0
        logger.info('Application started pid=%s mode=%s platform=%s',os.getpid(),'startup' if args.startup or args.minimized else 'manual',application.platformName())
        def exception_hook(kind,value,traceback):
            logger.error('Unhandled UI signal exception',exc_info=(kind,value,traceback))
            sys.__excepthook__(kind,value,traceback)
        sys.excepthook=exception_hook
        record_baseline(ROOT / 'reports' / 'source_hash_baseline.json')
        repo = Repository(Database(TEST_ROOT / 'app_state' / 'data' / 'ntp_payroll.db'))
        evidence = ROOT / 'reports' / 'historical_analysis.json'
        if evidence.exists():
            import_history(repo, json.loads(evidence.read_text(encoding='utf-8')), ROOT / 'reference_data')
        service = PayrollService(repo)
        from app.excel.payroll_writer import PayrollWriter
        controller=WindowController(application,lambda:MainWindow(service,writer=PayrollWriter(service)))
        window=controller.ensure_window()
        tray = PayrollTray(window, application,show_main_window=controller.show_main_window)
        application.payroll_tray=tray
        instance.show_requested.connect(lambda:controller.show_main_window('second_launch'))
        window.tray = tray
        window.configure_watcher()
        available = QSystemTrayIcon.isSystemTrayAvailable()
        application.setQuitOnLastWindowClosed(not available)
        if available:
            tray.show()
        if not (args.minimized or args.startup) or not available:
            controller.show_main_window('manual_launch' if not args.smoke_test else 'smoke_test')
        application.aboutToQuit.connect(window.shutdown)
        if args.smoke_test:
            QTimer.singleShot(500, application.quit)
        logger.info('Desktop application started in copies-only mode')
        if os.name == 'nt':
            import win32gui,win32process
            info=win32process.GetStartupInfo()
            logger.info('Launch probe platform=%s qt_visible=%s native_visible=%s minimized=%s startup_flags=%s startup_show=%s hwnd=%s',
                application.platformName(),window.isVisible(),bool(win32gui.IsWindowVisible(int(window.winId()))),window.isMinimized(),info.dwFlags,info.wShowWindow,int(window.winId()))
        result = application.exec()
        window.shutdown()
        logger.info('Desktop application exited')
        return result
    except Exception as exc:
        logger.exception('Application initialization failed')
        if not args.smoke_test:
            QMessageBox.critical(None, 'NTP Payroll Assistant', str(exc))
        return 1
    finally:
        instance.close()


if __name__ == '__main__':
    raise SystemExit(main())
