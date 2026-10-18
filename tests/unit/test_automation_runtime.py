import shutil
import os
from types import SimpleNamespace

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication

from app.db.database import Database
from app.db.repositories import Repository
from app.domain import PayrollState
from app.services.automation_runtime import AutomationRuntime, RuntimeState
from app.services.payroll_service import PayrollService
from app.ui.lifecycle import WindowController
from app.ui.main_window import MainWindow
from app.ui.tray import PayrollTray


@pytest.fixture(scope='session')
def qt_app():
    return QApplication.instance() or QApplication([])


class FakeFolderWatcher:
    instances = []

    def __init__(self, folder, process, *, on_result, notify):
        self.folder, self.process = folder, process
        self.on_result, self.notify = on_result, notify
        self.started = self.stopped = False
        type(self).instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True
        return True

    def trigger(self, path):
        self.on_result(self.process(path))


class ControlledStopWatcher(FakeFolderWatcher):
    stop_outcome = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1
        outcome = type(self).stop_outcome
        if isinstance(outcome, BaseException):
            raise outcome
        if outcome:
            self.stopped = True
        return outcome


def configured_runtime(workbook_workspace):
    attendance, payroll = workbook_workspace / 'attendance', workbook_workspace / 'payroll'
    attendance.mkdir(); payroll.mkdir()
    service = PayrollService(Repository(Database(workbook_workspace / 'runtime.db')))
    runtime = AutomationRuntime(service, folder_watcher_factory=FakeFolderWatcher)
    runtime.workflow.configure(attendance, payroll)
    return runtime, attendance


def controlled_runtime(workbook_workspace, outcome):
    ControlledStopWatcher.instances.clear()
    ControlledStopWatcher.stop_outcome = outcome
    attendance, payroll = workbook_workspace / 'attendance', workbook_workspace / 'payroll'
    attendance.mkdir(); payroll.mkdir()
    service = PayrollService(Repository(Database(workbook_workspace / 'runtime.db')))
    runtime = AutomationRuntime(service, folder_watcher_factory=ControlledStopWatcher)
    runtime.workflow.configure(attendance, payroll)
    assert runtime.resume_monitoring()
    return runtime, attendance, payroll, runtime.watcher


def test_disabled_runtime_never_reports_watching_or_creates_watcher(qt_app, workbook_workspace):
    FakeFolderWatcher.instances.clear()
    runtime, _ = configured_runtime(workbook_workspace)
    runtime.repo.set_setting('watch_enabled', False)
    assert runtime.start()
    assert runtime.state == RuntimeState.DISABLED
    assert runtime.watcher is None and not FakeFolderWatcher.instances
    tray = PayrollTray(runtime, qt_app, show_main_window=lambda _: None)
    assert 'หยุดเฝ้าดู' in tray.toolTip()
    tray.hide()


def test_runtime_pause_resume_is_idempotent_and_owns_watcher(workbook_workspace):
    FakeFolderWatcher.instances.clear()
    runtime, _ = configured_runtime(workbook_workspace)
    assert runtime.resume_monitoring()
    first = runtime.watcher
    assert runtime.state == RuntimeState.WATCHING and first.started
    assert runtime.resume_monitoring()
    assert runtime.watcher is first
    assert len(FakeFolderWatcher.instances) == 1
    assert runtime.pause_monitoring()
    assert runtime.state == RuntimeState.DISABLED and first.stopped and runtime.watcher is None
    assert runtime.pause_monitoring()
    assert runtime.state == RuntimeState.DISABLED


def test_background_processing_requires_no_main_window(qt_app, copied_reference, workbook_workspace):
    FakeFolderWatcher.instances.clear()
    runtime, attendance_folder = configured_runtime(workbook_workspace)
    source = next((copied_reference / 'attendance').glob('* 8.xlsx'))
    attendance = attendance_folder / source.name
    shutil.copy2(source, attendance)
    runtime.resume_monitoring()
    active = runtime.watcher
    active.trigger(attendance)
    qt_app.processEvents()
    qt_app.processEvents()
    assert runtime.last_result is not None
    assert runtime.current_file == attendance
    assert runtime.state == RuntimeState.REVIEW_REQUIRED
    assert active.started and not active.stopped
    assert runtime.shutdown()


def test_tray_open_creates_window_lazily_and_exit_stops_runtime(qt_app, workbook_workspace, monkeypatch):
    FakeFolderWatcher.instances.clear()
    runtime, _ = configured_runtime(workbook_workspace)
    runtime.resume_monitoring()
    controller = WindowController(qt_app, lambda: MainWindow(runtime.service, runtime=runtime))
    tray = PayrollTray(runtime, qt_app, show_main_window=controller.show_main_window, get_window=controller.ensure_window)
    qt_app.payroll_tray = tray
    assert controller.window is None
    tray.open_main()
    assert controller.window is not None
    exits = []
    monkeypatch.setattr(qt_app, 'quit', lambda: exits.append(True))
    tray.exit()
    assert exits == [True]
    assert runtime.watcher is None
    controller.window.close()


def test_closing_visible_window_hides_only_and_keeps_runtime_running(qt_app, workbook_workspace, monkeypatch):
    FakeFolderWatcher.instances.clear()
    runtime, _ = configured_runtime(workbook_workspace)
    runtime.resume_monitoring()
    watcher = runtime.watcher
    window = MainWindow(runtime.service, runtime=runtime)
    window.tray = type('VisibleTray', (), {'isVisible': lambda self: True})()
    window.show()
    window.close()
    assert runtime.watcher is watcher and not watcher.stopped
    assert runtime.state == RuntimeState.WATCHING
    assert runtime.shutdown()


def test_failed_pause_retains_watcher_and_blocks_resume_replacement(workbook_workspace):
    runtime, _, _, watcher = controlled_runtime(workbook_workspace, False)
    errors = []
    runtime.runtime_error.connect(errors.append)
    assert not runtime.pause_monitoring()
    assert runtime.repo.setting('watch_enabled') is False
    assert runtime.watcher is watcher
    assert runtime.state == RuntimeState.ERROR
    assert errors and 'still stopping' in errors[-1]
    assert not runtime.resume_monitoring()
    assert runtime.watcher is watcher
    assert len(ControlledStopWatcher.instances) == 1
    ControlledStopWatcher.stop_outcome = True
    assert runtime.pause_monitoring()
    assert runtime.watcher is None and runtime.state == RuntimeState.DISABLED


def test_stop_exception_retains_watcher_and_tray_exit_is_contained(qt_app, workbook_workspace, monkeypatch):
    runtime, _, _, watcher = controlled_runtime(workbook_workspace, RuntimeError('stop exploded'))
    exits, errors = [], []
    runtime.runtime_error.connect(errors.append)
    tray = PayrollTray(runtime, qt_app, show_main_window=lambda _: None)
    monkeypatch.setattr(qt_app, 'quit', lambda: exits.append(True))
    tray.exit()
    assert exits == []
    assert runtime.watcher is watcher and runtime.state == RuntimeState.ERROR
    assert errors and 'stop exploded' in errors[-1]
    assert len(ControlledStopWatcher.instances) == 1
    ControlledStopWatcher.stop_outcome = True
    assert runtime.shutdown()
    tray.hide()


def test_reconfigure_does_not_start_replacement_after_failed_stop(workbook_workspace):
    runtime, attendance, _, watcher = controlled_runtime(workbook_workspace, False)
    replacement_attendance = attendance.parent / 'replacement_attendance'
    replacement_payroll = attendance.parent / 'replacement_payroll'
    replacement_attendance.mkdir(); replacement_payroll.mkdir()
    runtime.workflow.configure(replacement_attendance, replacement_payroll)
    assert not runtime.reconfigure()
    assert runtime.watcher is watcher
    assert runtime.state == RuntimeState.ERROR
    # Phase B.1 tightened the A.1 invariant: no replacement is even built
    # until the currently owned watcher has confirmed it stopped.
    assert len(ControlledStopWatcher.instances) == 1
    ControlledStopWatcher.stop_outcome = True
    assert runtime.reconfigure()
    assert runtime.state == RuntimeState.WATCHING
    assert runtime.watcher is ControlledStopWatcher.instances[-1]
    assert runtime.shutdown()


def test_shutdown_false_stop_keeps_ownership_and_does_not_claim_disabled(workbook_workspace):
    runtime, _, _, watcher = controlled_runtime(workbook_workspace, False)
    assert not runtime.shutdown()
    assert runtime.watcher is watcher
    assert runtime.state == RuntimeState.ERROR
    ControlledStopWatcher.stop_outcome = True
    assert runtime.shutdown()
    assert runtime.watcher is None and runtime.state == RuntimeState.DISABLED


def test_queued_processing_result_cannot_revive_a_watcher_being_stopped(workbook_workspace):
    runtime, _, _, _ = controlled_runtime(workbook_workspace, False)
    assert not runtime.pause_monitoring()
    runtime._processing_started('late-event.xlsx')
    runtime._processing_finished({'draft': SimpleNamespace(source_path='late-event.xlsx', state=PayrollState.READY)})
    assert runtime.state == RuntimeState.ERROR
    ControlledStopWatcher.stop_outcome = True
    assert runtime.shutdown()
