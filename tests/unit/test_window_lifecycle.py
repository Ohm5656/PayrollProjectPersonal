import gc
from threading import Thread
from time import monotonic,sleep
import pytest
from PySide6.QtCore import Qt,QThread
from PySide6.QtWidgets import QMainWindow,QSystemTrayIcon,QLabel
from app.ui.lifecycle import WindowController
from app.ui.single_instance import SingleInstance
from app.ui.tray import PayrollTray
from app.ui.presentation import text
from tests.unit.test_ui import qt_app,draft_case
from app.services.payroll_service import PayrollService
from app.services.automation_runtime import AutomationRuntime
from app.ui.main_window import MainWindow


def test_window_reference_survives_gc_and_repeated_restore(qt_app):
    calls=[]
    def factory():calls.append(1);return QMainWindow()
    controller=WindowController(qt_app,factory)
    controller.show_main_window('manual_launch')
    window=controller.window
    gc.collect()
    window.hide()
    controller.show_main_window('open')
    controller.show_main_window('open_again')
    assert qt_app.main_window is window and window.isVisible()
    assert calls==[1]
    window.close()


def test_minimized_and_visible_window_restore_raises_same_window(qt_app,monkeypatch):
    window=QMainWindow();controller=WindowController(qt_app,lambda:window)
    raised=[];activated=[]
    monkeypatch.setattr(window,'raise_',lambda:raised.append(True))
    monkeypatch.setattr(window,'activateWindow',lambda:activated.append(True))
    window.showMinimized()
    controller.show_main_window('restore_minimized')
    assert not window.isMinimized() and window.isVisible()
    controller.show_main_window('visible_window')
    assert len(raised)==len(activated)==2
    window.close()


def test_worker_restore_is_queued_to_gui_thread(qt_app):
    created=[]
    def factory():created.append(QThread.currentThread());return QMainWindow()
    controller=WindowController(qt_app,factory)
    thread=Thread(target=lambda:controller.show_main_window('worker'))
    thread.start();thread.join()
    assert not created
    qt_app.processEvents()
    assert created==[qt_app.thread()] and controller.window.isVisible()
    controller.window.close()


def test_tray_open_click_double_and_clean_exit_use_authoritative_restore(qt_app,draft_case,monkeypatch):
    runtime=AutomationRuntime(PayrollService(draft_case[0]),qt_app)
    window=MainWindow(runtime.service,runtime=runtime)
    reasons=[];exits=[]
    tray=PayrollTray(runtime,qt_app,show_main_window=reasons.append,get_window=lambda:window)
    next(a for a in tray.contextMenu().actions() if a.text()=='เปิด NTP Payroll Assistant').trigger()
    tray.activated.emit(QSystemTrayIcon.DoubleClick)
    tray.activated.emit(QSystemTrayIcon.Trigger)
    assert reasons==['tray_open','tray_DoubleClick','tray_Trigger']
    monkeypatch.setattr(qt_app,'quit',lambda:exits.append(True))
    tray.exit()
    assert exits==[True]
    window.close()


def test_restore_exception_has_traceback(qt_app,caplog):
    def fail():raise ValueError('controlled window creation failure')
    controller=WindowController(qt_app,fail)
    controller.show_main_window()
    assert any(r.exc_info and 'show_main_window failed' in r.message for r in caplog.records)


def test_single_instance_sends_restore_and_releases_lock(qt_app,workbook_workspace):
    import subprocess,sys
    first=SingleInstance(qt_app,directory=workbook_workspace)
    assert first.acquire_or_notify()
    requested=[];result=[]
    first.show_requested.connect(lambda:requested.append(True))
    code='from PySide6.QtCore import QCoreApplication; from pathlib import Path; import sys; from app.ui.single_instance import SingleInstance; app=QCoreApplication([]); owner=SingleInstance(app,directory=Path(sys.argv[1])); primary=owner.acquire_or_notify(); owner.close(); sys.exit(9 if primary else 0)'
    child=subprocess.Popen([sys.executable,'-c',code,str(workbook_workspace)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    end=monotonic()+8
    while child.poll() is None and monotonic()<end:
        qt_app.processEvents();sleep(.01)
    try:
        # A clean isolated child was measured at about 2.57 seconds on this
        # Windows host. Eight seconds remains bounded but allows normal Qt
        # process startup and pipe teardown under a busy full suite.
        stdout,stderr=child.communicate(timeout=8)
        assert child.returncode==0,(stdout,stderr)
        assert requested==[True]
    finally:
        if child.poll() is None:
            child.terminate()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=3)
        first.close()
        qt_app.processEvents()
    fresh=SingleInstance(qt_app,directory=workbook_workspace)
    assert fresh.acquire_or_notify()
    fresh.close()


def test_duplicate_startup_launch_probes_silently_without_restoring_window(qt_app,workbook_workspace):
    import subprocess,sys
    first=SingleInstance(qt_app,directory=workbook_workspace)
    assert first.acquire_or_notify()
    requested=[]
    first.show_requested.connect(lambda:requested.append(True))
    code='from PySide6.QtCore import QCoreApplication; from pathlib import Path; import sys; from app.ui.single_instance import SingleInstance; app=QCoreApplication([]); owner=SingleInstance(app,directory=Path(sys.argv[1])); primary=owner.acquire_or_notify(show_existing=False); owner.close(); sys.exit(9 if primary else 0)'
    child=subprocess.Popen([sys.executable,'-c',code,str(workbook_workspace)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    end=monotonic()+8
    while child.poll() is None and monotonic()<end:
        qt_app.processEvents();sleep(.01)
    try:
        stdout,stderr=child.communicate(timeout=8)
        assert child.returncode==0,(stdout,stderr)
        assert requested==[]
    finally:
        if child.poll() is None:
            child.terminate(); child.wait(timeout=3)
        first.close(); qt_app.processEvents()


@pytest.mark.parametrize('value,expected',[('UNKNOWN_RULE','ยังไม่มีเงื่อนไขที่ยืนยัน'),('AUTO_REUSE','ใช้ค่าประจำเดิม'),
 ('ONE_TIME','รายการครั้งเดียว'),('CONFIRMED','ยืนยันเงินเดือนแล้ว'),('WRITTEN','บันทึกลง Excel แล้ว'),('LOCKED','ปิดรอบเดือนแล้ว')])
def test_technical_values_translate_without_changing_persistence(value,expected):assert text(value)==expected


def test_first_screen_has_next_steps_and_collapsed_advanced_controls(qt_app,draft_case):
    window=MainWindow(PayrollService(draft_case[0]))
    labels=[label.text() for label in window.findChildren(QLabel)]
    assert any('1 เลือกเดือน' in label and '5 อ่านข้อมูล' in label for label in labels)
    from PySide6.QtWidgets import QGroupBox
    group=next(g for g in window.findChildren(QGroupBox) if g.title()=='ตัวเลือกเพิ่มเติม')
    assert not group.isChecked()
    window.close()
